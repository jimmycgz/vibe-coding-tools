#!/usr/bin/env python3
"""Cache timing test: is there a real time saving from the prompt cache?

Single requests, not the agent loop, so that time to first token measures reading the prompt and not the model thinking or
calling tools. For each model and each prefix size, three states, each with a DIFFERENT question after the same long shared
prefix (a different claim), in a rotated order, one request at a time:

  no cache   the prefix with no cache_control anywhere
  cold       the same prefix with an explicit cache breakpoint at the end of it: the first request, which writes the cache
  warm       the same prefix and breakpoint again, a different question, within the cache lifetime: it reads the cache

An explicit breakpoint at the end of the shared prefix is what lets a different question hit: automatic caching puts the
breakpoint at the end of the request, so a new question is a new cache key. Every request's usage block is checked against
its state (cold must show a write, warm a read of about the prefix size, no cache neither); a request that fails the check is
reported and left out of the medians, never averaged in.

usage:
  cache_timing.py --selftest | --selftest-fault
  cache_timing.py --dry-run                      prints the schedule and the request shapes; no network, no key
  cache_timing.py --estimate                     upper-bound cost arithmetic; no network
  cache_timing.py --live --ceiling-usd X --out DIR [--smoke] [--reps N] [--thinking disabled|omit] [--tool-choice none|omit]
  cache_timing.py --report DIR                   builds the table and charts from DIR/requests.jsonl
"""
import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model_benchmark as mb  # noqa: E402  (data, tools, prompts, the streaming request and the spend guard)
import build_results_table as brt  # noqa: E402  (SVG helpers for the charts)

LEDGER_PATH = os.path.join(HERE, "assets", "claims_ledger.csv")
MODEL_ROLES = ["opus", "sonnet", "fable"]
PREFIXES = ["13k", "long"]
STATES = ["none", "cold", "warm"]
STATE_LABEL = {"none": "no cache", "cold": "cold cache (writes)", "warm": "warm cache (reads)"}
STATE_COLOR = {"none": "#8c97a3", "cold": "#e0a030", "warm": "#3b8f6b"}
CHART_NOTE = ("Latest models: Opus 5.5, Sonnet 5.5, Fable 5.1. 13k = ~13,000-token prefix; long = plus the claims ledger. "
              "Cold writes; warm reads.")
QUESTION = ("Claim {id}: {summary}\n\nIn about 100 words, say what you would decide and why. Do not call a tool.")
NOTE = ("Models: Opus 5.5, Sonnet 5.5, Fable 5.1, the latest versions. 13k = the benchmark's system prompt and tools, about 13,000 "
        "tokens; long = the same plus the claims ledger. no cache = none; cold = first request with a cache breakpoint, writes; "
        "warm = a different question after the same prefix, reads.")


# ------------------------------------------------------------------ schedule
def rotated(items, k):
    k %= len(items)
    return items[k:] + items[:k]


def schedule(reps, claims):
    """The fixed run order. For each repetition, each prefix, each model (model order rotated every repetition and prefix), one
    'set' of three requests with three DIFFERENT claims. The order inside a set alternates: cold then warm then no cache on even
    repetitions, no cache then cold then warm on odd ones (cold always precedes warm). Which of the three claims goes to which
    state rotates with the repetition, the model and the prefix, so no state always gets the same question."""
    out, n = [], len(claims)
    for r in range(reps):
        for p, prefix in enumerate(PREFIXES):
            for m, role in enumerate(rotated(MODEL_ROLES, r + p)):
                mi = MODEL_ROLES.index(role)
                base = (r + mi + 2 * p) % n
                trio = [claims[(base + 3 * i) % n]["id"] for i in range(3)]   # three distinct claims (3*i mod 10 is distinct)
                shift = (r + mi + p) % 3
                assign = dict(zip(STATES, rotated(trio, shift)))
                order = ["cold", "warm", "none"] if r % 2 == 0 else ["none", "cold", "warm"]
                out.append({"rep": r + 1, "prefix": prefix, "role": role, "order": order, "claims": assign})
    return out


# ------------------------------------------------------------------ request shapes
def load_ledger():
    with open(LEDGER_PATH, encoding="utf-8") as f:
        return f.read()


