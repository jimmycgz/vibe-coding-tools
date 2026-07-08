#!/bin/bash
# render.sh — rasterize an SVG to PNG so you can actually LOOK at it.
# Tries renderers in order of fidelity/availability. Prints the PNG path on success.
#
# Usage: bash render.sh input.svg [output.png] [width]
#   width defaults to the SVG's own width (or 1520).
#
# Why: "well-formed XML" says nothing about whether the picture is right.
# Rendering + reading the image back is the only real check for overlaps,
# clipping, hidden elements, and off-canvas content.

set -u
SVG="${1:?usage: render.sh input.svg [output.png] [width]}"
OUT="${2:-${SVG%.svg}.png}"
W="${3:-1520}"

if command -v rsvg-convert >/dev/null 2>&1; then
  rsvg-convert -w "$W" -o "$OUT" "$SVG" && { echo "$OUT"; exit 0; }
elif python3 -c "import cairosvg" >/dev/null 2>&1; then
  python3 -c "import cairosvg,sys; cairosvg.svg2png(url='$SVG', write_to='$OUT', output_width=$W)" && { echo "$OUT"; exit 0; }
elif command -v qlmanage >/dev/null 2>&1; then
  # macOS Quick Look. NOTE: qlmanage pads to a SQUARE and crops — for WIDE
  # diagrams it hides the right side. Inspect wide diagrams with tight-viewBox
  # zoom crops (see SKILL.md), not one full-canvas qlmanage render.
  DIR="$(dirname "$OUT")"
  qlmanage -t -s "$W" -o "$DIR" "$SVG" >/dev/null 2>&1
  GEN="$DIR/$(basename "$SVG").png"
  [ -f "$GEN" ] && mv "$GEN" "$OUT" && { echo "$OUT (qlmanage — square-padded, may crop wide diagrams)"; exit 0; }
fi

echo "no SVG renderer found. Install one:  brew install librsvg   (rsvg-convert)  or  pip install cairosvg" >&2
exit 1
