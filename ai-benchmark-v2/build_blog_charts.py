#!/usr/bin/env python3
"""Builds the charts for a post from the published raw records, standard library only: a value map (cost per task against time per claim,
one point per arm), the cache savings (cost with and without the prompt cache, for the agent task and for one request on a long prompt)
and, as a separate chart, the Gemini 3.8 Flash follow-up turn.

usage: build_blog_charts.py [--out DIR]     writes blog-charts.md, value-map.svg, cache-savings.svg and gemini-follow-up.svg (default reports/blog)
       build_blog_charts.py --selftest | --selftest-fault

Nothing is run again and no key is read. Every number comes from results/run1, results/gemini-flash-loop, results/cache-timing-sonnet and
results/gemini-flash-cache-timing, through the loaders the other builders use. Before anything is written, each number is compared with the
published tables and each ratio with the sentence that states it in the reports; one mismatch, or one label that overlaps another or leaves
the frame, and nothing is written. Charts are 640 units wide and no text is under 14.
"""
import json
import math
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_results_table as brt  # noqa: E402  (collect, the arms, the palette, the axis helpers)
import cache_timing as ct  # noqa: E402  (the Sonnet cache timing loaders and its reading rule)
import gemini_cache_timing as gct  # noqa: E402  (the Gemini ones)

AGENT_FOLDERS = ("results/run1", "results/gemini-flash-loop")
SONNET_FOLDER = "results/cache-timing-sonnet"
GEMINI_FOLDER = "results/gemini-flash-cache-timing"
EW = brt.EW
FONT = 14
INK, MUTED, GRID, PAPER = "#1d2430", "#5a6472", "#dcd8cf", "#fbfaf7"
NO_CACHE, COLD = ct.STATE_COLOR["none"], ct.STATE_COLOR["cold"]      # the cache timing charts' colours for no cache and for the write
TEXT_W, BOLD_W = 0.56, 0.62      # width of one character in units of the font size, wider than Helvetica so a wider font cannot overlap either
PRESETS = (("Opus", "Opus 5.5"), ("Sonnet", "Sonnet 5.5"))


# ------------------------------------------------------------------ the canvas: every text and every mark has a box
def overlaps(a, b, pad=1.5):
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] + pad and b[1] < a[3] + pad


class Canvas:
    """The pieces of one chart. Each text and each mark keeps a box, so a label that overlaps another or leaves the frame is found
    by problems() and not by looking, and place() picks the first spot for a label that is free."""

    def __init__(self, width, height):
        self.width, self.height = width, height
        self.parts, self.texts, self.marks = [], [], []

    def raw(self, svg):
        self.parts.append(svg)

    def mark(self, name, left, top, right, bottom):
        self.marks.append((name, (left, top, right, bottom)))

    @staticmethod
    def box(x, y, s, size, bold, anchor):
        w = len(s) * size * (BOLD_W if bold else TEXT_W)
        left = x - w / 2.0 if anchor == "middle" else x - w if anchor == "end" else x
        return left, y - 0.8 * size, left + w, y + 0.25 * size

    def text(self, x, y, s, size=FONT, bold=False, anchor="start", fill=None, backing=False):
        box = self.box(x, y, s, size, bold, anchor)
        self.texts.append((s, box))
        if backing:      # a pale patch so a gridline does not run through the letters
            self.parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" fill-opacity="0.85"/>'
                              % (box[0] - 2, box[1] - 1, box[2] - box[0] + 4, box[3] - box[1] + 2, PAPER))
        attrs = ' font-size="%d"' % size + (' font-weight="700"' if bold else "") + (' text-anchor="%s"' % anchor if anchor != "start" else "") \
            + (' fill="%s"' % fill if fill else "")
        self.parts.append('<text x="%.1f" y="%.1f"%s>%s</text>' % (x, y, attrs, brt.esc(s)))
        return box

    def fits(self, box):
        if box[0] < 2 or box[1] < 2 or box[2] > self.width - 2 or box[3] > self.height - 2:
            return False
        return not any(overlaps(box, b) for _, b in self.texts) and not any(overlaps(box, b, 0) for _, b in self.marks)

    def place(self, x, y, s, spots, size=FONT, bold=False, fill=None, backing=False):
        """Draws s at the first of the (dx, dy, anchor) spots around (x, y) where it overlaps nothing and stays in the frame."""
        for dx, dy, anchor in spots:
            if self.fits(self.box(x + dx, y + dy, s, size, bold, anchor)):
                return self.text(x + dx, y + dy, s, size, bold, anchor, fill, backing)
        raise ValueError("no room for %r near (%.0f, %.0f)" % (s, x, y))

    def line(self, name, x1, y1, x2, y2, color, width=2, opacity=1.0):
        self.parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%s" stroke-opacity="%s"/>'
                          % (x1, y1, x2, y2, color, width, opacity))
        self.sample(name, [(x1, y1), (x2, y2)])

    def sample(self, name, points):
        """Marks along a path (every 5 units), so a label that crosses it is found."""
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            n = max(1, int(math.hypot(x2 - x1, y2 - y1) / 5))
            for i in range(n + 1):
                x, y = x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n
                self.mark(name, x - 1, y - 1, x + 1, y + 1)

    def problems(self):
        out = []
        for i, (s, a) in enumerate(self.texts):
            if a[0] < 0 or a[1] < 0 or a[2] > self.width or a[3] > self.height:
                out.append("%r is outside the frame" % s)
            out += ["%r overlaps %r" % (s, s2) for s2, b in self.texts[i + 1:] if overlaps(a, b)]
            out += ["%r overlaps %s" % (s, name) for name, b in self.marks if overlaps(a, b, 0)]
        return out

    def svg(self, title, desc):
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="%s">\n'
                '<title>%s</title>\n<desc>%s</desc>\n<rect width="%d" height="%d" fill="%s"/>\n'
                '<g font-family="system-ui, -apple-system, Helvetica, Arial, sans-serif" fill="%s">\n%s\n</g>\n</svg>\n'
                % (self.width, self.height, self.width, self.height, brt.esc(title), brt.esc(title), brt.esc(desc), self.width,
                   self.height, PAPER, INK, "\n".join(self.parts)))


