#!/usr/bin/env python3
"""Builds the results table and the charts from the raw records, in one command, standard library only.

usage: build_results_table.py RESULTS_DIR [--out REPORTS_DIR]

RESULTS_DIR holds trials-*.jsonl and, for a streamed run, requests-*.jsonl. arms.json maps arm ids to the short labels used
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
import glob
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
FAMILY_COLOR = {"Opus": "#3b6ea5", "Sonnet": "#2f8f6b", "Fable": "#c0702a"}
STACK = [("uncached input", "#8c97a3"), ("cache write", "#e0a030"), ("cache read", "#3b8f6b"), ("output", "#5b4aa5")]


def load(folder):
    trials, requests = [], []
    for f in sorted(glob.glob(os.path.join(folder, "trials-*.jsonl"))):
        trials += [json.loads(x) for x in open(f, encoding="utf-8") if x.strip()]
    for f in sorted(glob.glob(os.path.join(folder, "requests-*.jsonl"))):
        requests += [json.loads(x) for x in open(f, encoding="utf-8") if x.strip()]
    return trials, requests


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def fmt(x, nd=2):
    return "n/a" if x is None else "%.*f" % (nd, x)


def cost_parts(r):
    """The four components of one request's cost, by the notebook's multipliers (cache write 1.25x for 5 minutes and 2x for
    1 hour, cache read 0.10x), in dollars."""
    u, p = r["usage"], PRICES[r["model"]]
    cc = u.get("cache_creation") or {}
    w5 = cc.get("ephemeral_5m_input_tokens", u.get("cache_creation_input_tokens", 0) or 0)
    w1 = cc.get("ephemeral_1h_input_tokens", 0)
    pin, pout = p["in"] / 1e6, p["out"] / 1e6
    return [(u.get("input_tokens") or 0) * pin, (w5 * 1.25 + w1 * 2.0) * pin,
            (u.get("cache_read_input_tokens") or 0) * 0.10 * pin, (u.get("output_tokens") or 0) * pout]


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


def table(rows):
    timed = any(r["timed"] for r in rows)
    head = ["Arm", "Trials", "$ per task"]
    if timed:
        head += ["Wall s per claim", "Wall s per request", "First event s, first / later turns",
                 "First content s, first / later turns", "First text s, first / later turns"]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        cells = [r["label"], r["passes"], "%.4f" % r["cost"]]
        if timed:
            cells += [fmt(r["claim_wall"]), fmt(r["req_wall"])]
            cells += ["%s / %s" % (fmt(r[k + "_first"]), fmt(r[k + "_later"])) for k in ("event", "content", "text")]
        out.append("| " + " | ".join(cells) + " |")
    return ("\n".join(out) + "\n\n" + NOTE + " Times are medians over all requests of the arm; wall time per claim runs "
            "from a claim's first request to its verdict.\n")


# ------------------------------------------------------------------ the charts (hand-written SVG)
W, LEFT, RIGHT, ROW = 900, 190, 90, 30


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def frame(title, subtitle, height, body, legend=""):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="%s">\n'
            '<title>%s</title>\n<desc>%s</desc>\n<rect width="%d" height="%d" fill="#fbfaf7"/>\n'
            '<g font-family="system-ui, -apple-system, Helvetica, Arial, sans-serif" fill="#1d2430">\n'
            '<text x="20" y="30" font-size="19" font-weight="700">%s</text>\n'
            '<text x="20" y="52" font-size="13" fill="#5a6472">%s</text>\n%s%s'
            '<text x="20" y="%d" font-size="12" fill="#5a6472">%s</text>\n</g>\n</svg>\n'
            % (W, height, W, height, esc(title), esc(title), esc(subtitle), W, height, esc(title), esc(subtitle), legend, body,
               height - 14, esc(NOTE)))


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
    grid, X = axis(nice_max(max(r["cost"] for r in rows) * 1.12), top, bottom, "Cost per task (US$, notebook formula)")
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
    grid, X = axis(nice_max(max(sum(r["parts"]) for r in rows) * 1.12), top, bottom, "Cost per task (US$, notebook formula)")
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
              'first turn of a claim (a cache write for cached arms)</text>'
              '<rect x="%d" y="64" width="12" height="12" fill="#667" fill-opacity="0.45"/>'
              '<text x="%d" y="75" font-size="12">later turns</text>' % (LEFT, LEFT + 18, LEFT + 400, LEFT + 418))
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
    out = os.path.join(HERE, "reports")
    if "--out" in argv:
        i = argv.index("--out")
        out = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 1:
        sys.exit(__doc__)
    rows = collect(argv[0])
    os.makedirs(out, exist_ok=True)
    text = table(rows)
    open(os.path.join(out, "results-table.md"), "w", encoding="utf-8").write(text)
    print(text)
    sub = "10 claims per trial, 2 trials per arm."
    charts = {
        "cost-per-task.svg": bars_chart(rows, "Cost per task", sub),
        "cost-breakdown.svg": stacked_chart(rows, "What the cost per task is made of", sub),
        "time-per-claim.svg": claim_chart(rows, "Time per claim", sub + " Dots mark each trial's own median."),
        "time-to-first-event.svg": first_event_chart(rows, "Time to first event", sub + " First turns and later turns side by side."),
    }
    for name, svg in charts.items():
        open(os.path.join(out, name), "w", encoding="utf-8").write(svg)
    print("wrote results-table.md and %d charts into %s" % (len(charts), out), file=sys.stderr)


if __name__ == "__main__":
    main()
