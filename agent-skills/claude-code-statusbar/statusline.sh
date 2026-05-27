#!/bin/bash
# Claude Code status line: model (context size) + color-coded usage %
# Thresholds: green <80%, orange 80-84%, red >=85%
# Alerts (macOS, once per session):
#   33% — passive notification
#   85% — blocking dialog: "save context before auto-compaction"
#   90% — blocking dialog: "compact now to avoid losing context"
#   95% — blocking dialog: "auto-compact imminent"

input=$(cat)

MODEL=$(echo "$input" | jq -r '.model.display_name // "?"')
MODEL_ID=$(echo "$input" | jq -r '.model.id // ""')
SIZE=$(echo "$input" | jq -r '.context_window.context_window_size // 200000')
PCT=$(echo "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)

# Strip any parenthesized suffix from display_name (e.g. "Opus 4.7 (1M context)" -> "Opus 4.7")
MODEL=$(echo "$MODEL" | sed -E 's/ *\([^)]*\) *$//')

# Append version from model.id (e.g. "claude-opus-4-7" -> "4.7") if not already in display name
VERSION=$(echo "$MODEL_ID" | grep -oE '[0-9]+-[0-9]+' | tr - .)
if [ -n "$VERSION" ] && [[ "$MODEL" != *"$VERSION"* ]]; then
  MODEL="$MODEL $VERSION"
fi

# Format context size: 1000000 -> 1M, 200000 -> 200k
if [ "$SIZE" -ge 1000000 ]; then
  SIZE_LABEL="$((SIZE/1000000))M"
elif [ "$SIZE" -ge 1000 ]; then
  SIZE_LABEL="$((SIZE/1000))k"
else
  SIZE_LABEL="$SIZE"
fi

# Color by usage threshold
if [ "$PCT" -ge 85 ]; then
  COLOR='\033[31m'        # red
elif [ "$PCT" -ge 80 ]; then
  COLOR='\033[38;5;208m'  # orange (256-color)
else
  COLOR='\033[32m'        # green
fi
DIM='\033[2m'
RESET='\033[0m'

# Build usage bar: filled (▓) = used in threshold color, empty (░) = available, dim
BAR_WIDTH=20
FILLED=$((PCT * BAR_WIDTH / 100))
EMPTY=$((BAR_WIDTH - FILLED))
BAR=""
if [ "$FILLED" -gt 0 ]; then
  printf -v FILL "%${FILLED}s"
  BAR="${COLOR}${FILL// /▓}${RESET}"
fi
if [ "$EMPTY" -gt 0 ]; then
  printf -v PAD "%${EMPTY}s"
  BAR="${BAR}${DIM}${PAD// /░}${RESET}"
fi

# macOS alerts
SESSION_ID=$(echo "$input" | jq -r '.session_id // "unknown"')
ALERT_DIR="$HOME/.claude/.statusline-alerts"
mkdir -p "$ALERT_DIR" 2>/dev/null

if command -v osascript >/dev/null; then
  # 33% — passive notification, fires once per session
  ALERT_33="$ALERT_DIR/${SESSION_ID}-33"
  if [ "$PCT" -ge 33 ] && [ ! -f "$ALERT_33" ]; then
    touch "$ALERT_33"
    osascript -e "display notification \"Context window at ${PCT}%\" with title \"Claude Code\" subtitle \"${MODEL} (${SIZE_LABEL})\"" 2>/dev/null &
  fi

  # Escalating blocking dialogs — each fires once per session
  for threshold in 85 90 95; do
    case "$threshold" in
      85) msg="Context window critical: ${PCT}% used.\n\nSave your session context before auto-compaction." ;;
      90) msg="Context window very high: ${PCT}% used.\n\nCompact now to avoid losing context." ;;
      95) msg="Context window imminent compaction: ${PCT}% used.\n\nAuto-compact will trigger soon." ;;
    esac
    ALERT_FILE="$ALERT_DIR/${SESSION_ID}-${threshold}"
    if [ "$PCT" -ge "$threshold" ] && [ ! -f "$ALERT_FILE" ]; then
      touch "$ALERT_FILE"
      osascript -e "display dialog \"${msg}\" with title \"Claude Code — ${MODEL} (${SIZE_LABEL})\" buttons {\"OK\"} default button \"OK\" with icon caution" >/dev/null 2>&1 &
    fi
  done
fi

echo -e "${COLOR}${MODEL} (${SIZE_LABEL})${RESET} ${BAR} ${COLOR}${PCT}%${RESET}"