def arrow(c, name, x1, y1, x2, y2, color):
    """A line with a head at (x2, y2)."""
    c.line(name, x1, y1, x2, y2, color, 2.5)
    a = math.atan2(y2 - y1, x2 - x1)
    pts = [(x2, y2), (x2 - 11 * math.cos(a - 0.45), y2 - 11 * math.sin(a - 0.45)), (x2 - 11 * math.cos(a + 0.45), y2 - 11 * math.sin(a + 0.45))]
    c.raw('<polygon points="%s" fill="%s"/>' % (" ".join("%.1f,%.1f" % p for p in pts), color))


def passed(row):
    """Claims passed in each trial, as numbers: '10/10, 10/10' gives [10, 10]."""
    return [int(p.split("/")[0]) for p in row["passes"].split(", ")]


def gap(values):
    """The gap between the two trials of an arm as a share of their mean."""
    v = [x for x in values if x]
    return abs(v[0] - v[1]) / (sum(v[:2]) / 2.0) if len(v) >= 2 else None


# ------------------------------------------------------------------ the numbers, from the records
def agent_rows():
    return [r for d in AGENT_FOLDERS for r in brt.collect(os.path.join(HERE, d))]


def cache_pairs(rows):
    """[(model name, family, row without cache, row with cache)] for Opus 5.5 and Sonnet 5.5 at high effort."""
    by = {r["label"]: r for r in rows}
    return [(name, fam, by["%s high no cache" % fam], by["%s high cache" % fam]) for fam, name in PRESETS
            if "%s high no cache" % fam in by and "%s high cache" % fam in by]


def first_turns(folder):
    """(first turns of the claims in every arm with the automatic cache on, how many of them read nothing from the cache): the
    automatic cache did not carry from one claim to the next, so the first turn of every claim writes the prefix again."""
    ids = {a["id"] for a in brt.ARMS if a["id"].endswith("-cache")}
    _, requests = brt.load(folder)
    firsts = [r for r in requests if r["tag"].split()[0] in ids and r["tag"].split()[-1] == "t1"]
    return len(firsts), sum(1 for r in firsts if not (r["usage"].get("cache_read_input_tokens") or 0))


def agent_prompt_tokens(pairs):
    """(smallest, largest) prompt size in tokens over every request of the arms in pairs, from the records of run 1."""
    ids = {a["label"]: a["id"] for a in brt.ARMS}
    wanted = {ids[r["label"]] for _, _, n, c in pairs for r in (n, c)}
    _, requests = brt.load(os.path.join(HERE, AGENT_FOLDERS[0]))
    sizes = [(r["usage"].get("input_tokens") or 0) + (r["usage"].get("cache_creation_input_tokens") or 0) + (r["usage"].get("cache_read_input_tokens") or 0)
             for r in requests if r["tag"].split()[0] in wanted]
    return min(sizes), max(sizes)


def long_prompt(folder):
    """Sonnet 5.5 on the long prefix: mean cost per request in each state over the requests that passed their state check, the number
    of those, the median prompt size in tokens, and how many pairs warm was faster than no cache (the cache timing report's own rule)."""
    rows = ct.load_requests(folder)
    cells = ct.cells(rows)
    out = {"tokens": statistics.median(r["prefix_tokens"] for r in cells[("sonnet", "long", "none")]["rows"])}
    for state in ct.STATES:
        c = cells[("sonnet", "long", state)]
        out[state] = {"cost": statistics.mean(r["cost"] for r in c["rows"]), "ok": c["ok"], "n": c["n"]}
    d = ct.paired(rows, "sonnet", "long", "none", "warm", "first_text") or ct.paired(rows, "sonnet", "long", "none", "warm", "first_delta")
    out["faster"], out["pairs"] = sum(1 for x in d if x < 0), len(d)
    out["seen"] = ct.reading(d, [])[0]
    probe = ct.build_body("model", "long", "nonce", {"id": "CLM-000", "summary": "probe"}, "cold", "")     # the test's own request builder
    out["effort"], out["max_tokens"] = probe["output_config"]["effort"], probe["max_tokens"]
    out["tool_choice"] = (probe.get("tool_choice") or {}).get("type", "omitted")
    return out


def gemini_follow_up(folder):
    """Gemini 3.8 Flash on the long prefix: the same for first request, repeat request (follow-up turn) and second first request, with
    the hit threshold read from the run's own records (sets.jsonl), which must hold one value."""
    thresholds = set()
    for line in open(os.path.join(folder, "sets.jsonl"), encoding="utf-8"):
        if '"threshold"' in line:
            thresholds.add(json.loads(line)["threshold"])
    if len(thresholds) != 1:
        raise ValueError("the sets records of %s hold %d hit thresholds, not one" % (folder, len(thresholds)))
    threshold = thresholds.pop()
    rows = gct.load_requests(folder, threshold)
    cells = gct.cells(rows)
    out = {"threshold": threshold, "tokens": statistics.median(r["prompt"] for r in cells[("flash", "first")]["rows"])}
    for state in gct.STATES:
        c = cells[("flash", state)]
        out[state] = {"cost": statistics.mean(r["cost"] for r in c["rows"]), "ok": c["ok"], "n": c["n"]}
    return out


def build_data():
    root = lambda d: os.path.join(HERE, d)
    rows = agent_rows()
    pairs = cache_pairs(rows)
    return {"rows": rows, "groups": brt.effort_groups(rows), "pairs": pairs, "agent_tokens": agent_prompt_tokens(pairs),
            "first_turns": first_turns(root(AGENT_FOLDERS[0])), "lp": long_prompt(root(SONNET_FOLDER)), "gem": gemini_follow_up(root(GEMINI_FOLDER))}


# ------------------------------------------------------------------ the checks against what is published
def table_rows(path):
    """Every row of every table in a Markdown file, as a list of cells."""
    out = []
    for line in open(path, encoding="utf-8"):
        if line.startswith("|") and not line.startswith("|---"):
            out.append([x.strip() for x in line.strip().strip("|").split("|")])
    return out


