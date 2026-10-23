#!/usr/bin/env python3
"""Builds the results table and the charts from the raw records, in one command, standard library only.

usage: build_results_table.py RESULTS_DIR [--out REPORTS_DIR] [--measure cost|timing|both]   (default both)
       build_results_table.py --selftest | --selftest-fault

--measure chooses what is tabled and charted: cost, timing or both. Cost is always recorded in the records.

RESULTS_DIR holds trials*.jsonl (the benchmark script writes trials.jsonl) and, for a streamed run, requests*.jsonl. arms.json maps arm ids to the short labels used
everywhere. One row per arm: pass counts per trial, cost per task by the notebook's formula, and for a streamed run the
median wall seconds per claim and per request and the median time to first event, first content and first text, for first
turns and later turns separately.

Writes, into REPORTS_DIR (default: reports next to this file) and prints the table:
  results-table.md          the table and its note
  cost-per-task.svg         bar chart of cost per task
  cost-breakdown.svg        stacked bar of what the cost is made of
  time-per-claim.svg        median wall seconds per claim, with each trial's value marked
  time-to-first-event.svg   median time to first event, first turns and later turns side by side
"""
import fnmatch
import glob
import importlib.util
import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARMS = json.load(open(os.path.join(HERE, "arms.json"), encoding="utf-8"))["arms"]
PRICES = json.load(open(os.path.join(HERE, "models.json"), encoding="utf-8"))["prices"]
NOTE = ("Models: Opus 5.5, Sonnet 5.5, Fable 5.1, the latest versions. high, medium, low = effort level. "
        "cache = automatic prompt cache; no cache = none.")
COST_LABEL = "Cost per task (US$, notebook formula)"     # the axis label; charts_for sets it from the rows
FIRST_TURN_LABEL = "first turn of a claim (a cache write for cached arms)"
FAMILY_COLOR = {"Opus": "#3b6ea5", "Sonnet": "#2f8f6b", "Fable": "#c0702a", "Gemini": "#8a4fa0"}
STACK = [("uncached input", "#8c97a3"), ("cache write", "#e0a030"), ("cache read", "#3b8f6b"), ("output", "#5b4aa5")]


TRIALS_GLOB = "trials*.jsonl"      # matches trials.jsonl, which model_benchmark.py writes, and trials-<name>.jsonl
REQUESTS_GLOB = "requests*.jsonl"


def load(folder):
    trials, requests = [], []
    for f in sorted(glob.glob(os.path.join(folder, TRIALS_GLOB))):
        trials += [json.loads(x) for x in open(f, encoding="utf-8") if x.strip()]
    for f in sorted(glob.glob(os.path.join(folder, REQUESTS_GLOB))):
        requests += [json.loads(x) for x in open(f, encoding="utf-8") if x.strip()]
    return trials, requests


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def fmt(x, nd=2):
    return "n/a" if x is None else "%.*f" % (nd, x)


def cost_parts(r):
    """The four components of one request's cost, by the notebook's multipliers (cache write 1.25x for 5 minutes and 2x for
    1 hour, cache read 0.10x), in dollars. The write rule is the one model_benchmark.usage_cost uses: the 5-minute and
    1-hour counts when either is non-zero, otherwise the flat cache_creation_input_tokens. Advisor iterations and batch
    pricing are not split into parts, so a request that has them is refused."""
    u = r["usage"]
    if "promptTokenCount" in u:
        return gemini_cost_parts(r)
    p = PRICES[r["model"]]
    if any(it.get("type") == "advisor_message" for it in u.get("iterations") or []):
        raise ValueError("advisor iterations are not split into cost parts (request %s)" % r.get("tag"))
    cc = u.get("cache_creation") or {}
    w5 = cc.get("ephemeral_5m_input_tokens", 0) or 0
    w1 = cc.get("ephemeral_1h_input_tokens", 0) or 0
    if not (w5 or w1):
        w5 = u.get("cache_creation_input_tokens") or 0
    pin, pout = p["in"] / 1e6, p["out"] / 1e6
    return [(u.get("input_tokens") or 0) * pin, (w5 * 1.25 + w1 * 2.0) * pin,
            (u.get("cache_read_input_tokens") or 0) * 0.10 * pin, (u.get("output_tokens") or 0) * pout]


