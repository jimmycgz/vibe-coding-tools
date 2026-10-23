#!/usr/bin/env python3
"""Gemini benchmark: the claims-adjudication agent loop of model_benchmark.py, run against Google's Vertex AI Gemini REST
API (streamGenerateContent with alt=sse), stdlib only, raw HTTPS.

The task is the same: the ten claims, the twelve tools, the system prompt with a fresh nonce at its head, at most six turns
per claim, the four terminal tools. Only the wire format changes: tools become functionDeclarations, the model's turn holds
functionCall parts, the answers go back as functionResponse parts, and every part the model sent is echoed back unchanged
(thought signatures must stay inside the part they came in).

Cache: Vertex has implicit caching switched on for every project, and only a project administrator can switch it off, so
there is no arm without a cache. Each request's usageMetadata says how much of the prompt was read from the cache
(cachedContentTokenCount); every request record carries that count and the cached share.

usage:
  gemini_benchmark.py --selftest | --selftest-fault
  gemini_benchmark.py --dry-run [--configs gemini-flash-medium] [--claims CLM-001] [--thinking-level LOW]
      prints every first-turn request body; no network, no credential read. The project in the URL is shown as <PROJECT>.
  gemini_benchmark.py --estimate [--configs ...] [--trials N]
      upper-bound cost with nothing read from the cache; no network.
  gemini_benchmark.py --live --ceiling-usd X --out DIR [--configs ...] [--claims ...] [--trials N] [--thinking-level L]
      the paid run. Needs GEMINI_ACCESS_TOKEN and GOOGLE_CLOUD_PROJECT in the environment (GOOGLE_CLOUD_LOCATION optional,
      default global). Writes requests.jsonl and trials.jsonl in DIR in the shape model_benchmark.py writes.

The project id and the access token are read from the environment at send time and never written: the URL is built only for
the request, error text from the server is redacted before it is recorded, printed or raised, and every line written to a
record file is redacted again.
"""
import argparse
import contextlib
import hashlib
import http.client as _httpclient
import io
import json
import os
import re
import ssl
import sys
import tempfile
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_benchmark as mb  # noqa: E402  (claims, tools, system prompt, tool results, _elide)

LIVE = {"armed": False}  # set only by live() after every live-mode check passes

# ---------------------------------------------------------------- settings (each one a named constant on purpose)

MODELS_PATH = os.path.join(HERE, "gemini_models.json")
API_VERSION = "v1"
GLOBAL_HOST = "aiplatform.googleapis.com"
DEFAULT_LOCATION = "global"
STREAM_METHOD = "streamGenerateContent"
STREAM_QUERY = "alt=sse"
PROJECT_PLACEHOLDER = "<PROJECT>"
TOKEN_PLACEHOLDER = "<REDACTED>"
MAX_TURNS = 6                    # as run_loop in model_benchmark.py
MAX_OUTPUT_TOKENS = 4096         # as max_tokens in model_benchmark.loop_body
FUNCTION_CALLING_MODE = "AUTO"
# The thinking docs page writes the field in snake_case (thinking_level); the REST API takes camelCase JSON field names and
# the existing local harness sends thinkingLevel. One constant, so the smoke test can switch it if the API refuses it.
THINKING_LEVEL_KEY = "thinkingLevel"
THINKING_LEVELS = ("LOW", "MEDIUM", "HIGH")   # both models; MINIMAL is a validation error on both (docs read 2026-10-22)
EFFORT_TO_LEVEL = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
# Thought summaries are off by default. Turning them on would add thought text parts to the reply; the benchmark does not
# need them, and whether they change the billed thinking tokens is not known.
INCLUDE_THOUGHTS = False
# The schema casing. Neither the docs notes nor the quotes show how the parameter schema types must be written; Vertex's
# Schema reference lists its Type enum in capitals (STRING, OBJECT), which is what "upper" sends. Not checked against the
# page in this work: the smoke test confirms it. "lower" sends the JSON Schema form the Anthropic tools use.
SCHEMA_TYPE_CASE = "upper"
# A tool result goes back as functionResponse.response, which must be a JSON object. The tool's text is put under this one
# key unchanged, so the model sees the same text the Claude arms see.
FUNCTION_RESPONSE_KEY = "result"
RETRY_STATUSES = (429, 500, 502, 503, 504)
MAX_ATTEMPTS = 5
# Spend guard: tokens are guessed from the body length at 3 characters per token (generous) at the full input price, plus
# the output limit and this many extra thinking tokens at the output price, because the docs read do not say whether
# maxOutputTokens also bounds the thinking tokens.
WORST_CASE_EXTRA_THOUGHT_TOKENS = 24_576
REQUIRE_USAGE = True             # stop the run when a stream carries no usageMetadata: its cost could not be counted
# --estimate: per claim, nothing read from the cache (an upper bound). Output includes the thinking tokens.
EST_INPUT_TOKENS_PER_CLAIM = 45_000
EST_OUTPUT_TOKENS_PER_CLAIM = 4_000
# Implicit cache reading. The GenerateContentResponse reference says promptTokenCount includes the cached tokens "when
# cachedContent is set" (explicit caching). For an implicit cache hit the page does not say. This file ASSUMES the same
# holds for implicit hits; the smoke data decides it, and this constant is the one place to change.
PROMPT_COUNT_INCLUDES_CACHED = True

# ---------------------------------------------------------------- the arms (not in arms.json yet)

CONFIGS = [
    dict(id="gemini-flash-high", label="Gemini 3.8 Flash high", kind="gemini_loop", role="gemini-3.8-flash", effort="high"),
    dict(id="gemini-flash-medium", label="Gemini 3.8 Flash medium", kind="gemini_loop", role="gemini-3.8-flash", effort="medium"),
    dict(id="gemini-flash-low", label="Gemini 3.8 Flash low", kind="gemini_loop", role="gemini-3.8-flash", effort="low"),
    dict(id="gemini-argon-high", label="Gemini 4 Argon high", kind="gemini_loop", role="gemini-4-argon", effort="high"),
    dict(id="gemini-argon-medium", label="Gemini 4 Argon medium", kind="gemini_loop", role="gemini-4-argon", effort="medium"),
    dict(id="gemini-argon-low", label="Gemini 4 Argon low", kind="gemini_loop", role="gemini-4-argon", effort="low"),
]
DEFAULT_CONFIGS = ["gemini-flash-high", "gemini-flash-medium", "gemini-flash-low"]   # Argon runs only when named