def read_text(*parts):
    return open(os.path.join(HERE, *parts), encoding="utf-8").read()


def against_published(data):
    """The mismatches between these numbers and the published tables and prose; an empty list means they agree."""
    bad = []
    reports = lambda *p: os.path.join(HERE, "reports", *p)
    table = {r[0]: r for r in table_rows(reports("consolidated", "results-table.md"))}
    arms = [r for _, _, bars in data["groups"] for _, r in bars] + [r for _, _, n, c in data["pairs"] for r in (n, c)]
    for r in arms:
        cells = table.get(r["label"])
        if cells is None:
            bad.append("%s is not in consolidated/results-table.md" % r["label"])
        elif ("%.4f" % r["cost"], "%.2f" % r["claim_wall"]) != (cells[2], cells[3]):
            bad.append("%s: %.4f and %.2f against the table's %s and %s" % (r["label"], r["cost"], r["claim_wall"], cells[2], cells[3]))
    sonnet = table_rows(reports("cache-timing-table.md"))
    for state, label in zip(ct.STATES, ("no cache", "cold cache (writes)", "warm cache (reads)")):
        cells = next((c for c in sonnet if c[:3] == ["Sonnet", "long", label]), None)
        if cells is None or cells[-1] != "%.4f" % data["lp"][state]["cost"]:
            bad.append("Sonnet long %s: %.4f against the table's %s" % (state, data["lp"][state]["cost"], cells and cells[-1]))
    gemini = table_rows(reports("gemini-cache-timing-table.md"))
    for state in gct.STATES:
        cells = next((c for c in gemini if c[:2] == ["Gemini 3.8 Flash", gct.STATE_LABEL[state]]), None)
        if cells is None or cells[-1] != "%.4f" % data["gem"][state]["cost"]:
            bad.append("Gemini %s: %.4f against the table's %s" % (state, data["gem"][state]["cost"], cells and cells[-1]))
    run1, sonnet_md, gemini_md = (open(reports(n), encoding="utf-8").read() for n in ("run-1-results.md", "cache-timing-results.md", "gemini-results.md"))
    readme = open(os.path.join(HERE, "README.md"), encoding="utf-8").read()
    want = "%d of %d first turns of cached arms" % (data["first_turns"][1], data["first_turns"][0])
    if want not in readme:
        bad.append("README.md does not say %r" % want)
    for name, fam, none, cache in data["pairs"]:
        want = "%s $%.4f to $%.4f (%.1f times)" % (fam, none["cost"], cache["cost"], none["cost"] / cache["cost"])
        if want not in run1:
            bad.append("run-1-results.md does not say %r" % want)
    lp, gem = data["lp"], data["gem"]
    for text, name, want in ((sonnet_md, "cache-timing-results.md", "about %s tokens" % "{:,}".format(int(round(data["agent_tokens"][0], -3)))),
                             (sonnet_md, "cache-timing-results.md", "Effort %s, %d output tokens at most, tool choice %s" % (lp["effort"], lp["max_tokens"], lp["tool_choice"])),
                             (sonnet_md, "cache-timing-results.md", "%.1f times less than one with no cache" % (lp["none"]["cost"] / lp["warm"]["cost"])),
                             (sonnet_md, "cache-timing-results.md", "(%d percent more than no cache)" % round(100 * (lp["cold"]["cost"] / lp["none"]["cost"] - 1))),
                             (gemini_md, "gemini-results.md", "(%.1f times less)" % (gem["first"]["cost"] / gem["repeat"]["cost"]))):
        if want not in text:
            bad.append("%s does not say %r" % (name, want))
    return bad


# ------------------------------------------------------------------ chart 1: the value map
def point_stacks(pts, closeness=4.0):
    """Consecutive points of one model that sit within `closeness` units of each other, as stacks."""
    stacks = []
    for p in pts:
        if stacks and math.hypot(p["x"] - stacks[-1][0]["x"], p["y"] - stacks[-1][0]["y"]) < closeness:
            stacks[-1].append(p)
        else:
            stacks.append([p])
    return stacks