def build_body(model_id, prefix, nonce, claim, state, ledger, thinking="disabled", tool_choice="none"):
    blocks = [{"type": "text", "text": "[set %s]\n\n%s" % (nonce, mb.SYSTEM_PROMPT)}]
    if prefix == "long":
        blocks.append({"type": "text", "text": "Historical claims ledger (CSV), reference data:\n" + ledger})
    if state != "none":
        blocks[-1]["cache_control"] = {"type": "ephemeral"}      # the breakpoint, at the end of the shared prefix
    body = {"model": model_id, "max_tokens": 256, "system": blocks, "tools": mb.TOOLS,
            "messages": [{"role": "user", "content": QUESTION.format(id=claim["id"], summary=claim["summary"])}],
            "output_config": {"effort": "low"}}
    if tool_choice == "none":
        body["tool_choice"] = {"type": "none"}
    if thinking == "disabled":
        body["thinking"] = {"type": "disabled"}
    return body


# ------------------------------------------------------------------ checks and numbers
def check_state(state, usage):
    """Returns (ok, reason). total = every input token of the request, cached or not."""
    w = usage.get("cache_creation_input_tokens") or 0
    rd = usage.get("cache_read_input_tokens") or 0
    total = (usage.get("input_tokens") or 0) + w + rd
    if total <= 0:
        return False, "no input tokens in usage"
    if state == "none":
        return (w == 0 and rd == 0), ("" if w == 0 and rd == 0 else "no-cache request shows cache tokens")
    if state == "cold":
        ok = w >= 0.8 * total and rd < 0.05 * total
        return ok, ("" if ok else "cold request does not show a write of the prefix (write %d, read %d, total %d)" % (w, rd, total))
    ok = rd >= 0.8 * total and w < 0.2 * total
    return ok, ("" if ok else "warm request does not show a read of the prefix (write %d, read %d, total %d)" % (w, rd, total))


def tokens_per_second(out_tokens, wall_s, first_text_s):
    """Output tokens after the first one, over the time after the first text token. None when the reply has no text."""
    if not out_tokens or out_tokens < 2 or first_text_s is None or wall_s is None or wall_s <= first_text_s:
        return None
    return (out_tokens - 1) / (wall_s - first_text_s)


def reading(d_none_warm, d_cold_warm, k=8):
    """The reading rule fixed in the plan. Headline: warm against no cache, seen when warm was faster in at least k paired
    repetitions. Stricter, secondary: warm was also faster than cold in at least k. Returns (headline, strict, counts)."""
    a = sum(1 for x in d_none_warm if x < 0)
    b = sum(1 for x in d_cold_warm if x < 0)
    return a >= k and len(d_none_warm) > 0, (a >= k and b >= k), (a, len(d_none_warm), b, len(d_cold_warm))


def quartiles(xs):
    xs = sorted(x for x in xs if x is not None)
    if len(xs) < 2:
        return (xs[0], xs[0], xs[0]) if xs else (None, None, None)
    q = statistics.quantiles(xs, n=4, method="inclusive")
    return q[0], statistics.median(xs), q[2]


def network_context():
    """Unprivileged context for each set: the default route's interface (it changes when the network is switched) and three
    TCP connect times to the API host. For reading the results, never used to correct them."""
    ctx = {}
    try:
        txt = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, timeout=5).stdout
        ctx["interface"] = next((l.split(":", 1)[1].strip() for l in txt.splitlines() if l.strip().startswith("interface:")), None)
    except Exception:
        ctx["interface"] = None
    ms = []
    for _ in range(3):
        t0 = time.monotonic()
        try:
            socket.create_connection(("api.anthropic.com", 443), timeout=5).close()
            ms.append(round((time.monotonic() - t0) * 1000, 1))
        except OSError:
            ms.append(None)
    ctx["connect_ms"] = ms
    return ctx


# ------------------------------------------------------------------ estimate and dry run
def prefix_tokens_guess():
    ledger_chars = len(load_ledger())
    return {"13k": 13100, "long_low": 13100 + int(ledger_chars / 3.0), "long_mid": 13100 + int(ledger_chars / 2.6),
            "long_high": 13100 + int(ledger_chars / 2.0)}


def estimate(models, reps):
    g = prefix_tokens_guess()
    lines = ["Upper-bound arithmetic, notebook multipliers (no cache 1x, cold write 1.25x, warm read 0.10x), %d reps, 3 models, "
             "output at most 256 tokens a request:" % reps]
    out_cost = sum(reps * 2 * 3 * 256 * models["prices"][models["roles"][r]]["out"] / 1e6 for r in MODEL_ROLES)
    totals = {}
    for key in ("long_low", "long_mid", "long_high"):
        tot = 0.0
        for role in MODEL_ROLES:
            pin = models["prices"][models["roles"][role]]["in"] / 1e6
            for p in (g["13k"], g[key]):
                tot += reps * p * pin * (1 + 1.25 + 0.10)
        totals[key] = tot + out_cost
        lines.append("  prefix guess: 13k = %d tokens, long = %d tokens -> $%.2f" % (g["13k"], g[key], totals[key]))
    lines.append("  (the ledger is %d characters; its token count is a range, measured with count_tokens after the go)"
                 % len(load_ledger()))
    return "\n".join(lines), totals