def select_configs(spec):
    wanted = [x.strip() for x in spec.split(",") if x.strip()] if spec else DEFAULT_CONFIGS
    unknown = [x for x in wanted if x not in {c["id"] for c in CONFIGS}]
    if unknown:
        raise SystemExit("unknown config id(s): %s; known: %s" % (", ".join(unknown), ", ".join(c["id"] for c in CONFIGS)))
    return [c for c in CONFIGS if c["id"] in wanted]


def load_gemini_models(path=MODELS_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def readiness(cfgs, gm, location=None):
    """The reasons the live path must refuse, as plain sentences; an empty list means it may run."""
    problems = []
    for role in dict.fromkeys(c["role"] for c in cfgs):
        mid = ((gm.get("models") or {}).get(role) or {}).get("id")
        if not mid or str(mid).startswith("UNKNOWN"):
            problems.append("model %s: id is %r; fill in the real model id first" % (role, mid))
        p = (gm.get("prices") or {}).get(role) or {}
        for k in ("in", "out", "cached_in"):
            if p.get(k) is None:
                problems.append("model %s: price %s is null (source: %s); the spend guard cannot work without it"
                                % (role, k, p.get("source", "none")))
        if location is not None and p.get("location") and p["location"] != location:
            problems.append("model %s: prices in the models file are for location %s, the run would use %s"
                            % (role, p["location"], location))
    return problems


# ---------------------------------------------------------------- request building


def schema_type(t):
    """JSON Schema type name -> the form sent to Vertex (see SCHEMA_TYPE_CASE)."""
    return t.upper() if SCHEMA_TYPE_CASE == "upper" else t.lower()


def to_schema(s):
    out = {}
    for k, v in s.items():
        if k == "type":
            out[k] = schema_type(v)
        elif k == "properties":
            out[k] = {name: to_schema(sub) for name, sub in v.items()}
        elif k == "items":
            out[k] = to_schema(v)
        else:
            out[k] = v
    return out


def gemini_tools(tools):
    return [{"functionDeclarations": [{"name": t["name"], "description": t["description"],
                                       "parameters": to_schema(t["input_schema"])} for t in tools]}]


def thinking_level_for(cfg, override=None):
    level = (override or EFFORT_TO_LEVEL[cfg["effort"]]).upper()
    if level not in THINKING_LEVELS:
        raise SystemExit("thinking level %s is not one of %s" % (level, ", ".join(THINKING_LEVELS)))
    return level


def first_contents(claim):
    return [{"role": "user", "parts": [{"text": mb.first_messages(claim)[0]["content"]}]}]


def loop_body(cfg, nonce, contents, thinking_level=None):
    thinking = {THINKING_LEVEL_KEY: thinking_level_for(cfg, thinking_level)}
    if INCLUDE_THOUGHTS:
        thinking["includeThoughts"] = True
    return {"systemInstruction": {"parts": [{"text": f"[trial {nonce}]\n\n{mb.SYSTEM_PROMPT}"}]},
            "contents": contents,
            "tools": gemini_tools(mb.TOOLS),
            "toolConfig": {"functionCallingConfig": {"mode": FUNCTION_CALLING_MODE}},
            "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS, "thinkingConfig": thinking}}


def endpoint(model_id, project, location):
    host = GLOBAL_HOST if location == "global" else "%s-%s" % (location, GLOBAL_HOST)
    return "https://%s/%s/projects/%s/locations/%s/publishers/google/models/%s:%s?%s" % (
        host, API_VERSION, project, location, model_id, STREAM_METHOD, STREAM_QUERY)


def request_headers(token=None):
    return {"content-type": "application/json", "authorization": "Bearer " + (token if token else TOKEN_PLACEHOLDER)}


def function_responses(model_parts):
    """One functionResponse part per functionCall part, in the same order, with the call's id echoed when it has one
    (the 3.8 Flash guide: a FunctionResponse turn must match the id, name and count of the preceding FunctionCall)."""
    out = []
    for p in model_parts:
        fc = p.get("functionCall")
        if fc is None:
            continue
        fr = {"name": fc["name"], "response": {FUNCTION_RESPONSE_KEY: mb.execute_tool(fc["name"], fc.get("args") or {})}}
        if fc.get("id"):
            fr["id"] = fc["id"]
        out.append({"functionResponse": fr})
    return out


# ---------------------------------------------------------------- cost


def cache_split(usage):
    """(uncached input tokens, cached input tokens, all input tokens), under PROMPT_COUNT_INCLUDES_CACHED (see there)."""
    prompt = usage.get("promptTokenCount") or 0
    cached = usage.get("cachedContentTokenCount") or 0
    if PROMPT_COUNT_INCLUDES_CACHED:
        return max(prompt - cached, 0), cached, prompt
    return prompt, cached, prompt + cached


def gemini_cost(usage, prices):
    """(dollars, cached share of the input) for one request: uncached input at the input price, cached input at the cached
    price, candidates plus thinking tokens at the output price. toolUsePromptTokenCount (built-in tools, not expected with
    function calling) is priced as input so that it is never dropped silently."""
    m = 1_000_000
    uncached, cached, total_in = cache_split(usage)
    uncached += usage.get("toolUsePromptTokenCount") or 0
    out = (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0)
    cost = uncached * prices["in"] / m + cached * prices["cached_in"] / m + out * prices["out"] / m
    return cost, (cached / total_in if total_in else 0.0)


# ---------------------------------------------------------------- dry run and estimate (no network)


def dry_run(cfgs, claims, gm, show_limit=300, thinking_level=None):
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or DEFAULT_LOCATION   # a region name, not a credential
    printed = 0
    for cfg in cfgs:
        mid = gm["models"][cfg["role"]]["id"]
        for c in claims:
            body = loop_body(cfg, 0, first_contents(c), thinking_level)
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            printed += 1
            print("#%d  %s  %s  turn 1 of up to %d" % (printed, cfg["id"], c["id"], MAX_TURNS))
            print("  POST %s" % endpoint(mid, PROJECT_PLACEHOLDER, location))
            print("  headers " + json.dumps(request_headers()))
            print("  body bytes %d sha256 %s" % (len(raw), hashlib.sha256(raw).hexdigest()))
            print("  body " + json.dumps(mb._elide(body, show_limit), ensure_ascii=False))
    for why in readiness(cfgs, gm, location):
        print("note: the live run would refuse: " + why)
    print("printed request bodies: %d (first turns only; no network call was made and no credential was read)" % printed)
    return printed


def estimate_claim_cost(cfg, gm):
    p = gm["prices"].get(cfg["role"]) or {}
    if p.get("in") is None or p.get("out") is None:
        return None
    return (EST_INPUT_TOKENS_PER_CLAIM * p["in"] + EST_OUTPUT_TOKENS_PER_CLAIM * p["out"]) / 1e6


def estimate(cfgs, gm, n_claims, trials):
    print("Upper bound, nothing read from the cache: %d input and %d output tokens (thinking included) per claim, x %d claims x %d"
          " trials, at the list prices in the models file." % (EST_INPUT_TOKENS_PER_CLAIM, EST_OUTPUT_TOKENS_PER_CLAIM,
                                                              n_claims, trials))
    total, unread = 0.0, 0
    for cfg in cfgs:
        per = estimate_claim_cost(cfg, gm)
        if per is None:
            unread += 1
            print("  %-22s %-26s prices unread" % (cfg["id"], cfg["label"]))
            continue
        cost = per * n_claims * trials
        total += cost
        p = gm["prices"][cfg["role"]]
        print("  %-22s %-26s $%.4f per claim (in %.3f, out %.3f per million, %s) -> $%.2f"
              % (cfg["id"], cfg["label"], per, p["in"], p["out"], p.get("location", "?"), cost))
    if unread and total == 0:
        print("  TOTAL prices unread")
    elif unread:
        print("  TOTAL $%.2f for the arms with prices; prices unread for %d arm(s)" % (total, unread))
    else:
        print("  TOTAL $%.2f" % total)
    return None if unread else total


# ---------------------------------------------------------------- streaming and timing
# Definitions, the same meaning as model_benchmark.py:
#   connect_s       DNS, TCP and TLS, kept apart; the clock below starts after the connection is open
#   ttfb_s          request sent -> first server chunk (network, queue and prefill)
#   first_delta_s   request sent -> first part of any kind (thought, text or functionCall)
#   first_text_s    request sent -> first non-empty text part that is not a thought (None when the reply has no text)
#   wall_s          request sent -> last server chunk (Gemini sends no stop event; the last chunk carries finishReason)


def _plain_text(p):
    return "text" in p and set(p) <= {"text", "thought"}   # a text part with no thoughtSignature and nothing else


def parse_gemini_sse(lines, clock=time.monotonic, t_open=None):
    """Assemble a streamGenerateContent?alt=sse stream (each `data: {json}` line is one GenerateContentResponse) into one
    response dict plus the timing fields above. Parts are kept in order; adjacent text parts are joined only when both are
    plain text of the same kind (thought or not) and neither carries a thoughtSignature. usageMetadata is taken from the
    last chunk that has one. Raises RuntimeError on an error chunk or a stream that ends without a finishReason."""
    t_open = clock() if t_open is None else t_open
    tm = {"ttfb_s": None, "first_delta_s": None, "first_text_s": None, "wall_s": None}
    parts, finish, usage, role, extra, chunks = [], None, None, None, {}, 0
    for raw in lines:
        line = raw.decode("utf-8", "replace").strip() if isinstance(raw, (bytes, bytearray)) else raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        ev = json.loads(payload)
        now = clock() - t_open
        chunks += 1
        if tm["ttfb_s"] is None:
            tm["ttfb_s"] = now
        tm["wall_s"] = now
        if "error" in ev:
            raise RuntimeError("stream error chunk: %s" % json.dumps(ev["error"])[:600])
        if ev.get("usageMetadata"):
            usage = ev["usageMetadata"]
        for k in ("modelVersion", "responseId", "promptFeedback"):
            if k in ev:
                extra[k] = ev[k]
        cands = ev.get("candidates") or []
        if not cands:
            continue
        cand = cands[0]
        content = cand.get("content") or {}
        role = content.get("role", role)
        for p in content.get("parts") or []:
            if tm["first_delta_s"] is None:
                tm["first_delta_s"] = now
            if p.get("text") and not p.get("thought") and tm["first_text_s"] is None:
                tm["first_text_s"] = now
            if parts and _plain_text(parts[-1]) and _plain_text(p) and bool(parts[-1].get("thought")) == bool(p.get("thought")):
                parts[-1]["text"] += p["text"]
            else:
                parts.append(dict(p))
        if cand.get("finishReason"):
            finish = cand["finishReason"]
    if finish is None:
        why = (extra.get("promptFeedback") or {}).get("blockReason")
        raise RuntimeError("stream ended without a finishReason after %d chunks%s" % (chunks, "; blockReason " + why if why else ""))
    msg = {"candidates": [{"content": {"role": role or "model", "parts": parts}, "finishReason": finish}],
           "usageMetadata": usage or {}, "chunks": chunks}
    msg.update({k: v for k, v in extra.items() if k != "promptFeedback"})
    return msg, tm


def _no_redaction(s):
    return str(s)


def stream_gemini(url, hdrs, body, conn_factory=None, clock=time.monotonic, timeout=900, redact=_no_redaction,
                  sleep=time.sleep):
    """POST the body to a streamGenerateContent?alt=sse URL. Returns (status, response dict or redacted error text, timing,
    attempts). The connection pattern is model_benchmark.stream_http's: connect first (connect_s), start the clock, send,
    read; transient network errors and RETRY_STATUSES are retried up to MAX_ATTEMPTS times. Every error text returned or
    raised goes through redact first."""
    if not LIVE["armed"]:
        raise RuntimeError("network path reached while not armed; refusing")
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    u = urllib.parse.urlparse(url)
    path = u.path + ("?" + u.query if u.query else "")
    factory = conn_factory or (lambda: mb._default_connection(u.netloc, timeout))
    for attempt in range(1, MAX_ATTEMPTS + 1):
        conn = factory()
        try:
            t_connect = clock()
            conn.connect()
            connect_s = clock() - t_connect
            t_open = clock()
            conn.request("POST", path, body=data, headers=hdrs)
            r = conn.getresponse()
            if r.status != 200:
                txt = redact(r.read().decode("utf-8", "replace"))
                if r.status in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                    print("RETRY %d: HTTP %s" % (attempt, r.status), file=sys.stderr)
                    sleep(5 * attempt)
                    continue
                return r.status, txt, None, attempt
            msg, tm = parse_gemini_sse(r, clock, t_open)
            tm["connect_s"] = connect_s
            return 200, msg, tm, attempt
        except (ssl.SSLError, ConnectionError, TimeoutError, OSError, RuntimeError, _httpclient.HTTPException) as e:
            if attempt < MAX_ATTEMPTS:
                print("RETRY %d: %s" % (attempt, type(e).__name__), file=sys.stderr)
                sleep(5 * attempt)
                continue
            raise RuntimeError(redact("%s: %s" % (type(e).__name__, e))) from None
        finally:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------- live (never reached in --dry-run or --estimate)

_PROJECTS_PATTERN = re.compile(r"projects/[^/\s\"'?&]+")


def make_redactor(project, token):
    """Removes the token, the configured project string and any projects/<id> path segment (Vertex errors can name the
    project number as well as the id) from a text."""
    def redact(s):
        s = str(s)
        if token:
            s = s.replace(token, TOKEN_PLACEHOLDER)
        if project:
            s = s.replace(project, PROJECT_PLACEHOLDER)
        return _PROJECTS_PATTERN.sub("projects/" + PROJECT_PLACEHOLDER, s)
    return redact


def load_env():
    """From the environment and from nowhere else; nothing is printed."""
    token = os.environ.get("GEMINI_ACCESS_TOKEN")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    missing = [n for n, v in (("GEMINI_ACCESS_TOKEN", token), ("GOOGLE_CLOUD_PROJECT", project)) if not v]
    if missing:
        raise SystemExit("set %s in the environment" % " and ".join(missing))
    return {"token": token, "project": project, "location": os.environ.get("GOOGLE_CLOUD_LOCATION") or DEFAULT_LOCATION}


class Run:
    def __init__(self, a, gm, env, conn_factory=None, clock=time.monotonic, sleep=time.sleep, redact_on=True):
        self.a, self.gm, self.env = a, gm, env
        self.conn_factory, self.clock, self.sleep = conn_factory, clock, sleep
        self.redact = make_redactor(env["project"], env["token"]) if redact_on else _no_redaction
        self.spent = 0.0
        self.log = open(os.path.join(a.out, "requests.jsonl"), "a", encoding="utf-8")

    def prices(self, cfg):
        return self.gm["prices"][cfg["role"]]

    def worst_case(self, cfg, body):
        p = self.prices(cfg)
        tin = len(json.dumps(body)) / 3.0
        return (tin * p["in"] + (MAX_OUTPUT_TOKENS + WORST_CASE_EXTRA_THOUGHT_TOKENS) * p["out"]) / 1e6

    def guard(self, extra):
        if self.spent + extra > self.a.ceiling_usd:
            raise SystemExit("STOP before the next call: spent $%.4f + worst case $%.4f > ceiling $%.2f" % (
                self.spent, extra, self.a.ceiling_usd))

    def record(self, tag, cfg, body, status, resp, timing, attempts, level):
        resp = resp if isinstance(resp, dict) else {"raw": str(resp)[:600]}
        usage = resp.get("usageMetadata") or {}
        cost, share = gemini_cost(usage, self.prices(cfg)) if usage else (0.0, 0.0)
        self.spent += cost
        cand = (resp.get("candidates") or [{}])[0]
        rec = {"t": time.time(), "tag": tag, "model": self.gm["models"][cfg["role"]]["id"], "status": status,
               "resolved_model": resp.get("modelVersion"), "stop": cand.get("finishReason"),
               "usage": usage, "notebook_cost": cost, "list_cost": cost,
               "cached_tokens": usage.get("cachedContentTokenCount") or 0,
               "thoughts_tokens": usage.get("thoughtsTokenCount") or 0, "cached_share": share,
               "prompt_count_includes_cached": PROMPT_COUNT_INCLUDES_CACHED,
               "thinking_level": level, "location": self.env["location"], "api": "vertex " + STREAM_METHOD,
               "body_sha256": hashlib.sha256(json.dumps(body).encode()).hexdigest(),
               "timing": timing, "attempts": attempts, "error": None if status == 200 else resp}
        self.log.write(self.redact(json.dumps(rec)) + "\n")
        self.log.flush()
        return cost

    def create(self, tag, cfg, body, level):
        self.guard(self.worst_case(cfg, body))
        url = endpoint(self.gm["models"][cfg["role"]]["id"], self.env["project"], self.env["location"])
        status, resp, tm, attempts = stream_gemini(url, request_headers(self.env["token"]), body,
                                                   conn_factory=self.conn_factory, clock=self.clock,
                                                   redact=self.redact, sleep=self.sleep)
        cost = self.record(tag, cfg, body, status, resp, tm, attempts, level)
        if status != 200:
            raise RuntimeError(self.redact("HTTP %s on %s: %s" % (status, tag, str(resp)[:600])))
        if REQUIRE_USAGE and not resp.get("usageMetadata"):
            raise RuntimeError("no usageMetadata in the stream for %s; its cost cannot be counted, stopping" % tag)
        return resp, cost


def run_loop(run, cfg, claim, nonce, tag, thinking_level=None):
    """The agent loop: the model's content is appended as received, every functionCall is answered in one user turn, and
    a terminal tool ends the claim with its verdict. Returns (verdict, cost, turns)."""
    level = thinking_level_for(cfg, thinking_level)
    contents = first_contents(claim)
    cost_tot, verdict, turns = 0.0, None, 0
    for turns in range(1, MAX_TURNS + 1):
        body = loop_body(cfg, nonce, contents, level)
        r, cost = run.create("%s t%d" % (tag, turns), cfg, body, level)
        cost_tot += cost
        content = (r.get("candidates") or [{}])[0].get("content") or {}
        model_parts = content.get("parts") or []
        contents.append({"role": content.get("role") or "model", "parts": model_parts})
        calls = [p["functionCall"] for p in model_parts if "functionCall" in p]
        for fc in calls:
            if fc.get("name") in mb.TERMINAL:
                verdict = mb.TERMINAL[fc["name"]]
        if verdict or not calls:
            break
        contents.append({"role": "user", "parts": function_responses(model_parts)})
    return verdict or "NONE", cost_tot, turns


def live(cfgs, claims, gm, a, env=None, transport=None):
    """The paid run. transport (selftest only) supplies conn_factory, clock, sleep and redact_on."""
    transport = transport or {}
    location = (env or {}).get("location") or os.environ.get("GOOGLE_CLOUD_LOCATION") or DEFAULT_LOCATION
    problems = readiness(cfgs, gm, location)
    if problems:
        raise SystemExit("refusing the live run:\n  " + "\n  ".join(problems))
    env = env or load_env()
    os.makedirs(a.out, exist_ok=True)
    LIVE["armed"] = True
    run = Run(a, gm, env, **transport)
    with open(os.path.join(a.out, "trials.jsonl"), "a", encoding="utf-8") as summary:
        for cfg in cfgs:
            level = thinking_level_for(cfg, a.thinking_level)
            for trial in range(1, a.trials + 1):
                nonce = time.time_ns()   # a fresh nonce per trial, so its first request cannot match an earlier prefix
                tag = "%s trial%d" % (cfg["id"], trial)
                t_trial = time.monotonic()
                results, claim_wall = {}, {}
                for c in claims:
                    t_claim = time.monotonic()
                    results[c["id"]] = run_loop(run, cfg, c, nonce, "%s %s" % (tag, c["id"]), level)
                    claim_wall[c["id"]] = round(time.monotonic() - t_claim, 3)
                misses = sorted(c["id"] for c in claims if results[c["id"]][0] != c["expected"])
                n = len(claims)
                per_task = sum(v[1] for v in results.values()) / n
                rec = {"config": cfg["id"], "label": cfg["label"], "trial": trial, "n": n, "correct": n - len(misses),
                       "misses": misses, "per_task_notebook": per_task, "per_task_list": per_task,
                       "turns": sum(v[2] for v in results.values()), "verdicts": {k: v[0] for k, v in results.items()},
                       "models": {cfg["role"]: gm["models"][cfg["role"]]["id"]}, "arm_name": cfg["label"],
                       "streamed": True, "order": "arm", "claim_wall_s": claim_wall,
                       "trial_wall_s": round(time.monotonic() - t_trial, 3), "thinking_level": level,
                       "thinking_level_forced": bool(a.thinking_level)}
                summary.write(run.redact(json.dumps(rec)) + "\n")
                summary.flush()
                shown = ""
                if a.measure != "timing":
                    shown += "  $/task %.4f" % per_task
                if a.measure != "cost":
                    shown += "  wall %.0f s" % rec["trial_wall_s"]
                print(run.redact("%-20s %-26s thinking %s%s trial %d  %d/%d  requests %d%s  misses %s  spent $%.2f" % (
                    cfg["id"], cfg["label"], level, " (forced)" if a.thinking_level else "", trial, rec["correct"], n,
                    rec["turns"], shown, ",".join(misses) or "-", run.spent)), flush=True)
    run.log.close()


# ---------------------------------------------------------------- selftest (offline: fake transport, fake clock)


def _data(o):
    return ("data: " + json.dumps(o)).encode()


def _chunk(parts, finish=None, usage=None, **kw):
    cand = {"content": {"role": "model", "parts": parts}}
    if finish:
        cand["finishReason"] = finish
    ev = {"candidates": [cand], **kw}
    if usage:
        ev["usageMetadata"] = usage
    return _data(ev)


USAGE_T1 = {"promptTokenCount": 12000, "cachedContentTokenCount": 8000, "candidatesTokenCount": 50,
            "thoughtsTokenCount": 300, "totalTokenCount": 12350}
USAGE_T2 = {"promptTokenCount": 12500, "cachedContentTokenCount": 12000, "candidatesTokenCount": 20,
            "thoughtsTokenCount": 100, "totalTokenCount": 12620}
FAKE_PRICES = {"in": 1.0, "cached_in": 0.1, "out": 4.0, "location": "global", "source": "selftest"}


def _turn1_stream(cid, ids=False):
    """A thought in two pieces (the second carries a signature), text in two pieces, two parallel function calls (only the
    first carries a signature), an interim usage block, and a last chunk with finishReason and the final usage."""
    fc1 = {"name": "get_claim", "args": {"claim_id": cid}}
    fc2 = {"name": "get_policy", "args": {"claim_id": cid}}
    if ids:
        fc1["id"], fc2["id"] = "call-a", "call-b"
    return [b": keepalive comment", b"",
            _chunk([{"text": "weighing ", "thought": True}]), b"",
            _chunk([{"text": "the claim", "thought": True, "thoughtSignature": "SIG1"}]), b"",
            _chunk([{"text": "Checking "}]),
            _chunk([{"text": "the record."}]),
            _chunk([{"functionCall": fc1, "thoughtSignature": "SIG2"}, {"functionCall": fc2}],
                   usage={"promptTokenCount": 10}),
            _chunk([{"text": ""}], finish="STOP", usage=USAGE_T1, modelVersion="gemini-selftest")]


def _turn1_parts(cid, ids=False):
    fc1 = {"name": "get_claim", "args": {"claim_id": cid}}
    fc2 = {"name": "get_policy", "args": {"claim_id": cid}}
    if ids:
        fc1["id"], fc2["id"] = "call-a", "call-b"
    return [{"text": "weighing ", "thought": True},
            {"text": "the claim", "thought": True, "thoughtSignature": "SIG1"},
            {"text": "Checking the record."},
            {"functionCall": fc1, "thoughtSignature": "SIG2"},
            {"functionCall": fc2},
            {"text": ""}]


def _turn2_stream(cid):
    return [_chunk([{"functionCall": {"name": "approve_claim", "args": {"claim_id": cid, "amount": "5000"}},
                     "thoughtSignature": "SIG3"}], finish="STOP", usage=USAGE_T2)]


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class _FakeVertex:
    """Answers each request with the next reply. A reply is a function (path, headers) -> (status, list of lines or text),
    so an error reply can echo the URL and the authorization header back, as a careless server might."""
    def __init__(self, replies, clock):
        self.replies, self.clock, self.sent = list(replies), clock, []

    def factory(self):
        srv = self

        class _Resp:
            def __init__(self, status, payload):
                self.status, self.payload = status, payload

            def __iter__(self):
                for line in self.payload:
                    if line.startswith(b"data:"):
                        srv.clock.t += 1.0
                    yield line

            def read(self):
                return self.payload.encode() if isinstance(self.payload, str) else b"\n".join(self.payload)

        class _Conn:
            def connect(self):
                srv.clock.t += 0.30          # DNS, TCP and TLS take 0.30 s on this fake connection

            def request(self, method, path, body=None, headers=None):
                srv.sent.append({"method": method, "path": path, "headers": dict(headers or {}), "body": json.loads(body)})
                self.reply = srv.replies.pop(0)(path, headers or {})

            def getresponse(self):
                return _Resp(*self.reply)

            def close(self):
                pass
        return _Conn()


def _no_network():
    raise RuntimeError("selftest: a real connection was requested")


def _leak_run(project, token, redact_on):
    """Two fake live runs into a fresh temporary --out folder: one claim that succeeds (its calls carry ids), then one
    whose first request gets a 403 echoing the URL and the token. Returns what the checks need."""
    out = tempfile.mkdtemp(prefix="gemini-selftest-")
    clk = _Clock()
    claim = {"id": "CLM-TEST", "summary": "Made-up claim for the selftest.", "expected": "APPROVE"}
    env = {"token": token, "project": project, "location": "global"}
    gm = {"models": {"gemini-3.8-flash": {"id": "gemini-selftest"}}, "prices": {"gemini-3.8-flash": FAKE_PRICES}}
    cfg = [c for c in CONFIGS if c["id"] == "gemini-flash-medium"]
    a = argparse.Namespace(out=out, ceiling_usd=1.0, trials=1, measure="both", thinking_level=None)

    def echo(path, hdrs):
        return 403, json.dumps({"error": {"code": 403, "message": "Permission denied on https://%s%s for consumer "
                                          "projects/123456789012; credential %s" % (GLOBAL_HOST, path, hdrs.get("authorization"))}})
    srv = _FakeVertex([lambda p, h: (200, _turn1_stream(claim["id"], ids=True)), lambda p, h: (200, _turn2_stream(claim["id"])),
                       echo], clk)
    transport = {"conn_factory": srv.factory, "clock": clk, "sleep": lambda s: None, "redact_on": redact_on}
    buf, raised = io.StringIO(), ""
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            live(cfg, [claim], gm, a, env=env, transport=transport)
            live(cfg, [claim], gm, a, env=env, transport=transport)
        except (RuntimeError, SystemExit) as e:
            raised = str(e)
        finally:
            LIVE["armed"] = False
    files = {}
    for name in sorted(os.listdir(out)):
        with open(os.path.join(out, name), encoding="utf-8") as f:
            files[name] = f.read()
    blob = "\n".join(files.values()) + "\n" + buf.getvalue() + "\n" + raised
    leaked = any(s in blob for s in (project, token, "123456789012"))
    return {"leaked": leaked, "files": files, "raised": raised, "sent": srv.sent, "out": out}


def selftest(inject_fault=False):
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = round(got, 6) == round(want, 6) if isinstance(want, float) else got == want
        ok &= good
        def short(x):
            s = repr(x)
            return s if len(s) <= 120 else "%s... (%d chars)" % (s[:100], len(s))
        print("%-4s %-58s got %s want %s" % ("PASS" if good else "FAIL", name, short(got), short(want)))

    # tool conversion
    decl = gemini_tools(mb.TOOLS)
    check("tools: one functionDeclarations block", (len(decl), list(decl[0])), (1, ["functionDeclarations"]))
    check("tools: all twelve, same order", [d["name"] for d in decl[0]["functionDeclarations"]], [t["name"] for t in mb.TOOLS])
    check("tools: get_claim converted", decl[0]["functionDeclarations"][0],
          {"name": "get_claim", "description": "Retrieve the full claim record.",
           "parameters": {"type": "OBJECT", "properties": {"claim_id": {"type": "STRING", "description": "Claim ID, e.g. CLM-001"}},
                          "required": ["claim_id"]}})
    check("tools: schema type casing", (schema_type("object"), schema_type("string")), ("OBJECT", "STRING"))

    # request body
    claim0 = mb.EVAL_CLAIMS[0]
    med = [c for c in CONFIGS if c["id"] == "gemini-flash-medium"][0]
    b = loop_body(med, 7, first_contents(claim0))
    check("body: system instruction has the trial head", b["systemInstruction"]["parts"][0]["text"],
          "[trial 7]\n\n" + mb.SYSTEM_PROMPT)
    check("body: first user text as model_benchmark", b["contents"], [{"role": "user", "parts": [{"text":
          mb.first_messages(claim0)[0]["content"]}]}])
    check("body: thinking level from the arm's effort", b["generationConfig"]["thinkingConfig"], {"thinkingLevel": "MEDIUM"})
    check("body: --thinking-level overrides the arm", loop_body(med, 7, [], "low")["generationConfig"]["thinkingConfig"],
          {"thinkingLevel": "LOW"})
    check("body: output limit and calling mode", (b["generationConfig"]["maxOutputTokens"], b["toolConfig"]),
          (4096, {"functionCallingConfig": {"mode": "AUTO"}}))
    check("body: no model or stream field in the body", ("model" in b, "stream" in b), (False, False))
    check("six arms, labels in words", [c["label"] for c in CONFIGS],
          ["Gemini 3.8 Flash high", "Gemini 3.8 Flash medium", "Gemini 3.8 Flash low",
           "Gemini 4 Argon high", "Gemini 4 Argon medium", "Gemini 4 Argon low"])
    check("url: global host", endpoint("m", "P", "global"),
          "https://aiplatform.googleapis.com/v1/projects/P/locations/global/publishers/google/models/m:streamGenerateContent?alt=sse")
    check("url: regional host", endpoint("m", "P", "us-central1").split("/")[2], "us-central1-aiplatform.googleapis.com")

    # function responses, with and without call ids
    fr = function_responses(_turn1_parts("CLM-001", ids=True))
    check("responses: ids echoed, names in order", [(x["functionResponse"].get("id"), x["functionResponse"]["name"]) for x in fr],
          [("call-a", "get_claim"), ("call-b", "get_policy")])
    fr = function_responses(_turn1_parts("CLM-001"))
    check("responses: no id when the call has none", ["id" in x["functionResponse"] for x in fr], [False, False])
    check("responses: tool text under the result key", fr[0]["functionResponse"]["response"],
          {"result": mb.execute_tool("get_claim", {"claim_id": "CLM-001"})})

    # stream parser on a fake clock: one tick per data line, t_open = -1, so the first chunk is at 1.0
    tick = iter(range(0, 1000))
    msg, tm = parse_gemini_sse(_turn1_stream("CLM-001"), clock=lambda: float(next(tick)), t_open=-1.0)
    parts = msg["candidates"][0]["content"]["parts"]
    check("sse: parts in order, as expected", parts, _turn1_parts("CLM-001"))
    check("sse: signed thought piece not merged into the one before", (parts[0], parts[1]),
          ({"text": "weighing ", "thought": True}, {"text": "the claim", "thought": True, "thoughtSignature": "SIG1"}))
    check("sse: plain text pieces joined", parts[2], {"text": "Checking the record."})
    check("sse: signature stays on the first call only", ("thoughtSignature" in parts[3], "thoughtSignature" in parts[4]),
          (True, False))
    check("sse: finish reason", msg["candidates"][0]["finishReason"], "STOP")
    check("sse: usage from the last chunk, not the interim one", msg["usageMetadata"], USAGE_T1)
    check("sse: model version kept", msg.get("modelVersion"), "gemini-selftest")
    check("sse: timing on the fake clock (first chunk, first part, first text, wall)",
          (tm["ttfb_s"], tm["first_delta_s"], tm["first_text_s"], tm["wall_s"]), (1.0, 1.0, 3.0, 6.0))
    try:
        parse_gemini_sse(_turn1_stream("CLM-001")[:-1], clock=lambda: 0.0, t_open=0.0)
        check("sse: a stream without finishReason is refused", "accepted", "refused")
    except RuntimeError:
        check("sse: a stream without finishReason is refused", "refused", "refused")

    # cost, hand-computed: 4000 uncached x $1 + 8000 cached x $0.1 + (50 + 300) out x $4, per million
    cost, share = gemini_cost(USAGE_T1, FAKE_PRICES)
    check("cost: hand-computed example (thinking billed as output)", cost, 0.0062)
    check("cost: cached share", round(share, 4), 0.6667)
    check("cost: without cachedContentTokenCount all input is uncached", gemini_cost({"promptTokenCount": 1000}, FAKE_PRICES),
          (0.001, 0.0))
    check("estimate: per claim at the fake prices", estimate_claim_cost(med, {"prices": {"gemini-3.8-flash": FAKE_PRICES}}),
          0.061)
    check("estimate: null prices read as unread",
          estimate_claim_cost(med, {"prices": {"gemini-3.8-flash": {"in": None, "out": None}}}), None)

    # readiness and refusals
    unknown = {"models": {"gemini-3.8-flash": {"id": "UNKNOWN: fill after the smoke test"}},
               "prices": {"gemini-3.8-flash": FAKE_PRICES}}
    nullp = {"models": {"gemini-3.8-flash": {"id": "gemini-3.8-flash"}},
             "prices": {"gemini-3.8-flash": {"in": None, "out": None, "cached_in": None, "source": "UNREAD"}}}
    a0 = argparse.Namespace(out=tempfile.mkdtemp(prefix="gemini-selftest-"), ceiling_usd=1.0, trials=1, measure="both",
                            thinking_level=None)
    for name, gm_, word in (("live refuses an UNKNOWN model id", unknown, "UNKNOWN"), ("live refuses a null price", nullp, "null")):
        try:
            live([med], [claim0], gm_, a0, env={"token": "t", "project": "p", "location": "global"},
                 transport={"conn_factory": _no_network})
            check(name, "ran", "refused")
        except SystemExit as e:
            check(name, "refused" if word in str(e) else "refused for another reason: %s" % e, "refused")
        except RuntimeError as e:   # readiness let it through and it reached the (fake) network
            check(name, "ran until: %s" % e, "refused")
        finally:
            LIVE["armed"] = False
    check("readiness: a price for another location is refused",
          bool(readiness([med], {"models": {"gemini-3.8-flash": {"id": "x"}}, "prices": {"gemini-3.8-flash": FAKE_PRICES}},
                         "us-central1")), True)
    check("readiness: the shipped models file is ready for global", readiness(CONFIGS, load_gemini_models(), "global"), [])

    # network guard
    try:
        stream_gemini("https://%s/x" % GLOBAL_HOST, {}, {})
        check("network refused while not armed", "ran", "refused")
    except RuntimeError as e:
        check("network refused while not armed", "refused" if "not armed" in str(e) else str(e), "refused")

    # dry run reads no credential and shows placeholders
    real_load_env = globals()["load_env"]

    def _forbidden():
        raise AssertionError("dry run read the credentials")
    globals()["load_env"] = _forbidden
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            dry_run([med], [claim0], load_gemini_models())
        dry = buf.getvalue()
    finally:
        globals()["load_env"] = real_load_env
    check("dry run: project and token shown as placeholders",
          ("/projects/<PROJECT>/" in dry, "Bearer <REDACTED>" in dry), (True, True))

    # whole loop on a fake transport: get_claim and get_policy, then approve_claim
    clk = _Clock()
    srv = _FakeVertex([lambda p, h: (200, _turn1_stream("CLM-TEST")), lambda p, h: (200, _turn2_stream("CLM-TEST"))], clk)
    out = tempfile.mkdtemp(prefix="gemini-selftest-")
    gm = {"models": {"gemini-3.8-flash": {"id": "gemini-selftest"}}, "prices": {"gemini-3.8-flash": FAKE_PRICES}}
    run = Run(argparse.Namespace(out=out, ceiling_usd=1.0), gm, {"token": "selftest-token-x", "project": "selftest-project-x", "location": "global"},
              conn_factory=srv.factory, clock=clk, sleep=lambda s: None)
    LIVE["armed"] = True
    try:
        verdict, cost, turns = run_loop(run, med, {"id": "CLM-TEST", "summary": "Made-up claim."}, 1, "selftest CLM-TEST")
    finally:
        LIVE["armed"] = False
        run.log.close()
    check("loop: verdict, turns, requests", (verdict, turns, len(srv.sent)), ("APPROVE", 2, 2))
    check("loop: cost is the sum of both turns", cost, 0.0062 + 0.00218)
    c2 = srv.sent[1]["body"]["contents"]
    check("loop: second request echoes the model parts unchanged", c2[1], {"role": "model", "parts": _turn1_parts("CLM-TEST")})
    check("loop: one user turn of functionResponses, in call order",
          (c2[2]["role"], [p["functionResponse"]["name"] for p in c2[2]["parts"]], len(c2)), ("user", ["get_claim", "get_policy"], 3))
    check("loop: url path and query", srv.sent[0]["path"].endswith("/models/gemini-selftest:streamGenerateContent?alt=sse"), True)
    with open(os.path.join(out, "requests.jsonl"), encoding="utf-8") as f:
        recs = [json.loads(x) for x in f if x.strip()]
    check("records: two requests, tags end t1 and t2", [r["tag"].split()[-1] for r in recs], ["t1", "t2"])
    check("records: timing (connect apart, first chunk, wall)",
          (round(recs[0]["timing"]["connect_s"], 2), recs[0]["timing"]["ttfb_s"], recs[0]["timing"]["wall_s"]), (0.3, 1.0, 6.0))
    check("records: thinking tokens, cached tokens, both cost fields",
          (recs[0]["thoughts_tokens"], recs[0]["cached_tokens"], recs[0]["notebook_cost"] == recs[0]["list_cost"]), (300, 8000, True))
    check("records: usage is the raw usageMetadata", recs[1]["usage"], USAGE_T2)

    # the project id and the token never reach a file, a printed line or an exception
    fake_project, fake_token = "fake-employer-project-123", "fake-token-0123456789abcdef"
    res = _leak_run(fake_project, fake_token, redact_on=True)
    reqs = [json.loads(x) for x in res["files"].get("requests.jsonl", "").splitlines() if x.strip()]
    check("redaction: run wrote both files and stopped on the 403",
          (sorted(res["files"]), len(reqs), reqs[-1]["status"] if reqs else None, "HTTP 403" in res["raised"]),
          (["requests.jsonl", "trials.jsonl"], 3, 403, True))
    check("redaction: the error was recorded, with placeholders", "projects/<PROJECT>" in json.dumps(reqs[-1]["error"]), True)
    check("redaction: ids echoed through the loop", [p["functionResponse"].get("id") for p in res["sent"][1]["body"]["contents"][2]["parts"]],
          ["call-a", "call-b"])
    check("redaction: project, project number and token appear nowhere", res["leaked"], False)
    bad = _leak_run(fake_project, fake_token, redact_on=False)
    check("redaction: the leak check finds them when redaction is skipped", bad["leaked"], True)
    if inject_fault:
        check("injected fault: redaction skipped, nothing leaks (must FAIL)", bad["leaked"], False)
        check("injected fault (must FAIL)", 1, 2)
    print("temporary folders (left for the OS temp cleaner): %s %s %s" % (out, res["out"], bad["out"]))
    print("selftest", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selftest", action="store_true")
    mode.add_argument("--selftest-fault", action="store_true", help="selftest with wrong expectations added; must exit 1")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--estimate", action="store_true")
    mode.add_argument("--live", action="store_true")
    ap.add_argument("--configs", default=None, help="comma-separated config ids; default: the three Gemini 3.8 Flash arms")
    ap.add_argument("--claims", default=None, help="comma-separated claim ids; default all ten")
    ap.add_argument("--trials", type=int, default=2)
    ap.add_argument("--models", default=MODELS_PATH)
    ap.add_argument("--show-limit", type=int, default=300, help="dry run: strings longer than this are elided")
    ap.add_argument("--ceiling-usd", type=float, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--measure", choices=["cost", "timing", "both"], default="both",
                    help="what to show: cost, timing or both. Every request is streamed, timed and costed whatever is chosen")
    ap.add_argument("--thinking-level", type=str.upper, choices=list(THINKING_LEVELS), default=None,
                    help="force one thinking level for every arm (default: the arm's own effort)")
    a = ap.parse_args()
    if a.selftest or a.selftest_fault:
        return selftest(inject_fault=a.selftest_fault)
    gm = load_gemini_models(a.models)
    cfgs = select_configs(a.configs)
    claims = mb.EVAL_CLAIMS if not a.claims else [c for c in mb.EVAL_CLAIMS if c["id"] in set(a.claims.split(","))]
    if not cfgs or not claims:
        raise SystemExit("no configs or claims selected")
    if a.dry_run:
        dry_run(cfgs, claims, gm, a.show_limit, a.thinking_level)
        return 0
    if a.estimate:
        estimate(cfgs, gm, len(claims), a.trials)
        return 0
    if a.ceiling_usd is None or not a.out:
        raise SystemExit("--live needs --ceiling-usd and --out")
    live(cfgs, claims, gm, a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