def value_map(groups):
    """(canvas, title, description, stacks): cost per task across, median time per claim up, one point per arm, lower left better.
    stacks lists the points of one model that sit on the same spot and are drawn one inside the other: (model, levels, cost gap, time gap)."""
    title, subtitle = "Cost against time per claim", "One point per arm. A task is one claim: 10 per trial, 2 trials."
    left, right, top, plot_h = 62, 28, 172, 300
    bottom, plot_w = top + plot_h, EW - left - right
    flat = [(name, lv, r) for name, _, bars in groups for lv, r in bars]
    _, xmax, xticks = brt.axis_ticks(max(r["cost"] for *_, r in flat))
    _, ymax, yticks = brt.axis_ticks(max(r["claim_wall"] for *_, r in flat))
    X = lambda v: left + plot_w * v / xmax
    Y = lambda v: bottom - plot_h * v / ymax
    c = Canvas(EW, bottom + 68)
    c.text(left, 28, title, size=20, bold=True)
    c.text(left, 50, subtitle, fill=MUTED)
    for i, lv in enumerate(brt.LEVELS):
        x = left + i * 84
        c.raw('<rect x="%d" y="70" width="14" height="14" fill="#667" fill-opacity="%s"/>' % (x, brt.EFFORT_OPACITY[lv]))
        c.text(x + 20, 82, lv)
    c.text(left, 104, "low, medium, high = effort (Claude) or thinking level (Gemini)", fill=MUTED)
    c.raw('<circle cx="%d" cy="120" r="7" fill="%s" stroke="%s" stroke-width="2.5" stroke-dasharray="4 2.5"/>' % (left + 7, PAPER, brt.BELOW_BAR))
    c.text(left + 20, 126, "fewer than 10 of 10 claims passed in a trial")
    c.text(left, top - 16, "Seconds per claim (median)", fill=MUTED)
    for v, label in yticks:
        c.raw('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1"/>' % (left, Y(v), EW - right, Y(v), GRID))
        c.text(left - 6, Y(v) + 5, label, anchor="end", fill=MUTED)
    for v, label in xticks:
        c.raw('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1"/>' % (X(v), top, X(v), bottom, GRID))
        c.text(X(v), bottom + 24, label, anchor="middle", fill=MUTED)
    c.text(left + plot_w / 2.0, bottom + 48, "US$ per task (Claude: notebook formula, Gemini: list price)", anchor="middle", fill=MUTED)
    R = 6.5
    laid = []
    for name, family, bars in groups:
        pts = [{"lv": lv, "x": X(r["cost"]), "y": Y(r["claim_wall"]), "row": r} for lv, r in bars]
        laid.append((name, family, point_stacks(pts), pts))
        coords = [(p["x"], p["y"]) for p in pts]
        c.raw('<polyline points="%s" fill="none" stroke="%s" stroke-opacity="0.55" stroke-width="2" stroke-linejoin="round"/>'
              % (" ".join("%.1f,%.1f" % p for p in coords), brt.FAMILY_COLOR[family]))
        c.sample("%s path" % name, coords)
    for name, family, stacks, _ in laid:
        color = brt.FAMILY_COLOR[family]
        for stack in reversed(stacks):      # the highest level first, so the lowest sits on top and stays whole
            for k, p in enumerate(reversed(stack)):      # the highest level first, so the lower ones sit on top of it
                r_ = (R + 2.0 - 3.5 * k) if len(stack) > 1 else R
                short = min(passed(p["row"])) < 10
                if short:
                    c.raw('<circle cx="%.1f" cy="%.1f" r="7.5" fill="%s" stroke="%s" stroke-width="2.5" stroke-dasharray="4 2.5"/>'
                          % (p["x"], p["y"], PAPER, brt.BELOW_BAR))
                else:
                    c.raw('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" fill-opacity="%s" stroke="%s" stroke-width="%s"/>'
                          % (p["x"], p["y"], r_, color, brt.EFFORT_OPACITY[p["lv"]], color if k == 0 else PAPER, 2 if k == 0 else 1.5))
            lead = stack[0]
            c.mark("%s %s" % (name, "/".join(p["lv"] for p in stack)), lead["x"] - R - 2, lead["y"] - R - 2, lead["x"] + R + 2, lead["y"] + R + 2)
    for name, family, stacks, pts in laid:                  # the model names first, then the level of each point
        top_point = min(pts, key=lambda p: p["y"])
        c.place(top_point["x"], top_point["y"], name, [(0, -R - 12, "middle"), (R + 8, -R - 8, "start"), (-R - 8, -R - 8, "end"), (0, -R - 34, "middle")],
                size=15, bold=True)
    labels = []
    for name, family, stacks, pts in laid:
        for stack in stacks:
            lead = stack[0]
            short = min(passed(lead["row"])) < 10
            label = ", ".join(p["lv"] for p in stack)
            if short:
                label += ": %s of 10" % ", ".join(str(n) for n in passed(lead["row"]))
            labels.append((lead, label, short))
    for lead, label, short in sorted(labels, key=lambda t: -len(t[1])):      # the longest label has the fewest places to go, so it picks first
        c.place(lead["x"], lead["y"], label, [(R + 8, 5, "start"), (-R - 8, 5, "end"), (0, -R - 9, "middle"), (0, R + 21, "middle"),
                                              (-20, R + 21, "middle"), (20, R + 21, "middle"), (0, -R - 32, "middle")],
                bold=short, fill=brt.BELOW_BAR if short else None, backing=True)
    arrow(c, "better arrow", left + 62, bottom - 30, left + 14, bottom - 8, MUTED)
    c.text(left + 72, bottom - 12, "Better: cheaper and faster", bold=True, fill=MUTED, backing=True)
    desc = "A scatter of %d arms: " % len(flat) + "; ".join("%s %s, %s per task and %.1f s per claim%s" % (
        n, lv, "$%.4f" % r["cost"], r["claim_wall"], " (%s of 10 passed)" % " and ".join(str(p) for p in passed(r)) if min(passed(r)) < 10 else "")
        for n, lv, r in flat) + ". Lower left is better."
    stacks = [(name, [p["lv"] for p in stack], abs(stack[0]["row"]["cost"] - stack[-1]["row"]["cost"]),
               abs(stack[0]["row"]["claim_wall"] - stack[-1]["row"]["claim_wall"])) for name, _, stk, _ in laid for stack in stk if len(stack) > 1]
    return c, title, desc, stacks


def usd_range(rows, key="cost"):
    v = [r[key] for r in rows]
    return "$%.4f to $%.4f" % (min(v), max(v))


def sec_range(rows):
    v = [r["claim_wall"] for r in rows]
    return "%.1f to %.1f s" % (min(v), max(v))