def _gemini():
    """gemini_benchmark, imported on first use so that an Anthropic-only run never loads it."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import gemini_benchmark
    return gemini_benchmark


def gemini_cost_parts(r):
    """The four components for a Gemini request (records from gemini_benchmark.py): uncached input, cache write (Gemini
    reports none, so 0), cached input, and output including thinking tokens, at the list prices in gemini_models.json.
    The split of the prompt into cached and uncached tokens is gemini_benchmark.cache_split, so both files agree."""
    gb = _gemini()
    u, gm = r["usage"], gb.load_gemini_models()
    prices = next((gm["prices"][role] for role, m in gm["models"].items() if m["id"] == r["model"]), None)
    if prices is None:
        raise ValueError("no price in gemini_models.json for model %s (request %s)" % (r["model"], r.get("tag")))
    uncached, cached, _ = gb.cache_split(u)
    uncached += u.get("toolUsePromptTokenCount") or 0
    out = (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)
    return [uncached * prices["in"] / 1e6, 0.0, cached * prices["cached_in"] / 1e6, out * prices["out"] / 1e6]


GEMINI_NOTE = ("Gemini arms: high, medium, low = thinking level. The Gemini cache is implicit, on for every project and not "
               "switchable by a user, so there is no no-cache arm; the cached share is what the usage block reported.")


def note_for(rows):
    """The note under the table and charts. Anthropic-only results keep NOTE exactly; Gemini rows add GEMINI_NOTE."""
    gem = [r for r in rows if r["family"] == "Gemini"]
    if not gem:
        return NOTE
    if len(gem) == len(rows):
        return GEMINI_NOTE
    return NOTE + " " + GEMINI_NOTE


# ------------------------------------------------------------------ the numbers
def collect(folder):
    trials, requests = load(folder)
    rows = []
    for a in ARMS:
        ts = sorted([t for t in trials if t["config"] == a["id"]], key=lambda t: t["trial"])
        if not ts:
            continue
        rq = [r for r in requests if r["tag"].split()[0] == a["id"]]
        n_tasks = sum(t["n"] for t in ts)
        parts = [sum(cost_parts(r)[i] for r in rq) / n_tasks for i in range(4)] if rq else None
        timed = [dict(r["timing"], first=r["tag"].split()[-1] == "t1") for r in rq if r.get("timing")]
        row = {"label": a["label"], "family": a["label"].split()[0],
               "passes": ", ".join("%d/%d" % (t["correct"], t["n"]) for t in ts),
               "cost": statistics.mean(t["per_task_notebook"] for t in ts), "parts": parts, "timed": bool(timed),
               "claim_wall": med([w for t in ts for w in (t.get("claim_wall_s") or {}).values()]),
               "claim_wall_by_trial": [med(list((t.get("claim_wall_s") or {}).values())) for t in ts],
               "req_wall": med([x["wall_s"] for x in timed])}
        for key, name in (("ttfb_s", "event"), ("first_delta_s", "content"), ("first_text_s", "text")):
            row[name + "_first"] = med([x[key] for x in timed if x["first"]])
            row[name + "_later"] = med([x[key] for x in timed if not x["first"]])
        rows.append(row)
    return rows


def table(rows, measure="both"):
    """measure: cost, timing or both. Timing columns need streamed records; without them the table says so."""
    cost, timing = measure in ("cost", "both"), measure in ("timing", "both")
    timed = timing and any(r["timed"] for r in rows)
    head = ["Arm", "Trials"] + (["$ per task"] if cost else [])
    if timed:
        head += ["Wall s per claim", "Wall s per request", "First event s, first / later turns",
                 "First content s, first / later turns", "First text s, first / later turns"]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        cells = [r["label"], r["passes"]] + (["%.4f" % r["cost"]] if cost else [])
        if timed:
            cells += [fmt(r["claim_wall"]), fmt(r["req_wall"])]
            cells += ["%s / %s" % (fmt(r[k + "_first"]), fmt(r[k + "_later"])) for k in ("event", "content", "text")]
        out.append("| " + " | ".join(cells) + " |")
    note = note_for(rows) + (" Times are medians over all requests of the arm; wall time per claim runs from a claim's first request to "
                   "its verdict." if timed else "")
    if timing and not timed:
        note += " The records hold no timing: nothing was streamed."
    return "\n".join(out) + "\n\n" + note + "\n"


def labels_for(rows):
    """(cost axis label, first-turn legend text) for these rows. Claude rows: the notebook's formula and its cache write.
    Gemini rows: Vertex list prices from the usage block and no cache write. Both kinds together: neither claim is made."""
    gem = [r["family"] == "Gemini" for r in rows]
    if gem and all(gem):
        return "Cost per task (US$, list prices)", "first turn of a claim"
    if any(gem):
        return "Cost per task (US$)", "first turn of a claim"
    return "Cost per task (US$, notebook formula)", "first turn of a claim (a cache write for cached arms)"


def charts_for(rows, measure="both"):
    global NOTE, COST_LABEL, FIRST_TURN_LABEL
    saved = NOTE, COST_LABEL, FIRST_TURN_LABEL
    NOTE = note_for(rows)
    COST_LABEL, FIRST_TURN_LABEL = labels_for(rows)
    try:
        return _charts_for(rows, measure)
    finally:
        NOTE, COST_LABEL, FIRST_TURN_LABEL = saved


def _charts_for(rows, measure):
    sub = "10 claims per trial, 2 trials per arm."
    out = {}
    if measure in ("cost", "both"):
        out["cost-per-task.svg"] = bars_chart(rows, "Cost per task", sub)
        out["cost-breakdown.svg"] = stacked_chart(rows, "What the cost per task is made of", sub)
    if measure in ("timing", "both") and any(r["timed"] for r in rows):
        out["time-per-claim.svg"] = claim_chart(rows, "Time per claim", sub + " Dots mark each trial's own median.")
        out["time-to-first-event.svg"] = first_event_chart(rows, "Time to first event", sub + " First turns and later turns side by side.")
    return out


def selftest(inject_fault=False):
    """Checks the three modes on made-up rows: what each shows, and what it leaves out."""
    base = {"label": "Opus high no cache", "family": "Opus", "passes": "10/10, 10/10", "cost": 0.2, "parts": [0.18, 0, 0, 0.02],
            "claim_wall": 11.0, "claim_wall_by_trial": [10.5, 11.5], "req_wall": 3.0, "event_first": 1.5, "event_later": 1.4,
            "content_first": 1.6, "content_later": 2.0, "text_first": None, "text_later": 2.5}
    timed = [dict(base, timed=True)]
    plain = [dict(base, timed=False)]
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print("%-4s %-52s got %s want %s" % ("PASS" if good else "FAIL", name, got, want))
    check("cost: table has a cost column and no timing", ("$ per task" in table(timed, "cost"), "Wall s per claim" in table(timed, "cost")), (True, False))
    check("timing: table has timing and no cost column", ("$ per task" in table(timed, "timing"), "Wall s per claim" in table(timed, "timing")), (False, True))
    check("both: table has both", ("$ per task" in table(timed, "both"), "Wall s per claim" in table(timed, "both")), (True, True))
    check("timing without streamed records says so", "hold no timing" in table(plain, "timing"), True)
    check("cost: only the two cost charts", sorted(charts_for(timed, "cost")), ["cost-breakdown.svg", "cost-per-task.svg"])
    check("timing: only the two time charts", sorted(charts_for(timed, "timing")), ["time-per-claim.svg", "time-to-first-event.svg"])
    check("both: all four charts", len(charts_for(timed, "both")), 4)
    check("both without timing: two charts", len(charts_for(plain, "both")), 2)
    # The parts must add up to the script's own cost on the edge cases where the two rules once differed.
    spec = importlib.util.spec_from_file_location("model_benchmark", os.path.join(HERE, "model_benchmark.py"))
    mb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mb)
    model = next(iter(PRICES))
    edge = [{"input_tokens": 10, "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 5, "output_tokens": 7},
            {"input_tokens": 10, "cache_creation_input_tokens": 1000, "cache_creation": {"ephemeral_5m_input_tokens": 0,
             "ephemeral_1h_input_tokens": 0}, "output_tokens": 7},
            {"input_tokens": 10, "cache_creation_input_tokens": 1000, "cache_creation": {"ephemeral_5m_input_tokens": 400,
             "ephemeral_1h_input_tokens": 600}, "cache_read_input_tokens": 50, "output_tokens": 7}]
    gaps = [abs(sum(cost_parts({"usage": u, "model": model})) - mb.usage_cost(u, model, {"prices": PRICES})) for u in edge]
    check("cost parts add up to usage_cost on the edge cases", max(gaps) < 1e-9, True)
    # Gemini records: the parts add up to gemini_benchmark's own cost, and the Gemini arms in arms.json match its CONFIGS.
    gb = _gemini()
    gm = gb.load_gemini_models()
    role, meta = next(iter(gm["models"].items()))
    usage = {"promptTokenCount": 10000, "cachedContentTokenCount": 6000, "candidatesTokenCount": 300, "thoughtsTokenCount": 700}
    parts = cost_parts({"usage": usage, "model": meta["id"]})
    check("gemini cost parts add up to gemini_cost", abs(sum(parts) - gb.gemini_cost(usage, gm["prices"][role])[0]) < 1e-12, True)
    arm_ids = {a["id"]: a for a in ARMS}
    check("every gemini_benchmark arm is in arms.json with its label, not default",
          [(c["id"] in arm_ids and arm_ids[c["id"]]["label"] == c["label"] and not arm_ids[c["id"]]["default"]) for c in gb.CONFIGS],
          [True] * len(gb.CONFIGS))
    check("a table of Gemini rows has the Gemini note and not the Anthropic models line",
          (GEMINI_NOTE in note_for([dict(base, family="Gemini")]), "Opus 5.5" in note_for([dict(base, family="Gemini")])), (True, False))
    check("a table of Anthropic rows keeps the note unchanged", note_for([base]) == NOTE, True)
    check("labels: Claude rows keep the notebook formula and the cache write; Gemini rows say list prices and no cache write",
          (labels_for([base]), labels_for([dict(base, family="Gemini")])),
          (("Cost per task (US$, notebook formula)", "first turn of a claim (a cache write for cached arms)"),
           ("Cost per task (US$, list prices)", "first turn of a claim")))
    long_note = "word " * 60
    lines = wrap_note(long_note.strip())
    check("footer note: every wrapped line fits and no word is lost", (max(len(x) for x in lines) <= NOTE_WRAP, " ".join(lines) == long_note.strip()), (True, True))
    check("footer note: the Claude note stays on one line, the Gemini note wraps", (len(wrap_note(NOTE)), len(wrap_note(GEMINI_NOTE)) > 1), (1, True))
    # The file names model_benchmark.py writes (trials.jsonl, requests.jsonl) and the ones kept in results/ must be found.
    check("reads the file names the benchmark script writes",
          [fnmatch.fnmatch(n, g) for n, g in (("trials.jsonl", TRIALS_GLOB), ("requests.jsonl", REQUESTS_GLOB))], [True, True])
    check("reads trials-<name>.jsonl and requests-<name>.jsonl too",
          [fnmatch.fnmatch(n, g) for n, g in (("trials-run1.jsonl", TRIALS_GLOB), ("requests-run1.jsonl", REQUESTS_GLOB))], [True, True])
    if inject_fault:
        check("injected fault (must FAIL)", 1, 2)
    print("selftest", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


# ------------------------------------------------------------------ the charts (hand-written SVG)
W, LEFT, RIGHT, ROW = 900, 190, 90, 30


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


NOTE_WRAP = 150          # characters per footer line at 12 px in the 900 px frame; the Claude note (146) fits on one line
NOTE_LINE = 15           # pixels between footer lines


def wrap_note(text, width=NOTE_WRAP):
    """The footer note split at spaces into lines of at most width characters (one line when it fits)."""
    lines, cur = [], ""
    for word in text.split(" "):
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = word if not cur else cur + " " + word
    return lines + [cur] if cur else lines or [""]


def frame(title, subtitle, height, body, legend=""):
    lines = wrap_note(NOTE)
    foot = "".join('<text x="20" y="%d" font-size="12" fill="#5a6472">%s</text>\n' % (height - 14 + i * NOTE_LINE, esc(ln))
                   for i, ln in enumerate(lines))
    height += (len(lines) - 1) * NOTE_LINE
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="%s">\n'
            '<title>%s</title>\n<desc>%s</desc>\n<rect width="%d" height="%d" fill="#fbfaf7"/>\n'
            '<g font-family="system-ui, -apple-system, Helvetica, Arial, sans-serif" fill="#1d2430">\n'
            '<text x="20" y="30" font-size="19" font-weight="700">%s</text>\n'
            '<text x="20" y="52" font-size="13" fill="#5a6472">%s</text>\n%s%s%s</g>\n</svg>\n'
            % (W, height, W, height, esc(title), esc(title), esc(subtitle), W, height, esc(title), esc(subtitle), legend, body,
               foot))


def nice_step(raw):
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= raw:
            return m * mag
    return 10 * mag


def nice_max(v):
    step = nice_step(v / 5.0)
    return step * math.ceil(v / step - 1e-9)


def tick_label(v, step):
    return "%.2f" % v if step < 0.1 else "%.1f" % v if step < 1 else "%d" % v


def axis(xmax, top, bottom, label):
    """Vertical grid lines and the bottom axis title for a horizontal bar chart; returns (svg, x_of_value)."""
    span = W - LEFT - RIGHT
    step = nice_step(xmax / 5.0)
    out, v = [], 0.0
    while v <= xmax + 1e-9:
        x = LEFT + span * v / xmax
        out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#dcd8cf" stroke-width="1"/>' % (x, top, x, bottom))
        out.append('<text x="%.1f" y="%d" font-size="11" text-anchor="middle" fill="#5a6472">%s</text>'
                   % (x, bottom + 16, tick_label(v, step)))
        v += step
    out.append('<text x="%.1f" y="%d" font-size="12" text-anchor="middle" fill="#5a6472">%s</text>'
               % (LEFT + span / 2, bottom + 36, esc(label)))
    return "\n".join(out) + "\n", lambda val: LEFT + span * val / xmax


def label_at(y, text):
    return '<text x="%d" y="%d" font-size="13" text-anchor="end">%s</text>' % (LEFT - 10, y, esc(text))


def bars_chart(rows, title, subtitle):
    top, bottom = 70, 70 + ROW * len(rows)
    grid, X = axis(nice_max(max(r["cost"] for r in rows) * 1.12), top, bottom, COST_LABEL)
    body = [grid]
    for i, r in enumerate(rows):
        y = top + i * ROW
        body.append(label_at(y + 19, r["label"]))
        body.append('<rect x="%d" y="%d" width="%.1f" height="20" rx="3" fill="%s"/>'
                    % (LEFT, y + 5, X(r["cost"]) - LEFT, FAMILY_COLOR.get(r["family"], "#667")))
        body.append('<text x="%.1f" y="%d" font-size="12" font-weight="600">%.4f</text>' % (X(r["cost"]) + 6, y + 19, r["cost"]))
    return frame(title, subtitle, bottom + 70, "\n".join(body) + "\n")


def stacked_chart(rows, title, subtitle):
    rows = [r for r in rows if r["parts"]]
    top, bottom = 94, 94 + ROW * len(rows)
    grid, X = axis(nice_max(max(sum(r["parts"]) for r in rows) * 1.12), top, bottom, COST_LABEL)
    legend = "".join('<rect x="%d" y="64" width="12" height="12" fill="%s"/><text x="%d" y="75" font-size="12">%s</text>'
                     % (LEFT + i * 150, c, LEFT + i * 150 + 18, n) for i, (n, c) in enumerate(STACK))
    body = [grid]
    for i, r in enumerate(rows):
        y, x = top + i * ROW, LEFT
        body.append(label_at(y + 19, r["label"]))
        for part, (_, color) in zip(r["parts"], STACK):
            w = X(part) - LEFT
            if w > 0.2:
                body.append('<rect x="%.1f" y="%d" width="%.1f" height="20" fill="%s"/>' % (x, y + 5, w, color))
            x += w
        body.append('<text x="%.1f" y="%d" font-size="12" font-weight="600">%.4f</text>' % (x + 6, y + 19, sum(r["parts"])))
    return frame(title, subtitle, bottom + 70, "\n".join(body) + "\n", legend)


def claim_chart(rows, title, subtitle):
    rows = [r for r in rows if r["claim_wall"] is not None]
    top, bottom = 94, 94 + ROW * len(rows)
    allv = [v for r in rows for v in r["claim_wall_by_trial"] + [r["claim_wall"]] if v]
    grid, X = axis(nice_max(max(allv) * 1.12), top, bottom, "Seconds per claim, first request to verdict (median)")
    legend = ('<rect x="%d" y="64" width="12" height="12" fill="#667"/><text x="%d" y="75" font-size="12">median of both trials</text>'
              '<circle cx="%d" cy="70" r="5" fill="#fff" stroke="#1d2430" stroke-width="2"/>'
              '<text x="%d" y="75" font-size="12">median of one trial</text>' % (LEFT, LEFT + 18, LEFT + 190, LEFT + 202))
    body = [grid]
    for i, r in enumerate(rows):
        y = top + i * ROW
        body.append(label_at(y + 19, r["label"]))
        body.append('<rect x="%d" y="%d" width="%.1f" height="20" rx="3" fill="%s" fill-opacity="0.85"/>'
                    % (LEFT, y + 5, X(r["claim_wall"]) - LEFT, FAMILY_COLOR.get(r["family"], "#667")))
        marks = [v for v in r["claim_wall_by_trial"] if v]
        for v in marks:
            body.append('<circle cx="%.1f" cy="%d" r="5" fill="#fff" stroke="#1d2430" stroke-width="2"/>' % (X(v), y + 15))
        body.append('<text x="%.1f" y="%d" font-size="12" font-weight="600">%.1f</text>'
                    % (X(max([r["claim_wall"]] + marks)) + 12, y + 19, r["claim_wall"]))
    return frame(title, subtitle, bottom + 70, "\n".join(body) + "\n", legend)


def first_event_chart(rows, title, subtitle):
    rows = [r for r in rows if r["event_first"] is not None]
    grp = 2 * 16 + 14
    top, bottom = 94, 94 + grp * len(rows)
    vals = [r[k] for r in rows for k in ("event_first", "event_later") if r[k]]
    grid, X = axis(nice_max(max(vals) * 1.15), top, bottom, "Seconds from sending the request to the first server event (median)")
    legend = ('<rect x="%d" y="64" width="12" height="12" fill="#667"/><text x="%d" y="75" font-size="12">'
              '%s</text>'
              '<rect x="%d" y="64" width="12" height="12" fill="#667" fill-opacity="0.45"/>'
              '<text x="%d" y="75" font-size="12">later turns</text>' % (LEFT, LEFT + 18, esc(FIRST_TURN_LABEL), LEFT + 400, LEFT + 418))
    body = [grid]
    for i, r in enumerate(rows):
        y = top + i * grp
        body.append(label_at(y + 22, r["label"]))
        for j, (k, op) in enumerate((("event_first", 1.0), ("event_later", 0.45))):
            if r[k] is None:
                continue
            yy = y + 4 + j * 17
            body.append('<rect x="%d" y="%d" width="%.1f" height="14" rx="2" fill="%s" fill-opacity="%s"/>'
                        % (LEFT, yy, X(r[k]) - LEFT, FAMILY_COLOR.get(r["family"], "#667"), op))
            body.append('<text x="%.1f" y="%d" font-size="11" font-weight="600">%.2f</text>' % (X(r[k]) + 5, yy + 11, r[k]))
    return frame(title, subtitle, bottom + 70, "\n".join(body) + "\n", legend)


def main():
    argv = sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--selftest" in argv or "--selftest-fault" in argv:
        return selftest(inject_fault="--selftest-fault" in argv)
    out = os.path.join(HERE, "reports")
    if "--out" in argv:
        i = argv.index("--out")
        out = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    measure = "both"
    if "--measure" in argv:
        i = argv.index("--measure")
        measure = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
        if measure not in ("cost", "timing", "both"):
            sys.exit("--measure takes cost, timing or both")
    if len(argv) != 1:
        sys.exit(__doc__)
    if not glob.glob(os.path.join(argv[0], TRIALS_GLOB)):
        sys.exit("no %s in %s; nothing written" % (TRIALS_GLOB, argv[0]))
    rows = collect(argv[0])
    if not rows:
        sys.exit("no arm in %s matches arms.json; nothing written" % argv[0])
    text = table(rows, measure)
    charts = charts_for(rows, measure)
    os.makedirs(out, exist_ok=True)  # everything is built before anything is written
    open(os.path.join(out, "results-table.md"), "w", encoding="utf-8").write(text)
    print(text)
    for name, svg in charts.items():
        open(os.path.join(out, name), "w", encoding="utf-8").write(svg)
    print("wrote results-table.md and %d charts into %s (measure: %s)" % (len(charts), out, measure), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
