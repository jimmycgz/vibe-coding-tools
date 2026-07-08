#!/bin/bash
# svg_lint_hook.sh — PostToolUse hook wrapper for deterministic SVG QA.
#
# Wire this as a Claude Code PostToolUse hook on Write|Edit|MultiEdit. The harness
# runs it after every such tool call, passing the tool payload as JSON on stdin.
# If the edited/written file is a .svg, this runs the geometry linter and surfaces
# the result back to the model as hook feedback — so SVG QA happens whether or not
# the svg-diagram-qa skill was invoked. It NEVER blocks (exit 0 always); it only
# reports, nudging the model to render-and-look per the skill.
#
# settings.json:
#   "hooks": {
#     "PostToolUse": [
#       { "matcher": "Write|Edit|MultiEdit",
#         "hooks": [ { "type": "command",
#           "command": "bash /Users/jcui/.claude/skills/svg-diagram-qa/scripts/svg_lint_hook.sh" } ] }
#     ]
#   }

HERE="$(cd "$(dirname "$0")" && pwd)"
payload="$(cat)"

# Extract the target file path from the tool payload (jq if present, else grep fallback).
if command -v jq >/dev/null 2>&1; then
  file="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null)"
else
  file="$(printf '%s' "$payload" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]+"' | head -1 | sed -E 's/.*"file_path"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/')"
fi

case "$file" in
  *.svg)
    if [ -f "$file" ]; then
      out="$(python3 "$HERE/svg_lint.py" "$file" 2>&1)"
      if printf '%s' "$out" | grep -q '^✗'; then
        # Findings: report as additionalContext so the model sees and acts on them.
        printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":%s}}\n' \
          "$(printf '%s\n\nsvg-diagram-qa: geometry findings above. Render the SVG to PNG and look at it (scripts/render.sh), then fix.' "$out" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
      fi
    fi
    ;;
esac
exit 0