def value_map_text(groups, stacks):
    """(the takeaway line, the settings paragraph) for the value map, computed from the rows; stacks is what value_map returned. The
    orders the takeaway states are checked first; if the data does not have them the text is not written."""
    by = {g[1]: dict(g[2]) for g in groups}
    for fam in ("Opus", "Sonnet", "Gemini"):
        if fam not in by:
            raise ValueError("the value map needs Opus, Sonnet and Gemini rows")
    op, so, ge = by["Opus"], by["Sonnet"], by["Gemini"]
    lv = brt.LEVELS
    cost_gap, time_gap = brt.spread(groups)
    if not all(so[l]["claim_wall"] <= op[l]["claim_wall"] for l in lv):
        raise ValueError("the data does not have Sonnet as fast as or faster than Opus at every level, which the takeaway states")
    if not all(ge[l]["claim_wall"] > op[l]["claim_wall"] * (1 + time_gap / 100.0) for l in lv):
        raise ValueError("the data does not have Gemini slower than Opus by more than the gap between two trials at every level, which the takeaway states")
    if not all(ge[l]["cost"] < so[l]["cost"] < op[l]["cost"] for l in lv):
        raise ValueError("the data does not have Gemini cheaper than Sonnet cheaper than Opus at every level, which the takeaway states")
    ratios = [so[l]["cost"] / op[l]["cost"] for l in lv]
    cost_vs = "about half as much as Opus 5.5" if all(0.45 <= x <= 0.55 for x in ratios) else \
        "%d%% to %d%% as much as Opus 5.5" % (round(100 * min(ratios)), round(100 * max(ratios)))
    short = [(l, passed(ge[l])) for l in lv if min(passed(ge[l])) < 10]
    fail = "" if not short else ", and at %s thinking it failed the 10-of-10 bar (%s of 10)" % (
        _join([l for l, _ in short]), _join([" and ".join(str(p) for p in ps) for _, ps in short]))
    head = "Sonnet 5.5 costs %s (%s against %s per task) and is as fast or faster (%s per claim against %s); Gemini 3.8 Flash is the cheapest (%s) and, level for level, the slowest (%s)%s." % (
        cost_vs, usd_range(so.values()), usd_range(op.values()), sec_range(so.values()), sec_range(op.values()), usd_range(ge.values()), sec_range(ge.values()), fail)
    stack_note = "".join(" %s at %s land on the same spot (%s apart in cost per task, %.2f s in time per claim) and are drawn one inside the other." % (
        n, " and ".join(levels), "$%.4f" % dc, dt) for n, levels, dc, dt in stacks)
    settings = ("Settings: each point is one arm, 10 claims per trial and 2 trials per arm. Across is the mean cost per task of the two trials; up is the median, over "
                "the claims of both trials, of the seconds from a claim's first request to its verdict. Claude cost is by the notebook's formula and Gemini cost at "
                "Vertex list prices (global location), both from each request's usage block. The Claude arms use the automatic prompt cache; Gemini's cache is "
                "implicit and cannot be switched off. A lighter point is a lower effort (Claude) or thinking level (Gemini).%s The two trials of one arm differ by up to "
                "%.1f%% in cost per task and %.0f%% in median time per claim, so small gaps between neighbouring points are not differences. %s"
                % (stack_note, cost_gap, time_gap, brt.CROSS_FAMILY))
    return head, settings


def _join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# ------------------------------------------------------------------ chart 2: cache savings
def bar(c, name, x, bottom, plot_h, vmax, value, color, width, label_size=FONT):
    h = plot_h * value / vmax
    c.raw('<rect x="%.1f" y="%.1f" width="%d" height="%.1f" rx="3" fill="%s"/>' % (x, bottom - h, width, h, color))
    c.mark(name, x, bottom - h, x + width, bottom)
    c.text(x + width / 2.0, bottom - h - 8, "%.4f" % value, size=label_size, bold=True, anchor="middle")


def cache_savings(pairs, lp, agent_tokens):
    """(canvas, title, description): cost with and without the cache. Left, the agent task at high effort for each model; right, one
    request on the long prompt (Sonnet 5.5) with no cache, cold and warm. Both on one dollar axis, each panel saying what its unit is."""
    title = "Cost with and without the prompt cache"
    subtitle = "Opus 5.5 and Sonnet 5.5. Call-outs compare with no cache."
    left, right, top, plot_h = 62, 16, 190, 250
    bottom = top + plot_h
    bar_w, gap_, group_gap, panel_gap = 62, 8, 28, 40
    values = [v for _, _, n, c_ in pairs for v in (n["cost"], c_["cost"])] + [lp[s]["cost"] for s in ct.STATES]
    _, vmax, ticks = brt.axis_ticks(max(values))
    c = Canvas(EW, bottom + 104)
    Y = lambda v: bottom - plot_h * v / vmax
    c.text(left, 28, title, size=20, bold=True)
    c.text(left, 50, subtitle, fill=MUTED)
    x0 = left + 12
    group_w = 2 * bar_w + gap_
    panel1_end = x0 + len(pairs) * group_w + (len(pairs) - 1) * group_gap
    x1 = panel1_end + panel_gap
    c.text(x0, 84, "Automatic cache", bold=True)
    c.text(x0, 104, "An agent task (one claim)", fill=MUTED)
    c.text(x0, 124, "%dK to %dK tokens per request" % (round(agent_tokens[0] / 1000.0), round(agent_tokens[1] / 1000.0)), fill=MUTED)
    c.text(x0, 144, "10 claims, %s effort" % pairs[0][3]["label"].split()[1], fill=MUTED)
    c.text(x1, 84, "Explicit breakpoint", bold=True)
    c.text(x1, 104, "One long-prompt request", fill=MUTED)
    c.text(x1, 124, "Sonnet 5.5, %dK tokens" % round(lp["tokens"] / 1000.0), fill=MUTED)
    c.text(x1, 144, "%s effort, %d tokens max" % (lp["effort"], lp["max_tokens"]), fill=MUTED)
    c.text(left, top - 14, "US$ (per claim on the left, per request on the right)", fill=MUTED)
    for v, label in ticks:
        c.raw('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1"/>' % (left, Y(v), EW - right, Y(v), GRID))
        c.text(left - 6, Y(v) + 5, label, anchor="end", fill=MUTED)
    divider = (panel1_end + x1) / 2.0
    c.raw('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1.5" stroke-dasharray="3 4"/>' % (divider, top - 4, divider, bottom + 64, MUTED))
    for gi, (name, family, none, cache) in enumerate(pairs):
        gx = x0 + gi * (group_w + group_gap)
        for bi, (label, value, color) in enumerate((("no cache", none["cost"], NO_CACHE), ("cache", cache["cost"], brt.FAMILY_COLOR[family]))):
            bx = gx + bi * (bar_w + gap_)
            bar(c, "%s %s bar" % (name, label), bx, bottom, plot_h, vmax, value, color, bar_w)
            c.text(bx + bar_w / 2.0, bottom + 20, label, anchor="middle")
        c.text(gx + group_w / 2.0, bottom + 44, name, size=15, bold=True, anchor="middle")
        c.text(gx + group_w / 2.0, bottom + 66, "%.1f times less" % (none["cost"] / cache["cost"]), bold=True, anchor="middle", fill=brt.FAMILY_COLOR[family])
    for bi, (state, label, color) in enumerate((("none", "no cache", NO_CACHE), ("cold", "cold", COLD), ("warm", "warm", brt.FAMILY_COLOR["Sonnet"]))):
        bx = x1 + bi * (bar_w + gap_)
        bar(c, "long prompt %s bar" % label, bx, bottom, plot_h, vmax, lp[state]["cost"], color, bar_w)
        c.text(bx + bar_w / 2.0, bottom + 20, label, anchor="middle")
    mid = x1 + (3 * bar_w + 2 * gap_) / 2.0
    c.text(mid, bottom + 44, "Sonnet 5.5", size=15, bold=True, anchor="middle")
    c.text(mid, bottom + 66, "warm: %.1f times less" % (lp["none"]["cost"] / lp["warm"]["cost"]), bold=True, anchor="middle", fill=brt.FAMILY_COLOR["Sonnet"])
    c.text(mid, bottom + 88, "cold: %d%% more" % round(100 * (lp["cold"]["cost"] / lp["none"]["cost"] - 1)), bold=True, anchor="middle", fill="#9a6a10")
    desc = "Cost with and without the prompt cache. Agent task, per task, with the automatic cache: " + "; ".join(
        "%s $%.4f with no cache, $%.4f with the cache" % (n, a["cost"], b["cost"]) for n, _, a, b in pairs) + \
        ". One request on a %dK-token prompt, Sonnet 5.5, with an explicit cache breakpoint: $%.4f with no cache, $%.4f cold (writes the cache), $%.4f warm (reads it)." % (
            round(lp["tokens"] / 1000.0), lp["none"]["cost"], lp["cold"]["cost"], lp["warm"]["cost"])
    return c, title, desc


