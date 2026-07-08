---
name: svg-diagram-qa
description: >-
  Verify the quality of hand-authored SVG diagrams — architecture diagrams,
  flowcharts, sequence/block diagrams, system-design figures, pipeline
  illustrations. Use this WHENEVER you write or edit an SVG diagram by hand
  (not a charting library), before you tell the user it's done. It catches the
  bugs that "well-formed XML" hides: number badges or labels painted over by
  boxes, boxes overlapping each other, text running off the canvas, and content
  cropped out of the viewBox. The core discipline is render-to-PNG-and-actually-
  look, backed by a geometry linter. Trigger on: "draw an svg", "make a
  diagram", "architecture diagram", "flowchart", "block diagram", "fix the svg",
  "the boxes overlap", "the labels are cut off", "this diagram looks wrong", or
  any time you hand-produce or repair SVG markup meant to be looked at. This is
  for diagrams — for data charts (bar/line/scatter/dashboards) prefer the
  dataviz skill; this skill is about geometric/layout correctness of figures.
---

# SVG Diagram QA

## Why this skill exists

An SVG can be perfectly valid XML and still be visually broken. `xmllint` says
"OK" while a number badge hides behind its box, two panels bleed into each
other, or half the diagram sits outside the canvas. The author never sees it
because they're reading the *markup*, not the *picture*.

The fix is a discipline, not a trick: **render the SVG to a raster image and
look at it with your own eyes, then run a geometry lint to catch what the eye
skims past.** Markup review is not a substitute for either. Do this *before*
claiming a diagram is done — a broken diagram handed over as "done" is worse
than no diagram, because it wastes the reviewer's trust.

## The loop

1. **Write / edit** the SVG.
2. **Lint the geometry** — fast, catches the classic bugs and gives coordinates:
   ```bash
   python3 <skill>/scripts/svg_lint.py path/to/diagram.svg
   ```
3. **Render to PNG and READ IT BACK** — this is the non-negotiable step:
   ```bash
   bash <skill>/scripts/render.sh path/to/diagram.svg /tmp/out.png
   ```
   Then open the PNG with the Read tool and actually inspect it. Do not skip
   this because the lint passed — the lint is a heuristic; your eyes are ground
   truth.
4. **Zoom-crop wide diagrams** (see below) — one full render of a wide diagram
   hides detail; inspect regions.
5. **Fix and repeat** until the picture is right, not just the XML.

## The classic bugs (what to look for)

These are ranked by how often they slip through and how bad they look:

- **Hidden badge / label (paint order).** In SVG, later elements paint over
  earlier ones. If a number badge, icon, or label is drawn *before* the box it
  annotates AND overlaps it, the box covers it. Two independent mistakes
  usually stack: wrong paint order *and* the badge centered on the box edge
  instead of in a gap. **Rule:** draw decorations *after* the shapes they sit
  on, and position badges/labels in the whitespace *beside* a box (in the gap
  between boxes, or clearly above a corner), never centered on its border.
- **Boxes overlapping.** Sibling panels that intersect look like a rendering
  glitch. Full containment (a container holding a child box) is fine; *partial*
  overlap is the smell. The linter distinguishes these.
- **Off-canvas / cropped content.** Elements whose coordinates exceed the
  viewBox are silently clipped. Widen the viewBox or move the element.
- **Arrows that miss or overshoot.** A connector should start at one box's edge
  and end at the next box's edge, not float in space or pierce through a box.
  The linter can't judge intent here — this is an eyes check.
- **Text overflow.** Long strings run past their box's right edge. No parser
  catches this; only rendering does. Keep captions short or widen the box.

## Rendering notes (important gotcha)

Renderer availability differs by machine; `render.sh` tries `rsvg-convert`,
then `cairosvg`, then macOS `qlmanage`.

**macOS `qlmanage` pads the output to a SQUARE and crops.** For a wide diagram
(e.g. 1520×960) this silently hides the right-hand side — you'll think boxes
are missing when they're just cropped out of frame. This is the single most
confusing failure mode. Two ways around it:

- Prefer `rsvg-convert` (`brew install librsvg`) or `cairosvg`
  (`pip install cairosvg`), which respect aspect ratio.
- Or inspect wide diagrams in **zoom crops** (next section), which sidesteps
  the square-crop entirely.

## Zoom-crop verification for wide diagrams

A single full-canvas render of a wide figure shrinks everything and hides small
overlaps. To inspect a region, make a temporary copy with a tight `viewBox`
over just the area you care about, render *that*, and read it:

```bash
# focus on x∈[1110,1530], y∈[300,600] (e.g. the right-hand boxes)
sed 's#viewBox="0 0 1520 960" width="1520" height="960"#viewBox="1110 300 420 300" width="1400" height="1000"#' \
    diagram.svg > /tmp/zoom.svg
bash <skill>/scripts/render.sh /tmp/zoom.svg /tmp/zoom.png
```

Then Read `/tmp/zoom.png`. Repeat for each region of a large diagram. This is
how you confirm badge/label placement and box edges that a full render blurs.

## Style consistency with sibling diagrams

If the diagram will live alongside others (same folder / same deck), match
their visual language so the set reads as one system. Before finalizing, glance
at a sibling `.svg` in the same directory and align:

- **Palette** — reuse the same fills/strokes and semantic color roles.
- **Typography** — same `font-family`, comparable sizes for titles/labels/captions.
- **Canvas + margins** — similar background color and outer padding.
- **Marker/arrow style** — consistent arrowhead shape and stroke width.

Grab the existing palette quickly:
```bash
grep -oE 'fill="#[0-9a-fA-F]+"|font-family="[^"]*"' sibling-diagram.svg | sort | uniq -c | sort -rn
```

## What the linter does (and doesn't)

`scripts/svg_lint.py` parses rects/circles/text in document order and flags:
OFF-CANVAS (extent leaves viewBox), HIDDEN BADGE (circle center inside a
later-drawn rect → painted over), and PARTIAL BOX OVERLAP (rects intersect
without containment). Exit 0 = clean, 1 = findings, so it can gate a pre-commit
hook. It is a heuristic that tells you *where to look* — it does not understand
arrows, curved paths, `transform`/`g` nesting, or visual balance. It never
replaces rendering and reading the image.

## Definition of done

Before you say a diagram is finished:
- [ ] Lint reports clean (or every finding is understood and intentional).
- [ ] You rendered it and looked at the PNG.
- [ ] For wide diagrams, you zoom-cropped and inspected each region.
- [ ] Badges/labels sit in gaps, decorations paint after their shapes.
- [ ] Nothing is cropped; no unintended box overlaps; arrows connect cleanly.
- [ ] Style matches sibling diagrams if any exist.
