# SVG Diagram QA

An SVG can be perfectly valid XML and still be visually broken. `xmllint` says "OK" while a
number badge hides behind its box, two panels bleed into each other, or half the diagram sits
outside the canvas. The author never sees it because they're reading the *markup*, not the
picture.

This skill enforces the fix, which is a discipline rather than a trick: **render the SVG to a
raster image and look at it, then run a geometry lint to catch what the eye skims past.** Markup
review substitutes for neither.

## Disclaimer

**Provided "as is", used entirely at your own risk.**

- **No warranty (as-is).** This skill — including its instructions and scripts — is provided
  "AS IS", **without warranty of any kind**, express or implied, including but not limited to
  merchantability, fitness for a particular purpose, and non-infringement. No guarantee is made
  that it is secure, error-free, or suitable for any purpose.
- **Limitation of liability.** In no event shall the authors or contributors be liable for any
  claim, damages, or other liability — including data loss or unintended actions taken by an AI
  agent or a shell command — whether in contract, tort, or otherwise, arising from or in
  connection with this software or its use.
- **You are responsible** for reviewing what the linter reports and what you change as a result.
  The linter is a heuristic; a clean report is not a guarantee the diagram is right.

## What the linter catches

| Finding | Meaning |
|---|---|
| `HIDDEN BADGE` | A circle whose centre sits inside a rect drawn *later* — SVG paints in document order, so the box covers the badge |
| `PARTIAL BOX OVERLAP` | Two rects intersect without one containing the other. Full containment is fine; partial overlap reads as a rendering glitch |
| `OFF-CANVAS` | An element's extent leaves the `viewBox` and is silently clipped |

It does **not** understand arrows, curved paths, `transform`/`g` nesting, or visual balance.
Those are eyes-only checks — an arrow that overshoots its box is invisible to any parser.

## Install

Symlink into your skills directory:

```bash
ln -s "$PWD/agent-skills/svg-diagram-qa" ~/.claude/skills/svg-diagram-qa
```

The linter is pure Python 3 stdlib. **Rendering needs one of** `rsvg-convert`
(`brew install librsvg`), `cairosvg` (`pip install cairosvg`), or macOS `qlmanage` — the
bundled `render.sh` tries them in that order. Install one of the first two if you can; see the
gotcha below for why `qlmanage` is the fallback of last resort.

### Optional — make QA automatic

Wire the bundled hook so every SVG you write or edit gets linted whether or not the skill was
invoked. It never blocks (always exits 0); it only reports. In `settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Write|Edit|MultiEdit",
        "hooks": [ { "type": "command",
          "command": "bash ~/.claude/skills/svg-diagram-qa/scripts/svg_lint_hook.sh" } ] }
    ]
  }
}
```

## Use

**With an agent.** It triggers on "draw an svg", "make a diagram", "architecture diagram",
"flowchart", "the boxes overlap", "the labels are cut off", or any time an SVG is hand-authored
or repaired.

**Standalone**, as plain CLIs:

```bash
# lint geometry — one or more files
python3 ~/.claude/skills/svg-diagram-qa/scripts/svg_lint.py diagram.svg

# rasterize so you can actually look at it
bash ~/.claude/skills/svg-diagram-qa/scripts/render.sh diagram.svg out.png 1520
```

`svg_lint.py` exits `0` clean, `1` with findings, `2` if given no arguments — so it gates a
pre-commit hook directly. `render.sh` takes `input.svg [output.png] [width]`, defaulting the
output to `input.png` and the width to 1520, and prints the PNG path on success.

## The gotcha that wastes the most time

**macOS `qlmanage` pads its output to a SQUARE and crops.** For a wide diagram (say 1520×960)
it silently hides the right-hand side — so you conclude boxes are missing when they were merely
cropped out of frame. This is the single most confusing failure mode in the whole workflow.
Prefer `rsvg-convert` or `cairosvg`, which respect aspect ratio.

For wide diagrams, inspect in **zoom crops** rather than one shrunken full render — make a
temporary copy with a tight `viewBox` over the region you care about, render that, and read it:

```bash
sed 's#viewBox="0 0 1520 960" width="1520" height="960"#viewBox="1110 300 420 300" width="1400" height="1000"#' \
    diagram.svg > /tmp/zoom.svg
bash scripts/render.sh /tmp/zoom.svg /tmp/zoom.png
```

## What's in the box

- `SKILL.md` — agent-facing guidance: the loop, the classic bug catalogue, paint-order rules,
  zoom-crop verification, style consistency with sibling diagrams, and a definition of done.
- `scripts/svg_lint.py` — the geometry linter.
- `scripts/render.sh` — renderer wrapper with automatic fallback.
- `scripts/svg_lint_hook.sh` — PostToolUse hook wrapper for automatic linting.

## Related

For Markdown that reads fine but renders wrong, see
[`markdown-render-qa`](../markdown-render-qa) — same render-and-look discipline, different
format.