def cache_savings_text(pairs, lp, agent_tokens, first):
    parts = ["%s %s (%.1f times less)" % (n, "$%.4f to $%.4f" % (a["cost"], b["cost"]), a["cost"] / b["cost"]) for n, _, a, b in pairs]
    ratios = [b["cost"] / a["cost"] for _, _, a, b in pairs]
    about = "costs about half" if all(0.45 <= x <= 0.55 for x in ratios) else "costs %d%% to %d%% as much" % (round(100 * min(ratios)), round(100 * max(ratios)))
    head = ("With the automatic cache an agent task %s: %s per task. With an explicit cache breakpoint at the end of a shared %dK-token prompt, a warm "
            "Sonnet 5.5 request cost $%.4f against $%.4f with no cache (%.1f times less), and the first request, which writes the cache, cost $%.4f "
            "(%d%% more than no cache)."
            % (about, " and ".join(parts), round(lp["tokens"] / 1000.0), lp["warm"]["cost"], lp["none"]["cost"], lp["none"]["cost"] / lp["warm"]["cost"],
               lp["cold"]["cost"], round(100 * (lp["cold"]["cost"] / lp["none"]["cost"] - 1))))
    trial_gap = max(g for _, _, a, b in pairs for r in (a, b) for g in [gap(r["claim_wall_by_trial"])] if g is not None)
    if max(abs(a["claim_wall"] - b["claim_wall"]) / a["claim_wall"] for _, _, a, b in pairs) >= trial_gap or lp["seen"]:
        raise ValueError("the cache is not time-neutral in these records (a gap larger than the trial gap, or the cache timing reading is seen), "
                         "so the 'cost only' sentence of the settings would be false")
    time_pairs = ", and ".join("%.1f s without the cache and %.1f s with it for %s" % (a["claim_wall"], b["claim_wall"], n) for n, _, a, b in pairs)
    ok = all(lp[s]["ok"] == lp[s]["n"] for s in ct.STATES)
    if first[0] == 0 or first[1] != first[0]:
        raise ValueError("the automatic cache read something on a first turn in these records, so the sentence that says it never carried across claims would be false")
    settings = ("Settings: the agent task is 10 claims per trial and 2 trials per arm at high effort, with prompts of %dK to %dK tokens a turn; a task is one claim, the "
                "bar is the mean of the two trials, cost is by the notebook's formula and the cached arm uses the automatic prompt cache (what its cost is made of is in "
                "[the run 1 results](../run-1-results.md)). The long-prompt request is Sonnet 5.5 on a prefix of about %s tokens (the "
                "system prompt, the tools and the claims ledger), 10 requests per state, a different question in each, one at a time, at %s effort with tool choice "
                "%s and at most %d output tokens; "
                "each bar is the mean of the requests that passed their state check (%s). Cold is the first request with a cache breakpoint, which writes the "
                "prefix; warm is a different question after the same prefix, which reads it. **The two panels switch the cache on in different ways.** In the "
                "agent task the automatic cache did not carry from one claim to the next: all %d first turns of the cached arms wrote the prefix again and read "
                "nothing (see [how caching is switched](../how-caching-is-switched.md)), so the saving comes from the later turns of each claim. The long-prompt test "
                "puts an explicit breakpoint at the end of the shared prefix, which is what let a different question read it. The panels also differ in prompt "
                "size, effort and output, so the two ratios are not a like-for-like comparison of the two ways. Both panels share one dollar axis, but the left "
                "bars are cost per task (one claim) and the right bars cost per request. **Cost only:** warm was faster than no cache in %d of %d pairs, which "
                "the rule fixed before the run did not count as a time saving, and the agent task's median time per claim was %s, differences smaller than the "
                "%.0f%% gap between the two trials of one of these arms."
                % (round(agent_tokens[0] / 1000.0), round(agent_tokens[1] / 1000.0), "{:,}".format(int(round(lp["tokens"], -3))), lp["effort"],
                   lp["tool_choice"], lp["max_tokens"], "10 of 10 in every state" if ok else "see the table", first[0], lp["faster"], lp["pairs"],
                   time_pairs, 100 * trial_gap))
    return head, settings