def dry_run(models, reps, claims, show_body=True):
    sched = schedule(reps, claims)
    print("%d sets, %d requests (%d reps x %d prefixes x %d models x 3 states)" % (len(sched), 3 * len(sched), reps,
                                                                                 len(PREFIXES), len(MODEL_ROLES)))
    for s in sched[:8]:
        print("  rep %d %-4s %-6s order %s claims %s" % (s["rep"], s["prefix"], s["role"], "/".join(s["order"]), s["claims"]))
    print("  ...")
    if show_body:
        ledger = load_ledger()
        for prefix in PREFIXES:
            for state in STATES:
                b = build_body(models["roles"]["sonnet"], prefix, "<time>", claims[0], state, ledger)
                shown = json.loads(json.dumps(b))
                for blk in shown["system"]:
                    blk["text"] = blk["text"][:40].replace("\n", " ") + "... (%d characters)" % len(blk["text"])
                shown["tools"] = "(%d tool definitions)" % len(b["tools"])
                print("  [%s %s]" % (prefix, state), json.dumps(shown)[:420])


# ------------------------------------------------------------------ the live run
def run_live(a, models, claims):
    env = mb.load_key()
    os.makedirs(a.out, exist_ok=True)
    mb.LIVE["armed"] = True
    run = mb.Run(argparse.Namespace(out=a.out, ceiling_usd=a.ceiling_usd, stream=True), models, env)
    ledger = load_ledger()
    by_id = {c["id"]: c for c in claims}
    sched = schedule(a.reps, claims)
    if a.smoke:
        sched = [s for s in sched if s["rep"] == 1 and s["prefix"] == "13k" and s["role"] == "sonnet"][:1]
    meta = open(os.path.join(a.out, "sets.jsonl"), "a", encoding="utf-8")
    for s in sched:
        nonce = time.time_ns()
        ctx = network_context()
        meta.write(json.dumps({"rep": s["rep"], "prefix": s["prefix"], "role": s["role"], "order": s["order"], "claims": s["claims"],
                               "network": ctx, "t": time.time()}) + "\n")
        meta.flush()
        for state in s["order"]:
            claim = by_id[s["claims"][state]]
            body = build_body(models["roles"][s["role"]], s["prefix"], nonce, claim, state, ledger, a.thinking, a.tool_choice)
            tag = "%s %s rep%d %s %s" % (s["role"], s["prefix"], s["rep"], state, claim["id"])
            try:
                resp, nb, lst = run.create(tag, body)
            except RuntimeError as e:
                print("FAILED %s: %s" % (tag, str(e)[:300]), flush=True)
                if a.smoke:
                    raise
                continue
            u = resp["usage"]
            ok, why = check_state(state, u)
            with open(os.path.join(a.out, "requests.jsonl"), encoding="utf-8") as f:
                last = json.loads(f.readlines()[-1])
            t = last.get("timing") or {}
            print("%-40s %s write %6d read %6d  first event %.2f s, first text %s s, wall %.2f s  $%.4f  spent $%.2f%s" % (
                tag, "ok  " if ok else "FAIL", u.get("cache_creation_input_tokens") or 0, u.get("cache_read_input_tokens") or 0,
                t.get("ttfb_s") or 0, "n/a" if t.get("first_text_s") is None else "%.2f" % t["first_text_s"], t.get("wall_s") or 0, nb,
                max(run.spent_notebook, run.spent_list), "" if ok else "  <- " + why), flush=True)


