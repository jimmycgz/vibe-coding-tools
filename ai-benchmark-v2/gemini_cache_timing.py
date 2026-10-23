#!/usr/bin/env python3
"""Gemini cache timing test: is a Vertex implicit cache hit faster than a request that cannot hit?

Built on the data of Anthropic's cost-optimisation cookbook notebook (MIT licence): https://github.com/anthropics/claude-cookbooks/blob/a162e0184e71b60290808a43961a6cbc8060123c/cost_optimization/cost_optimization.ipynb

The Gemini counterpart of cache_timing.py, on Vertex AI, single requests (not the agent loop), so that time to first token
measures reading the prompt and thinking at the lowest level, not tool calls. The model is gemini-3.8-flash; gemini-4-argon
runs only with --only argon.

Vertex's implicit cache is on for every project and only a project administrator can switch it off, and the usage block
reports a hit (usageMetadata.cachedContentTokenCount) but never a write. So this test does not use the states of
cache_timing.py. Each set has three requests, each with a different claim as its question, sent one at a time:

  first request          a fresh nonce at the head of the system instruction, so no earlier prefix matches.
                         Valid when cachedContentTokenCount is 0 or absent.
  repeat request         a follow-up turn, sent straight after the first request of its set: that request's whole body
  (follow-up turn)       (the same nonce, system instruction, tools, tool config and generation config), then its own
                         reply as a model turn with the parts exactly as received (thought signatures kept), then a new
                         user turn holding a different question. A valid hit when cachedContentTokenCount is at least T
                         percent of the prompt tokens, T given by --threshold (no default: the live run and --report
                         refuse without it). If the first request failed there is no reply to carry, so the repeat is
                         not sent; the report lists it as not sent and counts it as a repeat that is not a valid hit.
  second first request   the control: another fresh nonce and a third question. Valid as a first request is.

Why a follow-up turn: a live check on Vertex found that a request with the same prefix and a NEW question as its only user
turn read nothing from the implicit cache (0 percent at about 8K, 48K and 171K prompt tokens), while a follow-up turn read
92.6 percent at 48K (an identical repeat read 93.1 percent). So the repeat request measures a later turn of a conversation
that carries the earlier turn. Its prompt is a little longer than its first request's (the reply and the new question,
about 200 tokens in that check); every check below uses each request's own promptTokenCount.

Order inside a set alternates: sets 1, 3, 5 ... run first request, repeat request, second first request; sets 2, 4, 6 ...
run second first request, first request, repeat request. The repeat always comes straight after the first request of its
set; the control sits after the repeat in odd sets and before the first request in even sets, so it does not take up an
order effect. Claims rotate as in cache_timing.schedule: over ten sets each state sees every claim once.

The prefix is cache_timing.py's long prefix, taken from its build_body: the nonce line and the benchmark's system prompt,
then the claims ledger, as two parts of systemInstruction; the twelve tools as functionDeclarations with function calling
mode NONE; the question as the only user content of a first request (the repeat request adds the reply and a second user
turn, as above).

Reading rule, fixed before the run:
  - Headline: repeat request against first request, on time to first token, paired within each set.
  - If fewer than 8 of the 10 repeat requests are valid hits, the reading is "inconclusive".
  - Otherwise it is "seen" when at least 8 sets give a valid pair (a valid first request and a valid hit) and the repeat
    was faster in at least 8 of those valid pairs, and "not seen" in every other case.
  - The same count for first request against second first request is reported beside it as a noise floor, not a finding.
  - The output-speed negative control of cache_timing.py is kept: flagged only when the gap between the state medians is
    over 10 percent AND over the widest within-state interquartile range.
A request that fails its state check is listed by name with its timings and cached share, and left out of the medians and
the pairs; the excluded pairs are printed.

usage:
  gemini_cache_timing.py --selftest | --selftest-fault
  gemini_cache_timing.py --dry-run [--reps N] [--only flash|argon] [--thinking-level LOW]
      prints the schedule, the first request body and the shape of the repeat request (its contents roles and size, with
      the reply shown as <first reply>); the project is shown as <PROJECT>, the token as <REDACTED>
  gemini_cache_timing.py --estimate [--reps N] [--only flash|argon]      upper-bound cost, nothing read from the cache; no network
  gemini_cache_timing.py --live --ceiling-usd X --out DIR --threshold T [--smoke] [--reps N] [--only flash|argon]
      the paid run (needs what gemini_benchmark.py --live needs in the environment); --smoke runs one set and needs no
      threshold: it prints each repeat request's cached share
  gemini_cache_timing.py --report DIR --threshold T [--out DIR2]       the table and three charts from DIR/requests.jsonl
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import statistics
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_benchmark as mb  # noqa: E402  (claims, tools, system prompt, _elide)
import gemini_benchmark as gb  # noqa: E402  (tool conversion, endpoint, streaming, Run and redaction, cost, readiness)
import cache_timing as ct  # noqa: E402  (the long prefix and question, quartiles, tokens per second, negative control)
import build_results_table as brt  # noqa: E402  (SVG helpers for the charts)

# ---------------------------------------------------------------- settings (each one a named constant on purpose)

ROLES = {"flash": "gemini-3.8-flash", "argon": "gemini-4-argon"}   # --only name -> role key in gemini_models.json
ROLE_ORDER = ["flash", "argon"]
STATES = ["first", "repeat", "control"]
STATE_LABEL = {"first": "first request", "repeat": "repeat request (follow-up turn)", "control": "second first request"}
LEGEND_STEP = 230                              # chart legend spacing, wide enough for the longest label
STATE_COLOR = {"first": "#5b4aa5", "repeat": "#3b8f6b", "control": "#8c97a3"}
ODD_ORDER = ["first", "repeat", "control"]     # sets 1, 3, 5 ...
EVEN_ORDER = ["control", "first", "repeat"]    # sets 2, 4, 6 ...
ANSWER_TOKENS = 256                            # as max_tokens in cache_timing.build_body
# The docs read do not say whether maxOutputTokens also bounds the thinking tokens, so the limit is the answer plus the
# same thinking allowance gemini_benchmark.py's spend guard adds, and a short answer is never cut off by thinking.
THINKING_ALLOWANCE = gb.WORST_CASE_EXTRA_THOUGHT_TOKENS
DEFAULT_THINKING_LEVEL = "LOW"                 # the lowest level both models accept (MINIMAL is refused, docs 2026-10-22)
FUNCTION_CALLING_MODE = "NONE"                 # the tools are in the prompt, the model may not call them
# cache_timing.build_body's state without cache_control; only its text (system blocks and question) is used here.
NO_BREAKPOINT = "none"
# --estimate: the long prefix's size by the Anthropic counter (148,271 tokens: system prompt, tools and ledger). Gemini's
# own count differs and is read from promptTokenCount in the smoke set.
PREFIX_TOKENS_ESTIMATE = 148_000
# --estimate: how much longer a repeat request's prompt is than its first request's: the first reply (at most ANSWER_TOKENS
# of answer, plus its thought signatures) and the new question. The live check measured about 200 tokens; 1,000 leaves room
# for a full answer and a longer question.
FOLLOWUP_EXTRA_TOKENS = 1_000
# Spend guard: the ledger is mostly digits and commas, about 1.7 characters a token by the Anthropic count, so the 3
# characters a token gemini_benchmark.py's guard assumes would undercount it. 1.25 leaves room for a finer tokenizer.
GUARD_CHARS_PER_TOKEN = 1.25
# The pricing page charges every token of a request at long-context rates above 200K input tokens. The models file holds
# the rate up to 200K, so the run stops if a prompt is larger than this.
LONG_CONTEXT_TOKENS = 200_000
MIN_HITS = 8                                   # valid repeat hits needed (of the 10) before any reading
MIN_PAIRS = 8                                  # valid pairs needed for "seen"
MIN_FASTER = 8                                 # valid pairs in which the repeat must be faster for "seen"
MIN_THRESHOLD = 50.0                           # the plan: T is never below 50 percent
NC_LIMIT = 0.10                                # the negative control's relative gap, as cache_timing.negative_control
TABLE_NAME = "gemini-cache-timing-table.md"
MAPPING_NOTE = ("These three states do not map onto the Anthropic cold, warm and no-cache states (a Gemini first request "
                "may be stored implicitly with no write field, and no request runs without the cache), so they are never "
                "drawn on one chart with them. The repeat request is a follow-up turn: the first request, its reply and a "
                "new question, so it measures a turn that carries the earlier turn, not a new user reading a shared "
                "document; it is not comparable with the Anthropic warm cache.")
PREFIX_NOTE = "Prefix: the benchmark's system prompt and tools plus the claims ledger."
FORBIDDEN_STATE_WORDS = re.compile(r"\bcold\b|\bwarm\b|no[- ]cache", re.I)   # the Anthropic state names, never ours


# ---------------------------------------------------------------- schedule

def schedule(reps, claims, only="flash"):
    """The fixed run order: one set of three requests per repetition, three DIFFERENT claims in a set (offsets 0, 3, 6 are
    distinct mod 10). Over ten repetitions each state sees every claim exactly once, as in cache_timing.schedule."""
    out, n = [], len(claims)
    mi = ROLE_ORDER.index(only)
    for r in range(reps):
        base = (r + mi) % n
        assign = {"first": claims[base]["id"], "repeat": claims[(base + 3) % n]["id"],
                  "control": claims[(base + 6) % n]["id"]}
        out.append({"set": r + 1, "role": only, "order": list(ODD_ORDER if r % 2 == 0 else EVEN_ORDER), "claims": assign})
    return out


def fresh_nonces():
    """Two different nonces: one for the first and repeat requests of a set, one for its second first request."""
    a = time.time_ns()
    b = time.time_ns()
    while b == a:
        b = time.time_ns()
    return a, b


# ---------------------------------------------------------------- request shape

def prefix_and_question(nonce, claim, ledger):
    """The system text blocks and the question exactly as cache_timing.py builds them for its long prefix."""
    b = ct.build_body("", "long", nonce, claim, NO_BREAKPOINT, ledger)
    return [blk["text"] for blk in b["system"]], b["messages"][0]["content"]


def build_body(nonce, claim, ledger, level=DEFAULT_THINKING_LEVEL):
    level = level.upper()
    if level not in gb.THINKING_LEVELS:
        raise SystemExit("thinking level %s is not one of %s" % (level, ", ".join(gb.THINKING_LEVELS)))
    texts, question = prefix_and_question(nonce, claim, ledger)
    thinking = {gb.THINKING_LEVEL_KEY: level}
    if gb.INCLUDE_THOUGHTS:
        thinking["includeThoughts"] = True
    return {"systemInstruction": {"parts": [{"text": t} for t in texts]},
            "contents": [{"role": "user", "parts": [{"text": question}]}],
            "tools": gb.gemini_tools(mb.TOOLS),
            "toolConfig": {"functionCallingConfig": {"mode": FUNCTION_CALLING_MODE}},
            "generationConfig": {"maxOutputTokens": ANSWER_TOKENS + THINKING_ALLOWANCE, "thinkingConfig": thinking}}


def reply_parts(resp):
    """The parts of a reply's first candidate, or None when there is no reply or it has no parts to carry."""
    try:
        parts = resp["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return None
    return parts or None


def followup_body(first_body, first_resp, question_parts):
    """The repeat request: the first request's body, then the first reply as a model turn and a new user turn.

    first_body is copied, so its system instruction, tools, tool config and generation config go out unchanged, nonce and
    all. The model turn carries the reply's parts exactly as received (thought signatures included), because Gemini expects
    earlier model turns echoed back as they came. question_parts are the parts of the new user turn: the repeat claim's
    question, as build_body puts it in contents[0]["parts"]. Raises ValueError when the reply has no parts."""
    parts = reply_parts(first_resp)
    if parts is None:
        raise ValueError("the first reply has no parts to carry into a follow-up turn")
    body = json.loads(json.dumps(first_body))
    body["contents"] = body["contents"] + [{"role": "model", "parts": json.loads(json.dumps(parts))},
                                           {"role": "user", "parts": json.loads(json.dumps(question_parts))}]
    return body


def repeat_question_parts(nonce, claim, ledger, level=DEFAULT_THINKING_LEVEL):
    """The user parts a first request for this claim would send: the question the repeat request asks in its new turn."""
    return build_body(nonce, claim, ledger, level)["contents"][0]["parts"][-1:]


# ---------------------------------------------------------------- checks and the reading rule

def threshold_problem(t):
    if t is None:
        return "--threshold T is required (percent of the prompt tokens a repeat request must read from the cache; fixed " \
               "in the pre-registration from the smoke set, no default)"
    if not MIN_THRESHOLD <= t <= 100:
        return "--threshold must be between %g and 100 percent, got %g" % (MIN_THRESHOLD, t)
    return None


def check_state(state, usage, threshold):
    """(ok, reason, cached share). The share is cachedContentTokenCount over all prompt tokens (gemini_benchmark.cache_split,
    which is promptTokenCount under its PROMPT_COUNT_INCLUDES_CACHED). ok is None for a repeat request with no threshold."""
    if state not in STATES:
        raise ValueError("unknown state %r" % state)
    _, cached, total = gb.cache_split(usage or {})
    if total <= 0:
        return False, "no prompt tokens in usageMetadata", None
    share = cached / total
    if state in ("first", "control"):
        ok = cached == 0
        return ok, ("" if ok else "%s shows %d cached tokens (%.1f percent): its prefix was not fresh"
                    % (STATE_LABEL[state], cached, 100 * share)), share
    if threshold is None:
        return None, "threshold not set", share
    ok = cached * 100 >= threshold * total
    return ok, ("" if ok else "repeat request read %.1f percent from the cache, below the threshold of %g percent"
                % (100 * share, threshold)), share


def reading(hits, diffs):
    """The reading rule (see the module docstring). hits = valid repeat hits; diffs = repeat minus first request over the
    VALID pairs only. Returns (reading, pairs where the repeat was faster, valid pairs)."""
    faster = sum(1 for d in diffs if d < 0)
    if hits < MIN_HITS:
        return "inconclusive", faster, len(diffs)
    if len(diffs) >= MIN_PAIRS and faster >= MIN_FASTER:
        return "seen", faster, len(diffs)
    return "not seen", faster, len(diffs)


# ---------------------------------------------------------------- dry run and estimate (no network)

def dry_run(gm, only, reps, claims, level=DEFAULT_THINKING_LEVEL, show_limit=300):
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or gb.DEFAULT_LOCATION   # a region name, not a credential
    role = ROLES[only]
    sched = schedule(reps, claims, only)
    print("%d sets, %d requests, one at a time; model %s; thinking level %s; maxOutputTokens %d (answer %d plus thinking "
          "allowance %d)" % (len(sched), 3 * len(sched), gm["models"][role]["id"], level.upper(),
                             ANSWER_TOKENS + THINKING_ALLOWANCE, ANSWER_TOKENS, THINKING_ALLOWANCE))
    for s in sched:
        print("  set %2d  %s" % (s["set"], " -> ".join("%s (%s)" % (STATE_LABEL[x], s["claims"][x]) for x in s["order"])))
    by_id = {c["id"]: c for c in claims}
    ledger = ct.load_ledger()
    body = build_body("<time_ns>", by_id[sched[0]["claims"]["first"]], ledger, level)
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    print("the first request of set 1:")
    print("  POST %s" % gb.endpoint(gm["models"][role]["id"], gb.PROJECT_PLACEHOLDER, location))
    print("  headers " + json.dumps(gb.request_headers()))
    print("  body bytes %d sha256 %s (with the nonce shown as <time_ns>)" % (len(raw), hashlib.sha256(raw).hexdigest()))
    print("  body " + json.dumps(mb._elide(body, show_limit), ensure_ascii=False))
    # no reply exists in a dry run, so the model turn holds a placeholder where the first reply's parts will go
    placeholder = {"candidates": [{"content": {"role": "model", "parts": [{"text": "<first reply>"}]}}]}
    rep = followup_body(body, placeholder, repeat_question_parts("<time_ns>", by_id[sched[0]["claims"]["repeat"]], ledger,
                                                                 level))
    rep_raw = json.dumps(rep, ensure_ascii=False).encode("utf-8")
    print("the %s of set 1: the first request's body, then its reply as a model turn, then a new user turn with the "
          "question for %s" % (STATE_LABEL["repeat"], sched[0]["claims"]["repeat"]))
    print("  contents roles %s" % ", ".join(c["role"] for c in rep["contents"]))
    print("  body bytes %d (the reply shown as <first reply>; the live body is longer by the reply)" % len(rep_raw))
    print("  model turn " + json.dumps(rep["contents"][1], ensure_ascii=False))
    print("  system instruction, tools, tool config and generation config: the same bytes as the first request's: %s"
          % all(json.dumps(rep[k], ensure_ascii=False) == json.dumps(body[k], ensure_ascii=False)
                for k in ("systemInstruction", "tools", "toolConfig", "generationConfig")))
    print("the second first request differs from the first request in the nonce line and the question")
    for why in gb.readiness([{"role": role}], gm, location):
        print("note: the live run would refuse: " + why)
    print("no network call was made and no credential was read")


def estimate(gm, only, reps):
    role = ROLES[only]
    p = (gm.get("prices") or {}).get(role) or {}
    if p.get("in") is None or p.get("out") is None:
        print("prices unread for %s; no estimate" % role)
        return None
    n = 3 * reps
    cap = ANSWER_TOKENS + THINKING_ALLOWANCE
    # each set's repeat request carries the first reply and a second question on top of the prefix
    tin = (n * PREFIX_TOKENS_ESTIMATE + reps * FOLLOWUP_EXTRA_TOKENS) * p["in"] / 1e6
    out_low = n * ANSWER_TOKENS * p["out"] / 1e6
    out_cap = n * cap * p["out"] / 1e6
    out_guard = n * (cap + gb.WORST_CASE_EXTRA_THOUGHT_TOKENS) * p["out"] / 1e6
    print("Upper bound, nothing read from the cache, %s, %d sets, %d requests, list prices from the models file (in %.3f, cached %s, "
          "out %.3f per million, %s):" % (gm["models"][role]["id"], reps, n, p["in"], p.get("cached_in"), p["out"],
                                          p.get("location", "?")))
    print("  input: %d requests x %d prompt tokens (the Anthropic count of the long prefix; Gemini's own count is read from "
          "the smoke set), plus %d tokens for each of the %d follow-up turns (the first reply and the new question), at the "
          "full input price: $%.2f" % (n, PREFIX_TOKENS_ESTIMATE, FOLLOWUP_EXTRA_TOKENS, reps, tin))
    print("  output if every reply reaches maxOutputTokens (%d a request, if that limit also bounds thinking): $%.2f -> "
          "total $%.2f" % (cap, out_cap, tin + out_cap))
    print("  output if the limit does not bound thinking (plus %d thinking tokens, the spend guard's reading): $%.2f -> "
          "total $%.2f" % (gb.WORST_CASE_EXTRA_THOUGHT_TOKENS, out_guard, tin + out_guard))
    print("  lower reference, not a bound: %d answer tokens a request and no thinking: $%.2f -> total $%.2f"
          % (ANSWER_TOKENS, out_low, tin + out_low))
    print("  the smoke set (one set, 3 requests) at the larger bound: $%.2f" % ((tin + out_guard) / reps))
    return tin + out_guard


# ---------------------------------------------------------------- the live run

class _WithPromptTokens:
    """Wraps the requests.jsonl file of gemini_benchmark.Run: adds prompt_tokens (usageMetadata.promptTokenCount) beside
    the cached_tokens Run already writes, redacts the line again, and keeps the last record for the printed line."""
    def __init__(self, f, redact):
        self.f, self.redact, self.last = f, redact, None

    def write(self, line):
        if not line.strip():
            return
        rec = json.loads(line)
        rec["prompt_tokens"] = (rec.get("usage") or {}).get("promptTokenCount")
        self.last = rec
        self.f.write(self.redact(json.dumps(rec)) + "\n")

    def flush(self):
        self.f.flush()

    def close(self):
        self.f.close()


class TimingRun(gb.Run):
    """gemini_benchmark.Run with this test's spend guard: input from the body length at GUARD_CHARS_PER_TOKEN, output at the
    body's maxOutputTokens plus the extra thinking tokens Run's guard allows."""
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.log = _WithPromptTokens(self.log, self.redact)

    def worst_case(self, cfg, body):
        p = self.prices(cfg)
        tin = len(json.dumps(body)) / GUARD_CHARS_PER_TOKEN
        tout = body["generationConfig"]["maxOutputTokens"] + gb.WORST_CASE_EXTRA_THOUGHT_TOKENS
        return (tin * p["in"] + tout * p["out"]) / 1e6


def live(a, gm, claims, env=None, transport=None):
    """The paid run. transport (selftest only) supplies conn_factory, clock, sleep and redact_on."""
    transport = transport or {}
    role = ROLES[a.only]
    cfg = {"id": "gemini-%s-cache-timing" % a.only, "role": role}
    location = (env or {}).get("location") or os.environ.get("GOOGLE_CLOUD_LOCATION") or gb.DEFAULT_LOCATION
    problems = gb.readiness([cfg], gm, location)
    tp = threshold_problem(a.threshold)
    if tp and not (a.smoke and a.threshold is None):
        problems.append(tp)
    if problems:
        raise SystemExit("refusing the live run:\n  " + "\n  ".join(problems))
    env = env or gb.load_env()
    os.makedirs(a.out, exist_ok=True)
    clock = transport.get("clock") or time.monotonic
    level = a.thinking_level.upper()
    ledger = ct.load_ledger()
    by_id = {c["id"]: c for c in claims}
    sched = schedule(1 if a.smoke else a.reps, claims, a.only)
    gb.LIVE["armed"] = True
    run = TimingRun(argparse.Namespace(out=a.out, ceiling_usd=a.ceiling_usd), gm, env, **transport)
    try:
        with open(os.path.join(a.out, "sets.jsonl"), "a", encoding="utf-8") as meta:
            for s in sched:
                n_first, n_control = fresh_nonces()
                nonce = {"first": n_first, "repeat": n_first, "control": n_control}
                meta.write(run.redact(json.dumps({"set": s["set"], "role": s["role"], "model": gm["models"][role]["id"],
                                                  "order": s["order"], "claims": s["claims"], "nonces": nonce,
                                                  "thinking_level": level, "threshold": a.threshold,
                                                  "t": time.time()})) + "\n")
                meta.flush()
                # the first request's body and reply in this set; the repeat is built from these and never from the
                # control, which runs before the first request in even sets
                first_end, first_body, first_resp = None, None, None
                for state in s["order"]:
                    claim = by_id[s["claims"][state]]
                    tag = "%s set%d %s %s" % (s["role"], s["set"], state, claim["id"])
                    if state == "repeat":
                        if first_resp is None or reply_parts(first_resp) is None:
                            why = "its first request failed" if first_resp is None else "its first reply had no parts"
                            print(run.redact("NOT SENT %s: %s, so there is no reply to carry into a follow-up turn"
                                             % (tag, why)), flush=True)
                            meta.write(json.dumps({"set": s["set"], "role": s["role"], "repeat_not_sent": why}) + "\n")
                            meta.flush()
                            if a.smoke:
                                raise SystemExit("smoke: the repeat request was not sent: " + why)
                            continue
                        body = followup_body(first_body, first_resp, repeat_question_parts(nonce[state], claim, ledger, level))
                        meta.write(json.dumps({"set": s["set"], "role": s["role"],
                                               "repeat_gap_s": round(clock() - first_end, 3)}) + "\n")
                        meta.flush()
                    else:
                        body = build_body(nonce[state], claim, ledger, level)
                    try:
                        resp, cost = run.create(tag, cfg, body, level)
                    except RuntimeError as e:
                        print(run.redact("FAILED %s: %s" % (tag, str(e)[:300])), flush=True)
                        if a.smoke:
                            raise
                        continue
                    if state == "first":
                        first_end, first_body, first_resp = clock(), body, resp
                    u = resp.get("usageMetadata") or {}
                    ok, why, share = check_state(state, u, a.threshold)
                    t = (run.log.last or {}).get("timing") or {}
                    word = "share" if ok is None else "ok  " if ok else ("MISS" if state == "repeat" else "FAIL")
                    print(run.redact("%-30s %s cached %7d of %7d (%5.1f percent)  first token %s s  total %.2f s  "
                                     "thinking %d  $%.4f  spent $%.2f%s" % (
                                         tag, word, u.get("cachedContentTokenCount") or 0, u.get("promptTokenCount") or 0,
                                         100 * (share or 0.0), "n/a" if t.get("first_text_s") is None else
                                         "%.2f" % t["first_text_s"], t.get("wall_s") or 0, u.get("thoughtsTokenCount") or 0,
                                         cost, run.spent, "" if ok in (True, None) else "  <- " + why)), flush=True)
                    if (u.get("promptTokenCount") or 0) > LONG_CONTEXT_TOKENS:
                        raise SystemExit("STOP: promptTokenCount %d is above %d, where every token is charged at the "
                                         "long-context rate the models file does not hold" % (u["promptTokenCount"],
                                                                                             LONG_CONTEXT_TOKENS))
        if a.smoke:
            print("smoke: the threshold T is set in the pre-registration from the repeat request's cached share above")
    finally:
        gb.LIVE["armed"] = False
        run.log.close()


# ---------------------------------------------------------------- report

def load_requests(folder, threshold):
    rows = []
    with open(os.path.join(folder, "requests.jsonl"), encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            role, set_s, state, claim = r["tag"].split()
            u, t = r.get("usage") or {}, r.get("timing") or {}
            if r["status"] == 200:
                ok, why, share = check_state(state, u, threshold)
            else:
                ok, why, share = False, "status %s" % r["status"], None
            ftt = t.get("first_text_s") if t.get("first_text_s") is not None else t.get("first_delta_s")
            rows.append({"role": role, "set": int(set_s[3:]), "state": state, "claim": claim, "tag": r["tag"], "ok": ok,
                         "why": why, "share": share, "model": r.get("resolved_model") or r.get("model"),
                         "ftt": ftt, "wall": t.get("wall_s"), "out": u.get("candidatesTokenCount"),
                         "thoughts": u.get("thoughtsTokenCount"), "cached": u.get("cachedContentTokenCount") or 0,
                         "prompt": u.get("promptTokenCount"), "level": r.get("thinking_level"),
                         "tps": ct.tokens_per_second(u.get("candidatesTokenCount"), t.get("wall_s"), t.get("first_text_s")),
                         "cost": r.get("notebook_cost") or 0.0})
    return rows


def load_sets(folder):
    """What sets.jsonl says: the scheduled sets {(role, set): repeat claim}, why a repeat was not sent {(role, set): why},
    and the waits between a first request ending and its repeat starting. Empty when the file is absent."""
    sched, why_not, gaps = {}, {}, []
    sp = os.path.join(folder, "sets.jsonl")
    if not os.path.exists(sp):
        return sched, why_not, gaps
    with open(sp, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            m = json.loads(line)
            key = (m.get("role"), m.get("set"))
            if "order" in m:
                sched[key] = (m.get("claims") or {}).get("repeat")
            if "repeat_not_sent" in m:
                why_not[key] = m["repeat_not_sent"]
            if "repeat_gap_s" in m:
                gaps.append(m["repeat_gap_s"])
    return sched, why_not, gaps


def unsent_repeats(rows, sched, why_not):
    """Scheduled repeat requests with no record in requests.jsonl: the first request failed, or the repeat itself failed
    before a status came back. Each is counted as a repeat that is not a valid hit."""
    seen = {(r["role"], r["set"]) for r in rows if r["state"] == "repeat"}
    out = []
    for (role, s), claim in sorted(sched.items(), key=lambda kv: (ROLE_ORDER.index(kv[0][0]) if kv[0][0] in ROLE_ORDER
                                                                   else len(ROLE_ORDER), kv[0][1])):
        if (role, s) not in seen:
            why = why_not.get((role, s))
            out.append({"role": role, "set": s, "claim": claim, "tag": "%s set%d repeat %s" % (role, s, claim),
                        "why": "not sent: " + why if why else "no record of it (it failed before a status came back)"})
    return out


def cells(rows):
    out = {}
    for role in ROLE_ORDER:
        for state in STATES:
            rs = [r for r in rows if r["role"] == role and r["state"] == state]
            if rs:
                good = [r for r in rs if r["ok"]]
                out[(role, state)] = {"n": len(rs), "ok": len(good), "rows": good, "failed": [r for r in rs if not r["ok"]]}
    return out


def med(c, key):
    return ct.quartiles([r[key] for r in c["rows"]])


def paired(rows, role, a, b, key="ftt", sets=()):
    """Per set, a minus b, over VALID pairs only. sets: the scheduled set numbers, so a set with neither request on record
    is still listed as excluded. Returns ([(set, difference)], [(set, why excluded)])."""
    by = {s: {} for s in sets}
    for r in rows:
        if r["role"] == role and r["state"] in (a, b):
            by.setdefault(r["set"], {})[r["state"]] = r
    diffs, excluded = [], []
    for s in sorted(by):
        why = []
        for st in (a, b):
            r = by[s].get(st)
            if r is None:
                why.append("%s missing" % STATE_LABEL[st])
            elif not r["ok"]:
                why.append("%s not valid (%s)" % (STATE_LABEL[st], r["why"]))
            elif r[key] is None:
                why.append("%s has no timing" % STATE_LABEL[st])
        if why:
            excluded.append((s, "; ".join(why)))
        else:
            diffs.append((s, by[s][a][key] - by[s][b][key]))
    return diffs, excluded


def model_name(gm, role):
    return ((gm.get("models") or {}).get(ROLES[role]) or {}).get("name") or ROLES[role]


def note_for(gm, roles):
    """The note under the table and the charts: only the models in the results, and the prefix."""
    return "Model: %s. %s" % (", ".join(model_name(gm, r) for r in roles), PREFIX_NOTE)


def fmt(x, nd=2):
    return "n/a" if x is None else "%.*f" % (nd, x)


def report(folder, out, threshold, gm):
    tp = threshold_problem(threshold)
    if tp:
        raise SystemExit("refusing the report: " + tp)
    rows = load_requests(folder, threshold)
    sched, why_not, gaps = load_sets(folder)
    unsent = unsent_repeats(rows, sched, why_not)
    cs = cells(rows)
    roles = [r for r in ROLE_ORDER if any(k[0] == r for k in cs) or any(u["role"] == r for u in unsent)]
    rep_label = STATE_LABEL["repeat"]
    L = ["Hit threshold: a %s is a valid hit when at least %g percent of its own prompt tokens were read from the "
         "cache (fixed before the run)." % (rep_label, threshold), ""]
    L += ["| Model | State | Requests | Valid | First token s (median, quartiles) | Total s (median) | "
          "Output tokens/s (median) | Thinking tokens (median) | $ per request (mean of valid) |", "|---|---|---|---|---|---|---|---|---|"]
    for (role, state), c in cs.items():
        q = med(c, "ftt")
        L.append("| %s | %s | %d | %d | %s | %s | %s | %s | %s |" % (
            model_name(gm, role), STATE_LABEL[state], c["n"], c["ok"],
            "n/a" if q[1] is None else "%.2f (%.2f to %.2f)" % (q[1], q[0], q[2]), fmt(med(c, "wall")[1]),
            fmt(med(c, "tps")[1], 1), fmt(med(c, "thoughts")[1], 0),
            "%.4f" % statistics.mean(r["cost"] for r in c["rows"]) if c["rows"] else "n/a"))
    L += ["", "Total spent: $%.4f over %d requests." % (sum(r["cost"] for r in rows), len(rows))]
    # hit rate per set and overall
    L += ["", "Hit rate: whether each %s read its prefix from the cache." % rep_label, "",
          "| Model | Set | Claim of the %s | Cached share | Valid hit |" % rep_label, "|---|---|---|---|---|"]
    all_rep = [r for r in rows if r["state"] == "repeat"]
    hit_rows = [(r["role"], r["set"], r["claim"], "n/a" if r["share"] is None else "%.1f percent" % (100 * r["share"]),
                 "yes" if r["ok"] else "no") for r in all_rep]
    hit_rows += [(u["role"], u["set"], u["claim"], "not sent", "no") for u in unsent]
    for role, s, claim, share, hit in sorted(hit_rows, key=lambda x: (ROLE_ORDER.index(x[0]), x[1])):
        L.append("| %s | %d | %s | %s | %s |" % (model_name(gm, role), s, claim, share, hit))
    L.append("")

    def n_rep(role=None):
        # every scheduled repeat counts in the denominator, sent or not
        return (sum(1 for r in all_rep if role in (None, r["role"])) + sum(1 for u in unsent if role in (None, u["role"])))
    for role in roles:
        L.append("Hit rate, %s: %d of %d repeat requests were valid hits." % (
            model_name(gm, role), sum(1 for r in all_rep if r["role"] == role and r["ok"]), n_rep(role)))
    L.append("Hit rate, overall: %d of %d repeat requests were valid hits." % (sum(1 for r in all_rep if r["ok"]), n_rep()))
    missed = [r for r in all_rep if not r["ok"]]
    L += ["", "Missed repeat requests (left out of the medians and the pairs, shown here): %d." % len(missed)]
    L += ["- %s: cached share %s, first token %s s, total %s s; %s" % (
        r["tag"], "n/a" if r["share"] is None else "%.1f percent" % (100 * r["share"]), fmt(r["ftt"]), fmt(r["wall"]), r["why"])
        for r in missed]
    L += ["", "Repeat requests not sent or not on record (counted above as not valid hits): %d." % len(unsent)]
    L += ["- %s: %s" % (u["tag"], u["why"]) for u in unsent]
    # paired differences
    L += ["", "Paired differences, per set, valid pairs only (negative = the first-named was faster):", "",
          "| Model | Pair | First token s, median difference | Sets where the first-named was faster | "
          "Total s, median difference |", "|---|---|---|---|---|"]
    pairs = (("repeat", "first", "%s minus first request" % rep_label),
             ("first", "control", "first request minus second first request (noise floor)"))
    excl_lines, readings = [], []
    for role in roles:
        res = {}
        role_sets = sorted(s for (r_, s) in sched if r_ == role)
        for a_, b_, label in pairs:
            d1, ex = paired(rows, role, a_, b_, "ftt", role_sets)
            d2, _ = paired(rows, role, a_, b_, "wall", role_sets)
            res[a_] = [d for _, d in d1]
            L.append("| %s | %s | %s | %d of %d | %s |" % (
                model_name(gm, role), label, "n/a" if not d1 else "%+.2f" % statistics.median(res[a_]),
                sum(1 for x in res[a_] if x < 0), len(d1), "n/a" if not d2 else "%+.2f" % statistics.median([d for _, d in d2])))
            excl_lines += ["- %s, %s, set %d: %s" % (model_name(gm, role), label, s, why) for s, why in ex]
        hits = sum(1 for r in all_rep if r["role"] == role and r["ok"])
        word, faster, n_pairs = reading(hits, res["repeat"])
        nf = sum(1 for x in res["first"] if x < 0)
        readings.append("| %s | %s (repeat faster in %d of %d valid pairs) | %d of %d | first faster in %d of %d valid pairs |" % (
            model_name(gm, role), word, faster, n_pairs, hits, n_rep(role), nf, len(res["first"])))
    L += ["", "Excluded pairs: %d." % len(excl_lines)] + excl_lines
    L += ["", "Reading rule (fixed before the run). Headline: %s against first request. Fewer than %d valid hits "
          "of the 10 repeat requests: inconclusive. Otherwise seen when the repeat was faster in at least %d valid pairs, "
          "with at least %d valid pairs; else not seen. First request against second first request is a noise floor: two "
          "requests of the same state, so a count far from half shows noise, load or the network, not the cache."
          % (rep_label, MIN_HITS, MIN_FASTER, MIN_PAIRS), "",
          "| Model | Headline: %s against first request | Valid hits | Noise floor: first request against second first "
          "request |" % rep_label, "|---|---|---|---|"] + readings
    # negative control, as cache_timing.py
    L += ["", "Negative control: output tokens per second should not depend on the state, since a cache read skips reading "
          "the prompt and not generating tokens. Flagged only when the largest gap between the state medians is both more "
          "than %d percent and larger than the widest interquartile range inside a state." % round(100 * NC_LIMIT), "",
          "| Model | Tokens/s: %s | Largest relative difference | " % ", ".join(STATE_LABEL[s] for s in STATES) +
          "Widest within-state spread (interquartile range) | Flag |", "|---|---|---|---|---|"]
    for role in roles:
        by = {st: [r["tps"] for r in cs[(role, st)]["rows"] if r["tps"] is not None] for st in STATES if (role, st) in cs}
        rel, flag, iqr = ct.negative_control(by, NC_LIMIT)
        if rel is not None:
            L.append("| %s | %s | %.1f percent | %.1f tokens/s | %s |" % (
                model_name(gm, role), ", ".join("%.1f" % statistics.median(by[st]) if by.get(st) else "n/a" for st in STATES),
                100 * rel, iqr, "SOMETHING OTHER THAN THE CACHE VARIES" if flag else "none"))
    if gaps:
        L += ["", "Longest wait between a first request ending and its %s starting: %.1f s." % (rep_label, max(gaps))]
    bad = [r for r in rows if r["state"] != "repeat" and not r["ok"]]
    L += ["", "First and second first requests that failed their state check (left out of the medians): %d of %d."
          % (len(bad), len(rows) - len(all_rep))]
    L += ["- %s: cached share %s, first token %s s, total %s s; %s" % (
        r["tag"], "n/a" if r["share"] is None else "%.1f percent" % (100 * r["share"]), fmt(r["ftt"]), fmt(r["wall"]), r["why"])
        for r in bad]
    levels = sorted({r["level"] for r in rows if r["level"]})
    L += ["", note_for(gm, roles) + " Thinking level: %s; time to first token includes that thinking." % (", ".join(levels) or "n/a"),
          "", MAPPING_NOTE]
    text = "\n".join(L) + "\n"
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, TABLE_NAME), "w", encoding="utf-8") as f:
        f.write(text)
    n_sets = len({(r["role"], r["set"]) for r in rows})
    for key, title, xlabel, fname, nd in (
            ("ftt", "Time to first token, by request kind", "Seconds to the first token (median)", "gemini-cache-timing-first-token.svg", 2),
            ("wall", "Total time, by request kind", "Seconds per request (median)", "gemini-cache-timing-wall.svg", 2),
            ("tps", "Output tokens per second, by request kind", "Output tokens per second after the first token (median)", "gemini-cache-timing-tps.svg", 1)):
        with open(os.path.join(out, fname), "w", encoding="utf-8") as f:
            f.write(states_chart(cs, roles, gm, key, title, xlabel, nd, n_sets))
    print(text)
    return text


def states_chart(cs, roles, gm, key, title, xlabel, nd, n_sets):
    """Bars per state, one group per model, drawn with the build_results_table.py helpers as cache_timing.states_chart."""
    grp = 3 * 16 + 14
    top, bottom = 94, 94 + grp * max(len(roles), 1)
    vals = [med(c, key)[1] for c in cs.values() if c["rows"] and med(c, key)[1] is not None] or [1.0]
    grid, X = brt.axis(brt.nice_max(max(vals) * 1.15), top, bottom, xlabel)
    legend = "".join('<rect x="%d" y="64" width="12" height="12" fill="%s"/><text x="%d" y="75" font-size="12">%s</text>'
                     % (brt.LEFT + i * LEGEND_STEP, STATE_COLOR[s], brt.LEFT + i * LEGEND_STEP + 18, brt.esc(STATE_LABEL[s]))
                     for i, s in enumerate(STATES))
    body = [grid]
    for i, role in enumerate(roles):
        y = top + i * grp
        body.append(brt.label_at(y + 28, model_name(gm, role)))
        for j, state in enumerate(STATES):
            c = cs.get((role, state))
            v = med(c, key)[1] if c and c["rows"] else None
            if v is None:
                continue
            yy = y + 4 + j * 17
            body.append('<rect x="%d" y="%d" width="%.1f" height="14" rx="2" fill="%s"/>' % (brt.LEFT, yy, X(v) - brt.LEFT, STATE_COLOR[state]))
            body.append('<text x="%.1f" y="%d" font-size="11" font-weight="600">%.*f</text>' % (X(v) + 5, yy + 11, nd, v))
    saved = brt.NOTE
    brt.NOTE = note_for(gm, roles)
    try:
        return brt.frame(title, "%d sets, one request at a time, a different question for each request kind; valid requests only."
                         % n_sets, bottom + 70, "\n".join(body) + "\n", legend)
    finally:
        brt.NOTE = saved


# ---------------------------------------------------------------- selftest (offline: fake transport, fake clock)

FAKE_GM = {"models": {"gemini-3.8-flash": {"id": "gemini-selftest", "name": "Gemini 3.8 Flash"}},
           "prices": {"gemini-3.8-flash": gb.FAKE_PRICES}}
FAKE_PROMPT = 150_000
FAKE_FOLLOWUP_EXTRA = 200                      # a repeat's prompt is longer than its first request's by the reply and question
USAGE_FIRST = {"promptTokenCount": FAKE_PROMPT, "cachedContentTokenCount": 0, "candidatesTokenCount": 120,
               "thoughtsTokenCount": 40}
USAGE_CONTROL = {"promptTokenCount": FAKE_PROMPT, "candidatesTokenCount": 120, "thoughtsTokenCount": 40}   # the cached field left out
USAGE_HIT = {"promptTokenCount": FAKE_PROMPT + FAKE_FOLLOWUP_EXTRA, "cachedContentTokenCount": 140_000,
             "candidatesTokenCount": 120, "thoughtsTokenCount": 40}
USAGE_MISS = dict(USAGE_HIT, cachedContentTokenCount=0)


def _reply_parts_for(s, st):
    """The parts the fake server's reply to (set s, state st) assembles into: a signed text part, then plain text. Each
    set and state gets its own signature, so a check can tell whose reply a follow-up turn carries."""
    return [{"text": "Reply to the %s of set %d: I would approve." % (st, s), "thoughtSignature": "SIG-%s-%d" % (st, s)},
            {"text": " The estimate is within policy."}]


def _fake_stream(wait_chunks, usage, parts=None):
    """wait_chunks empty chunks before the first text (one second each on the fake clock), then the reply's parts, the
    last chunk carrying finishReason and usage."""
    parts = parts or [{"text": "I would approve: the other driver was cited."}, {"text": " The estimate is within policy."}]
    lines = [gb._data({"candidates": [{"content": {"role": "model", "parts": []}}]}) for _ in range(wait_chunks)]
    lines += [gb._chunk([p]) for p in parts[:-1]]
    lines.append(gb._chunk([parts[-1]], finish="STOP", usage=usage, modelVersion="gemini-selftest"))
    return lines


def _fake_args(out, reps, smoke=False, threshold=75.0):
    return argparse.Namespace(out=out, ceiling_usd=100.0, reps=reps, smoke=smoke, threshold=threshold, only="flash",
                              thinking_level=DEFAULT_THINKING_LEVEL)


def _fake_run(project, token, redact_on, replies_for, reps, threshold=75.0):
    """A whole fake live run into a fresh temporary --out folder, then the report from it. replies_for(set, state) gives
    the reply function for each request in schedule order. Returns what the checks need."""
    out = tempfile.mkdtemp(prefix="gemini-cache-timing-selftest-")
    clk = gb._Clock()
    expected = [(s["set"], st) for s in schedule(reps, mb.EVAL_CLAIMS) for st in s["order"]]
    srv = gb._FakeVertex([], clk)
    pos, sent_as = [0], []

    def dispatch(path, hdrs):
        # a repeat that was not sent is skipped: the request on the wire is then a first or second first request, which
        # has one user turn only
        n_turns = len(srv.sent[-1]["body"]["contents"])
        while expected[pos[0]][1] == "repeat" and n_turns == 1:
            pos[0] += 1
        s, st = expected[pos[0]]
        pos[0] += 1
        sent_as.append((s, st))
        return replies_for(s, st)(path, hdrs)
    srv.replies = [dispatch] * len(expected)
    transport = {"conn_factory": srv.factory, "clock": clk, "sleep": lambda s: None, "redact_on": redact_on}
    env = {"token": token, "project": project, "location": "global"}
    buf, raised, text = io.StringIO(), "", ""
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            live(_fake_args(out, reps, threshold=threshold), FAKE_GM, mb.EVAL_CLAIMS, env=env, transport=transport)
            text = report(out, out, threshold, FAKE_GM)
        except (RuntimeError, SystemExit) as e:
            raised = str(e)
        except Exception as e:   # a crash is a failed check, not the end of the selftest
            raised = "%s: %s" % (type(e).__name__, e)
        finally:
            gb.LIVE["armed"] = False
    files = {}
    for name in sorted(os.listdir(out)):
        with open(os.path.join(out, name), encoding="utf-8") as f:
            files[name] = f.read()
    blob = "\n".join(files.values()) + "\n" + buf.getvalue() + "\n" + raised
    leaked = any(s in blob for s in (project, token, "123456789012"))
    return {"out": out, "files": files, "sent": srv.sent, "sent_as": sent_as, "printed": buf.getvalue(), "raised": raised,
            "report": text, "leaked": leaked}


def _ok_reply(st, miss_set=None, s=None):
    if st == "repeat":
        usage, wait = (USAGE_MISS, 3) if s == miss_set else (USAGE_HIT, 0)
    else:
        usage, wait = (USAGE_FIRST if st == "first" else USAGE_CONTROL), 3
    parts = _reply_parts_for(s or 0, st)
    return lambda p, h: (200, _fake_stream(wait, usage, parts))


def _echo_403(path, hdrs):
    return 403, json.dumps({"error": {"code": 403, "message": "Permission denied on https://%s%s for consumer "
                                      "projects/123456789012; credential %s" % (gb.GLOBAL_HOST, path, hdrs.get("authorization"))}})


def _outside_mapping_note(text):
    return FORBIDDEN_STATE_WORDS.findall(text.replace(MAPPING_NOTE, ""))


def selftest(inject_fault=False):
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = round(got, 6) == round(want, 6) if isinstance(want, float) and got is not None else got == want
        ok &= good

        def short(x):
            s = repr(x)
            return s if len(s) <= 120 else "%s... (%d chars)" % (s[:100], len(s))
        print("%-4s %-66s got %s want %s" % ("PASS" if good else "FAIL", name, short(got), short(want)))

    claims = mb.EVAL_CLAIMS
    ids = sorted(c["id"] for c in claims)
    by_id_c = {c["id"]: c for c in claims}

    # schedule
    sched = schedule(10, claims)
    check("schedule: 10 sets, 30 requests", (len(sched), sum(len(s["order"]) for s in sched)), (10, 30))
    check("schedule: odd sets first, repeat, second first", {tuple(s["order"]) for s in sched if s["set"] % 2 == 1},
          {("first", "repeat", "control")})
    check("schedule: even sets second first, first, repeat", {tuple(s["order"]) for s in sched if s["set"] % 2 == 0},
          {("control", "first", "repeat")})
    check("schedule: repeat straight after first in every set",
          all(s["order"].index("repeat") == s["order"].index("first") + 1 for s in sched), True)
    check("schedule: control after the repeat on odd sets, before the first on even",
          all((s["order"].index("control") > s["order"].index("repeat")) if s["set"] % 2 else
              (s["order"].index("control") < s["order"].index("first")) for s in sched), True)
    check("schedule: three different claims in every set", all(len(set(s["claims"].values())) == 3 for s in sched), True)
    check("schedule: every state sees every claim once over 10 sets",
          all(sorted(s["claims"][st] for s in sched) == ids for st in STATES), True)
    check("schedule: argon rotates claims too",
          all(sorted(s["claims"][st] for s in schedule(10, claims, "argon")) == ids for st in STATES), True)
    n1, n2 = fresh_nonces()
    check("nonces: the control's differs from the first request's", n1 != n2, True)
    check("state names: first, repeat (follow-up turn), second first request",
          (sorted(STATE_LABEL.values()), _outside_mapping_note(" ".join(STATE_LABEL.values()))),
          (["first request", "repeat request (follow-up turn)", "second first request"], []))
    check("mapping note: says the repeat is a follow-up turn, not comparable with Anthropic",
          ("The repeat request is a follow-up turn: the first request, its reply and a new question" in MAPPING_NOTE,
           "it is not comparable with the Anthropic warm cache." in MAPPING_NOTE), (True, True))

    # request body
    ledger = ct.load_ledger()
    b1 = build_body(11, claims[0], ledger)
    b2 = build_body(11, claims[3], ledger)
    b3 = build_body(12, claims[6], ledger)
    ct_body = ct.build_body("m", "long", 11, claims[0], NO_BREAKPOINT, ledger)
    check("body: system text is cache_timing's long prefix, two parts",
          [p["text"] for p in b1["systemInstruction"]["parts"]], [blk["text"] for blk in ct_body["system"]])
    check("body: nonce line at the head, ledger second",
          (b1["systemInstruction"]["parts"][0]["text"].startswith("[set 11]\n\n" + mb.SYSTEM_PROMPT[:20]),
           b1["systemInstruction"]["parts"][1]["text"].startswith("Historical claims ledger")), (True, True))
    check("body: the question is the only user content",
          b1["contents"], [{"role": "user", "parts": [{"text": ct_body["messages"][0]["content"]}]}])
    check("body: twelve functionDeclarations, calling mode NONE",
          (len(b1["tools"][0]["functionDeclarations"]), b1["toolConfig"]), (12, {"functionCallingConfig": {"mode": "NONE"}}))
    check("body: output limit and thinking level LOW", (b1["generationConfig"]["maxOutputTokens"],
                                                        b1["generationConfig"]["thinkingConfig"]),
          (256 + gb.WORST_CASE_EXTRA_THOUGHT_TOKENS, {"thinkingLevel": "LOW"}))
    check("body: --thinking-level is sent as given", build_body(1, claims[0], "", "medium")["generationConfig"]["thinkingConfig"],
          {"thinkingLevel": "MEDIUM"})
    check("body: second first request has another nonce line", b1["systemInstruction"] == b3["systemInstruction"], False)
    check("body: no model, stream or cache field", ("model" in b1, "stream" in b1, "cachedContent" in b1), (False, False, False))

    # the follow-up turn, built from a made-up first reply whose first part carries a thought signature
    b1_before = json.dumps(b1, sort_keys=True)
    fake_parts = [{"text": "Approve.", "thoughtSignature": "SIG-A"}, {"text": " Within policy."}]
    fu = followup_body(b1, {"candidates": [{"content": {"role": "model", "parts": fake_parts}}]},
                       repeat_question_parts(11, claims[3], ledger))
    check("follow-up: contents roles user, model, user", [c["role"] for c in fu["contents"]], ["user", "model", "user"])
    check("follow-up: first user turn is the first request's, unchanged", fu["contents"][0], b1["contents"][0])
    check("follow-up: model turn is the reply's parts exactly, signature kept",
          (fu["contents"][1]["parts"], fu["contents"][1]["parts"][0].get("thoughtSignature")), (fake_parts, "SIG-A"))
    check("follow-up: new user turn is the repeat claim's question", fu["contents"][2]["parts"], b2["contents"][0]["parts"])
    check("follow-up: system instruction, tools, tool config, generation config byte-identical to the first request's",
          [json.dumps(fu[k], sort_keys=True) == json.dumps(b1[k], sort_keys=True)
           for k in ("systemInstruction", "tools", "toolConfig", "generationConfig")], [True] * 4)
    check("follow-up: no other top-level field", sorted(fu), sorted(b1))
    check("follow-up: the first request's body is not changed", json.dumps(b1, sort_keys=True) == b1_before, True)
    for name, resp in (("no candidates", {}), ("empty parts", {"candidates": [{"content": {"role": "model", "parts": []}}]})):
        try:
            followup_body(b1, resp, b2["contents"][0]["parts"])
            check("follow-up: refused when the reply has %s" % name, "built", "refused")
        except ValueError:
            check("follow-up: refused when the reply has %s" % name, "refused", "refused")

    # state checks on made-up usage blocks
    def u(prompt, cached=None):
        d = {"promptTokenCount": prompt, "candidatesTokenCount": 100}
        if cached is not None:
            d["cachedContentTokenCount"] = cached
        return d
    check("state: repeat at 76 percent with T=75 is a hit", check_state("repeat", u(10000, 7600), 75)[0], True)
    check("state: repeat at 74 percent with T=75 is a miss", check_state("repeat", u(10000, 7400), 75)[0], False)
    check("state: repeat at exactly 75 percent with T=75 is a hit", check_state("repeat", u(10000, 7500), 75)[0], True)
    check("state: repeat with cachedContentTokenCount 0 is a miss", check_state("repeat", u(10000, 0), 75)[0], False)
    check("state: repeat without the cached field is a miss", check_state("repeat", u(10000), 75)[0], False)
    check("state: first request without the cached field is valid", check_state("first", u(10000), 75)[0], True)
    check("state: first request with cached 0 is valid", check_state("first", u(10000, 0), 75)[0], True)
    check("state: first request with a nonzero cached count is not valid", check_state("first", u(10000, 4096), 75)[0], False)
    check("state: second first request with a nonzero cached count is not valid", check_state("control", u(10000, 1), 75)[0], False)
    check("state: no threshold -> repeat not judged, share given", check_state("repeat", u(10000, 9000), None)[::2], (None, 0.9))
    check("state: empty usage is not valid", check_state("first", {}, 75)[0], False)
    check("threshold: none is refused, 49 refused, 75 accepted",
          (threshold_problem(None) is not None, threshold_problem(49) is not None, threshold_problem(75)), (True, True, None))

    # the reading rule on made-up pairs
    check("reading: 7 of 10 hits is inconclusive even with 10 faster", reading(7, [-1.0] * 10)[0], "inconclusive")
    check("reading: 8 hits, 8 of 8 valid pairs faster is seen", reading(8, [-1.0] * 8)[0], "seen")
    check("reading: 8 hits, 7 of 8 valid pairs faster is not seen", reading(8, [-1.0] * 7 + [0.5])[0], "not seen")
    check("reading: 10 hits, 7 valid pairs all faster is not seen", reading(10, [-1.0] * 7)[0], "not seen")
    check("reading: 10 hits, 8 of 10 faster is seen", reading(10, [-1.0] * 8 + [1.0, 1.0])[:3], ("seen", 8, 10))
    check("reading: a tie is not faster", reading(10, [-1.0] * 7 + [0.0] * 3)[:2], ("not seen", 7))

    # reused numbers from cache_timing.py
    check("tokens per second (cache_timing)", round(ct.tokens_per_second(101, 5.0, 1.0), 2), 25.0)
    check("negative control: wide scatter not flagged, tight gap flagged",
          (ct.negative_control({"first": [20, 30, 40, 50], "repeat": [18, 28, 36, 46]}, NC_LIMIT)[1],
           ct.negative_control({"first": [40, 41, 39, 40], "repeat": [30, 31, 29, 30]}, NC_LIMIT)[1]), (False, True))

    # estimate, hand-computed at the fake prices (in 1, out 4 per million): 30 x 148,000 x 1, plus 10 follow-up turns of
    # 1,000 tokens x 1, plus 30 x 49,408 x 4
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        est = estimate(FAKE_GM, "flash", 10)
    check("estimate: upper bound at the fake prices, with the follow-up growth", est,
          (30 * 148000 * 1.0 + 10 * 1000 * 1.0 + 30 * (256 + 2 * 24576) * 4.0) / 1e6)
    check("estimate: names the follow-up growth", "plus 1000 tokens for each of the 10 follow-up turns" in buf.getvalue(), True)

    # readiness refusals on the live path
    unknown = {"models": {"gemini-3.8-flash": {"id": "UNKNOWN: fill in"}}, "prices": {"gemini-3.8-flash": gb.FAKE_PRICES}}
    nullp = {"models": {"gemini-3.8-flash": {"id": "gemini-3.8-flash"}},
             "prices": {"gemini-3.8-flash": {"in": None, "out": None, "cached_in": None, "source": "UNREAD"}}}
    tmp0 = tempfile.mkdtemp(prefix="gemini-cache-timing-selftest-")
    for name, gm_, env_, args, word in (
            ("live refuses an UNKNOWN model id", unknown, "global", _fake_args(tmp0, 1), "UNKNOWN"),
            ("live refuses a null price", nullp, "global", _fake_args(tmp0, 1), "null"),
            ("live refuses a location the prices are not for", FAKE_GM, "us-central1", _fake_args(tmp0, 1), "location"),
            ("live refuses a missing threshold", FAKE_GM, "global", _fake_args(tmp0, 1, threshold=None), "--threshold"),
            ("live refuses a threshold below 50", FAKE_GM, "global", _fake_args(tmp0, 1, threshold=40.0), "between")):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                live(args, gm_, claims, env={"token": "t", "project": "p", "location": env_},
                     transport={"conn_factory": gb._no_network})
            check(name, "ran", "refused")
        except SystemExit as e:
            check(name, "refused" if word in str(e) else "refused for another reason: %s" % e, "refused")
        except RuntimeError as e:
            check(name, "ran until: %s" % e, "refused")
        finally:
            gb.LIVE["armed"] = False
    try:
        report(tmp0, tmp0, None, FAKE_GM)
        check("report refuses a missing threshold", "ran", "refused")
    except SystemExit:
        check("report refuses a missing threshold", "refused", "refused")
    try:
        gb.stream_gemini("https://%s/x" % gb.GLOBAL_HOST, {}, {})
        check("network refused while not armed", "ran", "refused")
    except RuntimeError as e:
        check("network refused while not armed", "refused" if "not armed" in str(e) else str(e), "refused")

    # dry run: reads no credential, shows placeholders and the alternation
    real_load_env = gb.load_env

    def _forbidden():
        raise AssertionError("dry run read the credentials")
    gb.load_env = _forbidden
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            dry_run(gb.load_gemini_models(), "flash", 2, claims)
    finally:
        gb.load_env = real_load_env
    dry = buf.getvalue()
    check("dry run: project and token as placeholders", ("/projects/<PROJECT>/" in dry, "Bearer <REDACTED>" in dry), (True, True))
    check("dry run: both orders printed", ("first request (%s) -> repeat request (follow-up turn)" % sched[0]["claims"]["first"]
                                           in dry, "set  2  second first request" in dry), (True, True))
    check("dry run: the repeat is shown as a follow-up turn with roles and size",
          ("repeat request (follow-up turn) of set 1: the first request's body, then its reply as a model turn" in dry,
           "contents roles user, model, user" in dry,
           bool(re.search(r"\(the reply shown as <first reply>", dry)), bool(re.search(r"  body bytes \d+ \(the reply", dry))),
          (True, True, True, True))
    check("dry run: model turn is the placeholder", '  model turn {"role": "model", "parts": [{"text": "<first reply>"}]}' in dry,
          True)
    check("dry run: repeat keeps the first request's config", "the same bytes as the first request's: True" in dry, True)
    check("dry run: no other state names", _outside_mapping_note(dry), [])

    # a whole fake-transport run of 2 sets, then the report from its folder; set 2's repeat request misses
    res = _fake_run("selftest-project-x", "selftest-token-x", True, lambda s, st: _ok_reply(st, miss_set=2, s=s), 2)
    reqs = [json.loads(x) for x in res["files"].get("requests.jsonl", "").splitlines() if x.strip()]
    sets = [json.loads(x) for x in res["files"].get("sets.jsonl", "").splitlines() if x.strip()]
    check("run: no exception", res["raised"], "")
    check("run: six requests in schedule order, tags carry set, state, claim",
          [r["tag"].split()[1:3] for r in reqs],
          [["set1", "first"], ["set1", "repeat"], ["set1", "control"], ["set2", "control"], ["set2", "first"], ["set2", "repeat"]])
    check("run: tags carry the scheduled claims",
          [r["tag"].split()[3] for r in reqs], [s["claims"][st] for s in schedule(2, claims) for st in s["order"]])
    check("run: records carry cached and prompt tokens; the repeat's prompt is the longer one",
          [(r["cached_tokens"], r["prompt_tokens"]) for r in reqs][:2],
          [(0, FAKE_PROMPT), (140000, FAKE_PROMPT + FAKE_FOLLOWUP_EXTRA)])
    sysi = [x["body"]["systemInstruction"] for x in res["sent"]]
    check("run: repeat sent with its first request's prefix, control with another",
          (sysi[0] == sysi[1], sysi[2] != sysi[0], sysi[4] == sysi[5], sysi[3] != sysi[4], sysi[0] != sysi[4]),
          (True, True, True, True, True))
    sent = {sa: x["body"] for sa, x in zip(res["sent_as"], res["sent"])}
    check("run: the fake server saw the six scheduled requests", sorted(sent), sorted((s["set"], st) for s in schedule(2, claims)
                                                                                       for st in s["order"]))
    for s_ in (1, 2):
        rb, fb = sent.get((s_, "repeat")) or {"contents": []}, sent.get((s_, "first")) or {}
        check("run: set %d repeat contents are user, model, user" % s_, [c["role"] for c in rb["contents"]],
              ["user", "model", "user"])
        check("run: set %d repeat carries the first reply's parts exactly, signature kept" % s_,
              rb["contents"][1]["parts"] if len(rb["contents"]) > 1 else None, _reply_parts_for(s_, "first"))
        check("run: set %d repeat's system instruction, tools, tool config, generation config are the first's" % s_,
              [rb.get(k) == fb.get(k) for k in ("systemInstruction", "tools", "toolConfig", "generationConfig")], [True] * 4)
        check("run: set %d repeat's first user turn is the first request's, last is its own question" % s_,
              (rb["contents"][:1] == fb.get("contents"),
               rb["contents"][-1:] == [{"role": "user", "parts": repeat_question_parts(0, by_id_c[schedule(2, claims)[s_ - 1]
                                                                                              ["claims"]["repeat"]], ledger)}]),
              (True, True))
    check("run: set 2 (control sent before the first) repeat carries the first's reply, not the control's",
          [p.get("thoughtSignature") for p in (sent.get((2, "repeat")) or {"contents": [{}, {"parts": []}]})["contents"][1]["parts"]],
          ["SIG-first-2", None])
    check("run: cost of a first request (gemini_cost at the fake prices)", reqs[0]["notebook_cost"], 0.15064)
    check("run: cost of a hit (its own, longer prompt)", reqs[1]["notebook_cost"], 0.02484)
    check("run: sets.jsonl has two sets and two repeat gaps",
          (len([s for s in sets if "order" in s]), [s.get("repeat_gap_s") is not None for s in sets if "repeat_gap_s" in s]),
          (2, [True, True]))
    rows = load_requests(res["out"], 75.0)
    d, ex = paired(rows, "flash", "repeat", "first")
    check("pairs: headline counts the valid pair only, set 2 excluded", ([s for s, _ in d], [s for s, _ in ex], d[0][1]),
          ([1], [2], -3.0))
    d, ex = paired(rows, "flash", "first", "control")
    check("pairs: noise floor has two valid pairs, first not faster", ([s for s, _ in d], sum(1 for _, x in d if x < 0)), ([1, 2], 0))
    rep = res["report"]
    check("report: hit rate overall", "Hit rate, overall: 1 of 2 repeat requests were valid hits." in rep, True)
    check("report: reading is inconclusive with 1 hit", "| Gemini 3.8 Flash | inconclusive (repeat faster in 1 of 1 valid pairs) | 1 of 2 |" in rep, True)
    check("report: the missed repeat is listed by name", "- flash set2 repeat %s: cached share 0.0 percent" % schedule(2, claims)[1]["claims"]["repeat"] in rep, True)
    check("report: excluded pair printed", "set 2: repeat request (follow-up turn) not valid" in rep, True)
    check("report: noise floor labelled as such", "first request minus second first request (noise floor)" in rep, True)
    check("report: state rows with valid counts", ("| Gemini 3.8 Flash | repeat request (follow-up turn) | 2 | 1 |" in rep,
                                                   "| Gemini 3.8 Flash | second first request | 2 | 2 |" in rep), (True, True))
    check("report: headline names the follow-up turn", "repeat request (follow-up turn) minus first request" in rep, True)
    check("report: nothing marked not sent when every repeat went out",
          "Repeat requests not sent or not on record (counted above as not valid hits): 0." in rep, True)
    check("report: negative control not flagged on equal speeds", "| none |" in rep, True)
    check("report: the mapping note appears once", rep.count(MAPPING_NOTE), 1)
    check("report: no other state names in the table", _outside_mapping_note(rep), [])
    svgs = {k: v for k, v in res["files"].items() if k.endswith(".svg")}
    check("charts: three SVGs", sorted(svgs), ["gemini-cache-timing-first-token.svg", "gemini-cache-timing-tps.svg",
                                               "gemini-cache-timing-wall.svg"])
    check("charts: note names the model and prefix only",
          all("Model: Gemini 3.8 Flash. Prefix:" in v and "Argon" not in v and "Opus" not in v for v in svgs.values()), True)
    check("charts: no other state names", [w for v in svgs.values() for w in _outside_mapping_note(v)], [])
    check("charts: legend names the follow-up turn",
          all(">repeat request (follow-up turn)</text>" in v for v in svgs.values()), True)

    # a failed first request in an even set (control first): the repeat is not sent, counted as not a valid hit, no crash
    def fail_first_2(s, st):
        return _echo_403 if (s, st) == (2, "first") else _ok_reply(st, s=s)
    ff = _fake_run("selftest-project-y", "selftest-token-y", True, fail_first_2, 2)
    ffr = ff["report"]
    check("failed first: no exception", ff["raised"], "")
    check("failed first: set 2's repeat not sent, the others were",
          ff["sent_as"], [(1, "first"), (1, "repeat"), (1, "control"), (2, "control"), (2, "first")])
    check("failed first: printed as not sent", "NOT SENT flash set2 repeat" in ff["printed"], True)
    check("failed first: noted in sets.jsonl",
          '"repeat_not_sent": "its first request failed"' in ff["files"].get("sets.jsonl", ""), True)
    check("failed first: counted in the hit rate as not a valid hit",
          ("Hit rate, overall: 1 of 2 repeat requests were valid hits." in ffr,
           "| Gemini 3.8 Flash | 2 | %s | not sent | no |" % schedule(2, claims)[1]["claims"]["repeat"] in ffr), (True, True))
    check("failed first: listed as not sent with the reason",
          ("Repeat requests not sent or not on record (counted above as not valid hits): 1." in ffr,
           "- flash set2 repeat %s: not sent: its first request failed" % schedule(2, claims)[1]["claims"]["repeat"] in ffr),
          (True, True))
    check("failed first: the headline pair of set 2 is excluded",
          "set 2: repeat request (follow-up turn) missing; first request not valid (status 403)" in ffr, True)
    check("failed first: reading uses 2 scheduled repeats", "valid pairs) | 1 of 2 |" in ffr, True)
    check("unsent: a scheduled repeat with no record and no note is counted too",
          [u["why"] for u in unsent_repeats([], {("flash", 3): "CLM-X"}, {})],
          ["no record of it (it failed before a status came back)"])

    # the project id and the token never reach a file, a printed line or an exception
    fake_project, fake_token = "fake-vertex-project-123", "fake-token-0123456789abcdef"

    def leak_replies(s, st):
        return _echo_403 if (s, st) == (1, "first") else _ok_reply(st, s=s)
    good = _fake_run(fake_project, fake_token, True, leak_replies, 1)
    greqs = [json.loads(x) for x in good["files"].get("requests.jsonl", "").splitlines() if x.strip()]
    check("redaction: the 403 was recorded, its repeat not sent, the run went on",
          ([r["status"] for r in greqs], "FAILED flash set1 first" in good["printed"], "NOT SENT flash set1 repeat" in good["printed"]),
          ([403, 200], True, True))
    check("redaction: the error was recorded with placeholders", "projects/<PROJECT>" in json.dumps(greqs[0]["error"]), True)
    check("redaction: project, project number and token appear nowhere", good["leaked"], False)
    bad = _fake_run(fake_project, fake_token, False, leak_replies, 1)
    check("redaction: the leak check finds them when redaction is skipped", bad["leaked"], True)
    if inject_fault:
        check("injected fault: redaction skipped, nothing leaks (must FAIL)", bad["leaked"], False)
    print("temporary folders (left for the OS temp cleaner): %s %s %s %s %s" % (tmp0, res["out"], ff["out"], good["out"],
                                                                               bad["out"]))
    print("selftest", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true")
    g.add_argument("--selftest-fault", action="store_true", help="selftest with one wrong expectation added; must exit 1")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--estimate", action="store_true")
    g.add_argument("--live", action="store_true")
    g.add_argument("--report", metavar="DIR")
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--only", choices=ROLE_ORDER, default="flash", help="the model: flash (default) or argon")
    ap.add_argument("--models", default=gb.MODELS_PATH)
    ap.add_argument("--ceiling-usd", type=float, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--threshold", type=float, default=None,
                    help="percent of the prompt tokens a repeat request must read from the cache to count as a hit; no "
                         "default, required by --live (except --smoke) and --report")
    ap.add_argument("--smoke", action="store_true", help="live: one set (set 1) to check the request shape and read the shares")
    ap.add_argument("--thinking-level", type=str.upper, choices=list(gb.THINKING_LEVELS), default=DEFAULT_THINKING_LEVEL)
    ap.add_argument("--show-limit", type=int, default=300, help="dry run: strings longer than this are elided")
    a = ap.parse_args()
    if a.selftest or a.selftest_fault:
        return selftest(inject_fault=a.selftest_fault)
    gm = gb.load_gemini_models(a.models)
    if a.report:
        report(a.report, a.out or a.report, a.threshold, gm)
        return 0
    if a.dry_run:
        dry_run(gm, a.only, a.reps, mb.EVAL_CLAIMS, a.thinking_level, a.show_limit)
        return 0
    if a.estimate:
        estimate(gm, a.only, a.reps)
        return 0
    if a.ceiling_usd is None or not a.out:
        raise SystemExit("--live needs --ceiling-usd and --out")
    live(a, gm, mb.EVAL_CLAIMS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