# ------------------------------------------------------------------ chart 3: the Gemini follow-up turn
def gemini_chart(gem):
    """(canvas, title, description): first request, follow-up turn and second first request on the long prefix, cost per request."""
    title = "Gemini 3.8 Flash follow-up turn"
    subtitle = "A %dK-token prompt, 10 sets of 3 requests." % round(gem["tokens"] / 1000.0)
    left, right, top, plot_h = 62, 16, 118, 250
    bottom = top + plot_h
    bar_w, gap_ = 96, 60
    _, vmax, ticks = brt.axis_ticks(max(gem[s]["cost"] for s in gct.STATES))
    c = Canvas(EW, bottom + 134)
    Y = lambda v: bottom - plot_h * v / vmax
    c.text(left, 28, title, size=20, bold=True)
    c.text(left, 50, subtitle, fill=MUTED)
    c.text(left, top - 14, "US$ per request (mean of the valid requests)", fill=MUTED)
    for v, label in ticks:
        c.raw('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1"/>' % (left, Y(v), EW - right, Y(v), GRID))
        c.text(left - 6, Y(v) + 5, label, anchor="end", fill=MUTED)
    x0 = left + (EW - left - right - (3 * bar_w + 2 * gap_)) / 2.0
    names = {"first": ("first request",), "repeat": ("follow-up turn",), "control": ("second first", "request (control)")}
    colors = {"first": NO_CACHE, "repeat": brt.FAMILY_COLOR["Gemini"], "control": NO_CACHE}
    for i, state in enumerate(gct.STATES):
        bx = x0 + i * (bar_w + gap_)
        bar(c, "%s bar" % state, bx, bottom, plot_h, vmax, gem[state]["cost"], colors[state], bar_w)
        for k, line in enumerate(names[state]):
            c.text(bx + bar_w / 2.0, bottom + 20 + 20 * k, line, anchor="middle")
        c.text(bx + bar_w / 2.0, bottom + 64, ("hit the cache: %d of %d" if state == "repeat" else "valid: %d of %d") % (gem[state]["ok"], gem[state]["n"]),
               anchor="middle", fill=MUTED)
    mid = x0 + 1.5 * bar_w + gap_
    c.text(mid, bottom + 92, "follow-up that hit the cache: %.1f times less" % (gem["first"]["cost"] / gem["repeat"]["cost"]), bold=True, anchor="middle",
           fill=brt.FAMILY_COLOR["Gemini"])
    c.text(mid, bottom + 114, "than a first request. Valid first request: read nothing cached.", anchor="middle", fill=MUTED)
    desc = "Gemini 3.8 Flash on a %dK-token prompt, cost per request: first request $%.4f, follow-up turn $%.4f, second first request $%.4f." % (
        round(gem["tokens"] / 1000.0), gem["first"]["cost"], gem["repeat"]["cost"], gem["control"]["cost"])
    return c, title, desc


def gemini_text(gem):
    head = ("On a %dK-token prompt, a Gemini 3.8 Flash follow-up turn that hit the cache cost $%.4f against $%.4f for a first request (%.1f times less); "
            "%d of the 10 follow-ups hit it."
            % (round(gem["tokens"] / 1000.0), gem["repeat"]["cost"], gem["first"]["cost"], gem["first"]["cost"] / gem["repeat"]["cost"], gem["repeat"]["ok"]))
    settings = ("Settings: Gemini 3.8 Flash on Vertex AI, thinking at low, 10 sets of three requests on a prefix of about %s tokens (the system prompt, the tools "
                "and the claims ledger). The first request has a fresh nonce; the follow-up turn is the first request, its reply and a new question; the second "
                "first request is a control of the same kind as the first. Each bar is the mean cost of the valid requests: a follow-up is valid when it read at "
                "least %g percent of its prompt from the cache, and a first request when it read nothing from it. Gemini's cache is implicit and cannot be "
                "switched off, so there is no no-cache arm, and a first request is the case where nothing was cached. **What it does not show:** in the "
                "diagnostic, a new question sent as a separate request never hit the cache (see [the Gemini results](../gemini-results.md#what-the-diagnostic-found-about-the-cache)), "
                "and the time reading fixed before the run came out as not seen, so this chart is about cost only. These states do not map onto the Claude "
                "cold, warm and no-cache states and are not drawn on the same chart as them."
                % ("{:,}".format(int(round(gem["tokens"], -3))), gem["threshold"]))
    return head, settings


# ------------------------------------------------------------------ the page and the build
def page(texts):
    vm, cs, gm = texts
    return "\n".join([
        "# Value map and cache savings",
        "",
        "Navigation: [index](../../README.md) · [effort levels side by side](../consolidated/consolidated-results.md) · [Claude run 1 results](../run-1-results.md) · "
        "[Claude cache timing results](../cache-timing-results.md) · [Gemini 3.8 Flash results](../gemini-results.md) · [method](../method.md)",
        "",
        "The value map and the cache savings, and the Gemini follow-up turn on its own. Everything is built from the records already published "
        "([run 1](../../results/run1), [Gemini agent task](../../results/gemini-flash-loop), [Sonnet cache timing](../../results/cache-timing-sonnet) and "
        "[Gemini cache timing](../../results/gemini-flash-cache-timing)); nothing was run again. Fable 5.1 and the arms without a cache are in the "
        "[full table](../consolidated/results-table.md), not on the value map.",
        "",
        "## Value map",
        "",
        "**%s**" % vm[0],
        "",
        "![Cost against time per claim](value-map.svg)",
        "",
        vm[1],
        "",
        "## Cache savings",
        "",
        "**%s**" % cs[0],
        "",
        "![Cost with and without the prompt cache](cache-savings.svg)",
        "",
        cs[1],
        "",
        "## Gemini follow-up turn",
        "",
        "**%s**" % gm[0],
        "",
        "![Gemini 3.8 Flash follow-up turn](gemini-follow-up.svg)",
        "",
        gm[1],
        "",
        "Built by `python3 build_blog_charts.py`.",
        ""])