# ------------------------------------------------------------------ report
def load_requests(folder):
    rows = []
    for line in open(os.path.join(folder, "requests.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        role, prefix, rep, state, claim = r["tag"].split()
        u, t = r["usage"], r.get("timing") or {}
        ok, why = check_state(state, u) if r["status"] == 200 else (False, "status %s" % r["status"])
        rows.append({"role": role, "prefix": prefix, "rep": int(rep[3:]), "state": state, "claim": claim, "ok": ok, "why": why,
                     "model": r["resolved_model"] or r["model"], "ttfb": t.get("ttfb_s"), "first_text": t.get("first_text_s"),
                     "first_delta": t.get("first_delta_s"), "wall": t.get("wall_s"), "connect": t.get("connect_s"), "out": u.get("output_tokens"),
                     "tps": tokens_per_second(u.get("output_tokens"), t.get("wall_s"), t.get("first_text_s")),
                     "cost": r["notebook_cost"], "prefix_tokens": (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                     + (u.get("cache_read_input_tokens") or 0)})
    return rows


def cells(rows):
    out = {}
    for role in MODEL_ROLES:
        for prefix in PREFIXES:
            for state in STATES:
                rs = [r for r in rows if r["role"] == role and r["prefix"] == prefix and r["state"] == state]
                if not rs:
                    continue
                good = [r for r in rs if r["ok"]]
                out[(role, prefix, state)] = {"n": len(rs), "ok": len(good), "rows": good, "failed": [r for r in rs if not r["ok"]]}
    return out


def metric(c, key):
    q = quartiles([r[key] for r in c["rows"]])
    return q


def paired(rows, role, prefix, a, b, key):
    """Per repetition, b minus a for the same model and prefix, over the repetitions where both requests passed the check."""
    ra = {r["rep"]: r[key] for r in rows if r["role"] == role and r["prefix"] == prefix and r["state"] == a and r["ok"] and r[key] is not None}
    rb = {r["rep"]: r[key] for r in rows if r["role"] == role and r["prefix"] == prefix and r["state"] == b and r["ok"] and r[key] is not None}
    d = [rb[k] - ra[k] for k in ra if k in rb]
    return d


def report(folder, out):
    rows = load_requests(folder)
    cs = cells(rows)
    names = {"opus": "Opus", "sonnet": "Sonnet", "fable": "Fable"}
    head = "| Model | Prefix | State | Checked ok | First token s (median, quartiles) | First event s (median) | Wall s (median) | Output tokens/s (median) | Connect s (median, not in the times) | $ per request |"
    lines = [head, "|" + "---|" * 10]
    for (role, prefix, state), c in cs.items():
        q = metric(c, "first_text") if any(r["first_text"] is not None for r in c["rows"]) else metric(c, "first_delta")
        lines.append("| %s | %s | %s | %d of %d | %s | %s | %s | %s | %s | %.4f |" % (
            names[role], prefix, STATE_LABEL[state], c["ok"], c["n"],
            "n/a" if q[1] is None else "%.2f (%.2f to %.2f)" % (q[1], q[0], q[2]),
            brt.fmt(metric(c, "ttfb")[1]), brt.fmt(metric(c, "wall")[1]), brt.fmt(metric(c, "tps")[1], 1), brt.fmt(metric(c, "connect")[1], 3),
            statistics.mean(r["cost"] for r in c["rows"]) if c["rows"] else 0.0))
    diffs = ["", "Paired differences, per repetition, same model and prefix (negative = the second is faster):", "",
             "| Model | Prefix | Pair | First token s, median difference | Repetitions where the second was faster | Wall s, median difference |", "|---|---|---|---|---|---|"]
    for role in MODEL_ROLES:
        for prefix in PREFIXES:
            for a_, b_ in (("cold", "warm"), ("none", "warm"), ("none", "cold")):
                d1 = paired(rows, role, prefix, a_, b_, "first_text") or paired(rows, role, prefix, a_, b_, "first_delta")
                d2 = paired(rows, role, prefix, a_, b_, "wall")
                if d1:
                    diffs.append("| %s | %s | %s to %s | %+.2f | %d of %d | %s |" % (
                        names[role], prefix, STATE_LABEL[a_].split(" (")[0], STATE_LABEL[b_].split(" (")[0], statistics.median(d1),
                        sum(1 for x in d1 if x < 0), len(d1), "n/a" if not d2 else "%+.2f" % statistics.median(d2)))
    read = ["", "Reading rule (fixed before the run): the headline is warm against no cache; a saving is seen when warm was faster in at least 8 of the 10 paired repetitions. The stricter rule also needs warm faster than cold in at least 8.", "",
            "| Model | Prefix | Headline: warm faster than no cache | Stricter: also faster than cold |", "|---|---|---|---|"]
    for role in MODEL_ROLES:
        for prefix in PREFIXES:
            dn = paired(rows, role, prefix, "none", "warm", "first_text") or paired(rows, role, prefix, "none", "warm", "first_delta")
            dc = paired(rows, role, prefix, "cold", "warm", "first_text") or paired(rows, role, prefix, "cold", "warm", "first_delta")
            if dn:
                h, st, (a_, n_, b_, m_) = reading(dn, dc)
                read.append("| %s | %s | %s (%d of %d) | %s (%d of %d) |" % (names[role], prefix, "seen" if h else "not seen", a_, n_,
                                                                          "seen" if st else "not seen", b_, m_))
    diffs += read
    failed = [r for c in cs.values() for r in c["failed"]]
    fl = ["", "Requests that failed their state check (left out of the medians): %d of %d." % (len(failed), len(rows))]
    fl += ["- %s %s rep %d %s: %s" % (names[r["role"]], r["prefix"], r["rep"], r["state"], r["why"]) for r in failed[:30]]
    text = "\n".join(lines + diffs + fl) + "\n\n" + NOTE + "\n"
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "cache-timing-table.md"), "w", encoding="utf-8").write(text)
    for key, title, xlabel, fname, nd in (("first_text", "Time to first token, by cache state", "Seconds to the first token (median)", "cache-timing-first-token.svg", 2),
                                          ("wall", "Total time, by cache state", "Seconds per request (median)", "cache-timing-wall.svg", 2),
                                          ("tps", "Output tokens per second, by cache state", "Output tokens per second after the first token (median)", "cache-timing-tps.svg", 1)):
        open(os.path.join(out, fname), "w", encoding="utf-8").write(states_chart(cs, key, title, xlabel, nd))
    print(text)


def states_chart(cs, key, title, xlabel, nd):
    groups = [(role, prefix) for role in MODEL_ROLES for prefix in PREFIXES if any((role, prefix, s) in cs for s in STATES)]
    names = {"opus": "Opus", "sonnet": "Sonnet", "fable": "Fable"}
    grp = 3 * 16 + 14
    top, bottom = 94, 94 + grp * len(groups)
    vals = [metric(c, key)[1] for c in cs.values() if c["rows"] and metric(c, key)[1] is not None]
    if not vals:
        vals = [metric(c, "first_delta")[1] for c in cs.values() if c["rows"]] if key == "first_text" else [1.0]
    grid, X = brt.axis(brt.nice_max(max(vals) * 1.15), top, bottom, xlabel)
    legend = "".join('<rect x="%d" y="64" width="12" height="12" fill="%s"/><text x="%d" y="75" font-size="12">%s</text>'
                     % (brt.LEFT + i * 190, STATE_COLOR[s], brt.LEFT + i * 190 + 18, STATE_LABEL[s]) for i, s in enumerate(STATES))
    body = [grid]
    for i, (role, prefix) in enumerate(groups):
        y = top + i * grp
        body.append(brt.label_at(y + 28, "%s %s" % (names[role], prefix)))
        for j, state in enumerate(STATES):
            c = cs.get((role, prefix, state))
            if not c or not c["rows"]:
                continue
            v = metric(c, key)[1] if metric(c, key)[1] is not None else (metric(c, "first_delta")[1] if key == "first_text" else None)
            if v is None:
                continue
            yy = y + 4 + j * 17
            body.append('<rect x="%d" y="%d" width="%.1f" height="14" rx="2" fill="%s"/>' % (brt.LEFT, yy, X(v) - brt.LEFT, STATE_COLOR[state]))
            body.append('<text x="%.1f" y="%d" font-size="11" font-weight="600">%.*f</text>' % (X(v) + 5, yy + 11, nd, v))
    saved = brt.NOTE
    brt.NOTE = CHART_NOTE
    try:
        return brt.frame(title, "10 repetitions per cell, one request at a time, a different question in each state.", bottom + 70, "\n".join(body) + "\n", legend)
    finally:
        brt.NOTE = saved


# ------------------------------------------------------------------ self test
def selftest(inject_fault=False):
    claims = mb.EVAL_CLAIMS
    sched = schedule(10, claims)
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print("%-4s %-44s got %s want %s" % ("PASS" if good else "FAIL", name, got, want))
    check("sets", len(sched), 10 * 2 * 3)
    check("requests", 3 * len(sched), 180)
    check("three different claims in every set", all(len(set(s["claims"].values())) == 3 for s in sched), True)
    check("cold always before warm", all(s["order"].index("cold") < s["order"].index("warm") for s in sched), True)
    per = {(r, p): sum(1 for s in sched if s["role"] == r and s["prefix"] == p) for r in MODEL_ROLES for p in PREFIXES}
    check("10 sets per model and prefix", set(per.values()), {10})
    seen = {st: {} for st in STATES}
    for s in sched:
        for st, cid in s["claims"].items():
            seen[st][cid] = seen[st].get(cid, 0) + 1
    spread = {st: (min(seen[st].values()), max(seen[st].values()), len(seen[st])) for st in STATES}
    print("     claims per state (min, max, how many distinct):", spread)
    check("every state sees at least 8 distinct claims", all(v[2] >= 8 for v in spread.values()), True)
    first_orders = {tuple(s["order"]) for s in sched}
    check("two alternating orders", len(first_orders), 2)
    check("model order rotates", len({tuple(rotated(MODEL_ROLES, r)) for r in range(3)}), 3)
    check("state check: cold ok", check_state("cold", {"input_tokens": 4, "cache_creation_input_tokens": 13000, "cache_read_input_tokens": 0})[0], True)
    check("state check: warm ok", check_state("warm", {"input_tokens": 4, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 13000})[0], True)
    check("state check: none ok", check_state("none", {"input_tokens": 13000})[0], True)
    check("state check: cold that read fails", check_state("cold", {"input_tokens": 4, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 13000})[0], False)
    check("state check: warm that wrote fails", check_state("warm", {"input_tokens": 4, "cache_creation_input_tokens": 13000, "cache_read_input_tokens": 0})[0], False)
    check("state check: none with a read fails", check_state("none", {"input_tokens": 100, "cache_read_input_tokens": 12900})[0], False)
    check("tokens per second", round(tokens_per_second(101, 5.0, 1.0), 2), 25.0)
    check("tokens per second without text", tokens_per_second(100, 5.0, None), None)
    check("quartiles", quartiles([1, 2, 3, 4, 5]), (2.0, 3, 4.0))
    check("reading rule: 8 of 10 faster than no cache is the headline", reading([-1] * 8 + [1, 1], [-1] * 4 + [1] * 6)[:2], (True, False))
    check("reading rule: 7 of 10 is not seen", reading([-1] * 7 + [1] * 3, [-1] * 10)[:2], (False, False))
    check("reading rule: both at 8 is the stricter reading", reading([-1] * 9 + [1], [-1] * 8 + [1] * 2)[:2], (True, True))
    b0 = build_body("m", "13k", "n", claims[0], "none", "")
    b1 = build_body("m", "13k", "n", claims[0], "warm", "")
    b2 = build_body("m", "long", "n", claims[0], "cold", "LEDGER")
    check("no cache: no cache_control anywhere", "cache_control" in json.dumps(b0), False)
    check("warm: breakpoint on the last system block", b1["system"][-1].get("cache_control"), {"type": "ephemeral"})
    check("long: ledger is the last system block and carries the breakpoint", (b2["system"][-1]["text"].startswith("Historical"), "cache_control" in b2["system"][-1], "cache_control" in b2["system"][0]), (True, True, False))
    check("the prefix is the same in all three states", json.dumps(b0["system"][0]["text"]) == json.dumps(b1["system"][0]["text"]), True)
    if inject_fault:
        check("injected fault (must FAIL)", 1, 2)
    try:
        mb.http("GET", mb.API + "/models", {})
        check("network refused while not armed", "ran", "refused")
    except RuntimeError:
        check("network refused while not armed", "refused", "refused")
    print("selftest", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true")
    g.add_argument("--selftest-fault", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--estimate", action="store_true")
    g.add_argument("--live", action="store_true")
    g.add_argument("--report", metavar="DIR")
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--models", default=os.path.join(HERE, "models.json"))
    ap.add_argument("--ceiling-usd", type=float, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--smoke", action="store_true", help="live: one set (Sonnet, 13k prefix, repetition 1) to check the request shape")
    ap.add_argument("--thinking", choices=["disabled", "omit"], default="disabled")
    ap.add_argument("--tool-choice", choices=["none", "omit"], default="none")
    a = ap.parse_args()
    if a.selftest or a.selftest_fault:
        return selftest(inject_fault=a.selftest_fault)
    models = mb.load_models(a.models)
    if a.report:
        report(a.report, a.out or a.report)
        return 0
    if a.dry_run:
        dry_run(models, a.reps, mb.EVAL_CLAIMS)
        return 0
    if a.estimate:
        print(estimate(models, a.reps)[0])
        return 0
    if a.ceiling_usd is None or not a.out:
        raise SystemExit("--live needs --ceiling-usd and --out")
    run_live(a, models, mb.EVAL_CLAIMS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
