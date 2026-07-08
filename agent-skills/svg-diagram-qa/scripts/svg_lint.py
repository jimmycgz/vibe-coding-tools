#!/usr/bin/env python3
"""svg_lint.py — geometry linter for hand-authored SVG diagrams.

Catches the mistakes that a "well-formed XML" check misses but that a human
immediately sees when the SVG is rendered: badges hidden behind boxes, boxes
bleeding into each other, and content falling outside the canvas.

It is a HEURISTIC, not a proof. It reports *suspicious* geometry with enough
detail to eyeball. The render-and-look step (see SKILL.md) remains the ground
truth — this just tells you where to look, and gives you a fast regression
check after edits.

Checks:
  1. OFF-CANVAS   — any rect/circle/text whose extent leaves the viewBox.
  2. HIDDEN BADGE — a <circle> (or its labelled number) whose CENTER sits
     inside a <rect> that is drawn LATER in document order. Later elements
     paint on top, so that badge is painted over. This is the classic
     "number blocked by the box" bug. Decorations must come after, and sit
     clear of, the shapes they annotate.
  3. PARTIAL BOX OVERLAP — two <rect>s that intersect but where neither
     fully contains the other. Full containment is fine (a container holding
     a child box); partial overlap usually means two sibling boxes collide.

Usage:
  python3 svg_lint.py diagram.svg [diagram2.svg ...]
Exit code 0 = clean, 1 = findings (so it can gate a commit hook).
"""
import sys
import re
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"


def _f(v, default=0.0):
    try:
        return float(re.sub(r"[a-z%]+$", "", (v or "").strip()))
    except (ValueError, TypeError):
        return default


def parse(path):
    """Return (viewBox tuple, ordered list of shape dicts) in document order."""
    tree = ET.parse(path)
    root = tree.getroot()
    vb = root.get("viewBox")
    if vb:
        x, y, w, h = (float(n) for n in vb.replace(",", " ").split())
        viewbox = (x, y, x + w, y + h)
    else:
        viewbox = (0.0, 0.0, _f(root.get("width")), _f(root.get("height")))
    shapes = []
    for el in root.iter():
        tag = el.tag.replace(NS, "")
        if tag == "rect":
            x, y = _f(el.get("x")), _f(el.get("y"))
            w, h = _f(el.get("width")), _f(el.get("height"))
            shapes.append({"kind": "rect", "x0": x, "y0": y, "x1": x + w, "y1": y + h,
                           "fill": el.get("fill", "")})
        elif tag == "circle":
            cx, cy, r = _f(el.get("cx")), _f(el.get("cy")), _f(el.get("r"))
            shapes.append({"kind": "circle", "cx": cx, "cy": cy, "r": r,
                           "x0": cx - r, "y0": cy - r, "x1": cx + r, "y1": cy + r})
        elif tag == "text":
            x, y = _f(el.get("x")), _f(el.get("y"))
            shapes.append({"kind": "text", "x": x, "y": y,
                           "text": (el.text or "").strip()[:40]})
    return viewbox, shapes


def contains(a, b):
    """rect a fully contains rect/box b (small tolerance)."""
    t = 0.5
    return (a["x0"] - t <= b["x0"] and a["y0"] - t <= b["y0"]
            and a["x1"] + t >= b["x1"] and a["y1"] + t >= b["y1"])


def intersects(a, b):
    return not (a["x1"] <= b["x0"] or b["x1"] <= a["x0"]
                or a["y1"] <= b["y0"] or b["y1"] <= a["y0"])


def lint(path):
    vb, shapes = parse(path)
    vx0, vy0, vx1, vy1 = vb
    findings = []
    margin = 1.0

    # 1. off-canvas
    for s in shapes:
        if s["kind"] == "text":
            if not (vx0 - margin <= s["x"] <= vx1 + margin and vy0 - margin <= s["y"] <= vy1 + margin):
                findings.append(f"OFF-CANVAS text at ({s['x']:.0f},{s['y']:.0f}) "
                                f"outside viewBox {vb}: \"{s['text']}\"")
        else:
            if (s["x0"] < vx0 - margin or s["y0"] < vy0 - margin
                    or s["x1"] > vx1 + margin or s["y1"] > vy1 + margin):
                findings.append(f"OFF-CANVAS {s['kind']} bbox "
                                f"({s['x0']:.0f},{s['y0']:.0f})-({s['x1']:.0f},{s['y1']:.0f}) "
                                f"leaves viewBox {vb}")

    # 2. hidden badge: circle center inside a LATER rect
    for i, s in enumerate(shapes):
        if s["kind"] != "circle":
            continue
        for later in shapes[i + 1:]:
            if later["kind"] != "rect":
                continue
            cx, cy = s["cx"], s["cy"]
            if (later["x0"] <= cx <= later["x1"] and later["y0"] <= cy <= later["y1"]):
                findings.append(
                    f"HIDDEN BADGE circle at ({cx:.0f},{cy:.0f}) r={s['r']:.0f} is inside a rect "
                    f"({later['x0']:.0f},{later['y0']:.0f})-({later['x1']:.0f},{later['y1']:.0f}) "
                    f"drawn AFTER it — the box will paint over the badge. "
                    f"Move the badge into a gap, or draw it after the box.")
                break

    # 3. partial rect overlap (exclude full containment = container/child)
    rects = [s for s in shapes if s["kind"] == "rect"]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i], rects[j]
            if intersects(a, b) and not contains(a, b) and not contains(b, a):
                # ignore hairline touches
                ox = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
                oy = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
                if ox > 2 and oy > 2:
                    findings.append(
                        f"PARTIAL BOX OVERLAP: rect ({a['x0']:.0f},{a['y0']:.0f})-({a['x1']:.0f},{a['y1']:.0f}) "
                        f"and rect ({b['x0']:.0f},{b['y0']:.0f})-({b['x1']:.0f},{b['y1']:.0f}) "
                        f"overlap by {ox:.0f}x{oy:.0f} without containment.")
    return findings


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    total = 0
    for path in argv[1:]:
        try:
            findings = lint(path)
        except ET.ParseError as e:
            print(f"✗ {path}: NOT well-formed XML — {e}")
            total += 1
            continue
        if findings:
            print(f"✗ {path}: {len(findings)} finding(s)")
            for f in findings:
                print(f"    • {f}")
            total += len(findings)
        else:
            print(f"✓ {path}: geometry clean (still render-and-look — this is a heuristic)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