def build():
    """(files, problems): every file's text, and whatever stops it being written (a mismatch with the published numbers, an overlap)."""
    data = build_data()
    problems = against_published(data)
    files = {}
    vm_canvas, vm_title, vm_desc, stacks = value_map(data["groups"])
    for name, (canvas, title, desc) in (("value-map.svg", (vm_canvas, vm_title, vm_desc)), ("cache-savings.svg", cache_savings(data["pairs"], data["lp"], data["agent_tokens"])),
                                        ("gemini-follow-up.svg", gemini_chart(data["gem"]))):
        problems += ["%s: %s" % (name, p) for p in canvas.problems()]
        files[name] = canvas.svg(title, desc)
    files["blog-charts.md"] = page([value_map_text(data["groups"], stacks), cache_savings_text(data["pairs"], data["lp"], data["agent_tokens"], data["first_turns"]),
                              gemini_text(data["gem"])])
    return files, problems, data


def selftest(inject_fault=False):
    ok = True

    def check(name, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print("%-4s %-60s got %s want %s" % ("PASS" if good else "FAIL", name, str(got)[:90], str(want)[:90]))
    files, problems, data = build()
    check("the real records agree with the published tables and prose, and no label overlaps another or leaves its frame", problems, [])
    # the comparison can fail: a changed number, a changed ratio and a missing row are each caught
    bump = dict(data, groups=[(n, f, [(lv, dict(r, cost=r["cost"] * 1.01) if (n, lv) == ("Sonnet 5.5", "high") else r) for lv, r in bars]) for n, f, bars in data["groups"]])
    check("a cost changed by 1% is caught against the published table", any("Sonnet high cache" in m for m in against_published(bump)), True)
    worse = dict(data, lp=dict(data["lp"], warm=dict(data["lp"]["warm"], cost=data["lp"]["warm"]["cost"] * 1.2)))
    check("a warm cost changed by 20% is caught (table and the 9.2 times)", len(against_published(worse)) >= 2, True)
    check("a missing arm is caught", any("not in" in m for m in against_published(dict(data, pairs=[(n, f, dict(a, label="x"), b) for n, f, a, b in data["pairs"]]))), True)
    # the charts
    names = ["value-map.svg", "cache-savings.svg", "gemini-follow-up.svg"]
    sizes = [min(int(x) for x in re.findall(r'font-size="(\d+)"', files[n])) for n in names]
    check("every chart is 640 units wide and no text is under 14", ([('viewBox="0 0 640 ' in files[n]) for n in names], sizes), ([True] * 3, [14, 14, 14]))
    vm = files["value-map.svg"]
    check("value map: nine points and one legend mark, Fable absent", (vm.count("<circle"), "Fable" in vm), (10, False))
    check("value map: one dashed red point (Gemini low) and one in the legend, the passes written out", (vm.count('stroke-dasharray="4 2.5"'), "low: 7, 8 of 10" in vm), (2, True))
    check("value map: lower left is said on the chart", "Better: cheaper and faster" in vm, True)
    check("value map: the Sonnet medium and high points are stacked into one label", "medium, high" in vm, True)
    check("value map: a task is one claim, the price bases are on the axis, and the page says slowest only level for level",
          ("A task is one claim" in vm, "Gemini: list price" in vm, "level for level, the slowest" in files["blog-charts.md"]), (True, True, True))
    cs = files["cache-savings.svg"]
    check("cache savings: seven bars, the call-outs from the data", (cs.count("<rect") - 1, "2.0 times less" in cs, "1.9 times less" in cs, "warm: 9.2 times less" in cs, "cold: 25% more" in cs),
          (7, True, True, True, True))
    check("cache savings: the chart names the mechanism of each panel and the long prompt's effort and token cap",
          ("Automatic cache" in cs, "Explicit breakpoint" in cs, "low effort, 256 tokens max" in cs), (True, True, True))
    check("the automatic cache read nothing on any first turn of a cached arm (180 of 180), as the README says", data["first_turns"], (180, 180))
    try:
        cache_savings_text(data["pairs"], data["lp"], data["agent_tokens"], (180, 170))
        raised = False
    except ValueError:
        raised = True
    check("a first turn that did read the cache refuses the 'never carried across claims' text", raised, True)
    gm = files["gemini-follow-up.svg"]
    check("gemini chart: three bars, the follow-up call-out and the valid counts", (gm.count("<rect") - 1, "follow-up that hit the cache: 8.0 times less" in gm, "valid: 9 of 10" in gm, "hit the cache: 8 of 10" in gm),
          (3, True, True, True))
    check("the page links its three charts and says nothing was run again", (all(("(%s)" % n) in files["blog-charts.md"] for n in names), "nothing was run again" in files["blog-charts.md"]), (True, True))
    check("the page and the charts hold no absolute path and no e-mail address", [w for w in ("/Users/", "/home/", "@") if w in "".join(files.values())], [])
    # the label placer and the canvas can fail
    c = Canvas(200, 100)
    c.text(50, 50, "occupied", anchor="middle")
    try:
        c.place(50, 50, "occupied again", [(0, 0, "middle")])
        placed = True
    except ValueError:
        placed = False
    check("a label with no free spot is refused, not drawn on top", placed, False)
    c2 = Canvas(100, 100)
    c2.text(95, 50, "far too long for this frame")
    c2.text(10, 20, "a")
    c2.text(10, 21, "b")
    check("a text outside the frame and two on top of each other are both reported", len(c2.problems()) >= 2, True)
    # the takeaways state orders; data without them is refused
    swapped = [(n, f, [(lv, dict(r, claim_wall=r["claim_wall"] * (4 if f == "Sonnet" else 1))) for lv, r in bars]) for n, f, bars in data["groups"]]
    try:
        value_map_text(swapped, [])
        refused = False
    except ValueError:
        refused = True
    check("a value map whose speed order is not the one the takeaway states is refused", refused, True)
    if inject_fault:
        check("injected fault (must FAIL)", 1, 2)
    print("selftest", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def main():
    argv = sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--selftest" in argv or "--selftest-fault" in argv:
        return selftest(inject_fault="--selftest-fault" in argv)
    out = os.path.join(HERE, "reports", "blog")
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    files, problems, _ = build()
    if problems:
        print("nothing written:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    os.makedirs(out, exist_ok=True)      # everything is built and checked before anything is written
    for name, text in files.items():
        open(os.path.join(out, name), "w", encoding="utf-8").write(text)
    print("wrote %s into %s" % (", ".join(files), out), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
