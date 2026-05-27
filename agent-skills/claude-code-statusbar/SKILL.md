---
name: claude-code-statusbar
description: Install, test, customize, or uninstall the Claude Code status bar — a color-coded bottom line showing model, context size, a 20-char usage bar, and escalating macOS popups at 33%, 85%, 90%, 95% context usage. Use when the user mentions status line, status bar, context monitoring, usage alerts, or context-window popups.
---

# Claude Code status bar

Color-coded `statusLine` showing model name, context size, usage bar, and percentage — plus escalating macOS notifications/dialogs as context fills up.

Sample output:
```
Opus 4.7 (1M) ▓▓▓▓▓▓░░░░░░░░░░░░░░ 31%
```

Color tiers (used portion of bar + the percent text):
- **green** <80%
- **orange** 80–84%
- **red** ≥85%

macOS alerts (each fires once per session, never repeats):
- **33%** — passive notification "Context window at NN%"
- **85%** — blocking dialog "save your session context before auto-compaction"
- **90%** — blocking dialog "compact now to avoid losing context"
- **95%** — blocking dialog "auto-compact will trigger soon"

The canonical script lives next to this file at `statusline.sh`.

---

## When invoked, ask the user what they want

When `/claude-code-statusbar` is invoked, present these options and act on the user's choice:

1. **Install** — copy `statusline.sh` to `~/.claude/statusline.sh` and add the `statusLine` block to `~/.claude/settings.json`
2. **Test** — temporarily lower thresholds so all three dialogs fire quickly without waiting for real context to fill up
3. **Restore production thresholds** — set back to 80/85/90/95 after testing
4. **Customize** — edit thresholds, colors, dialog wording, or bar width
5. **Uninstall** — rename `statusline.sh` with a timestamp suffix and remove the `statusLine` block from settings.json

---

## Install

1. Copy this skill's `statusline.sh` to `~/.claude/statusline.sh` (do **not** chmod; the settings.json command invokes via `bash`).
2. Read `~/.claude/settings.json`, merge in the following block at the top level (preserve all existing keys):
   ```json
   "statusLine": {
     "type": "command",
     "command": "bash ~/.claude/statusline.sh",
     "padding": 2
   }
   ```
3. The status line refreshes on the next assistant message — no restart needed.

---

## Test mode — verify all alerts work in seconds

Real context usage takes a long session to reach 85%+. To verify the popup logic works in a fresh shell session, temporarily lower the thresholds in `~/.claude/statusline.sh`.

Edit two regions:

**Color thresholds** (around line 30):
```bash
if [ "$PCT" -ge 34 ]; then          # was 85
  COLOR='\033[31m'        # red
elif [ "$PCT" -ge 32 ]; then        # was 80
  COLOR='\033[38;5;208m'  # orange
else
  COLOR='\033[32m'        # green
fi
```

**Dialog thresholds** (the `for threshold in 85 90 95` loop):
```bash
for threshold in 34 36 38; do       # was 85 90 95
```

Then trigger any message in Claude Code. With context already past 38%, the status line refresh will fire all three dialogs in sequence (and turn red). Click OK on each.

**Important:** also clear the per-session alert markers so the dialogs can re-fire if you re-test the same session:
```bash
ls ~/.claude/.statusline-alerts/<session-id>-*    # find markers
# then rename them with timestamp instead of rm:
mv ~/.claude/.statusline-alerts/<session-id>-85 ~/.claude/.statusline-alerts/TO-DELETE-<DATE>-<session-id>-85
```

---

## Restore production thresholds

After verifying the test fires correctly, revert the two regions:
- Colors: `34` → `85` and `32` → `80`
- Dialog loop: `for threshold in 34 36 38` → `for threshold in 85 90 95`

The dialog message strings are tied to the threshold values inside the `case` statement — leave those alone unless you're changing the production threshold numbers.

---

## Customize

| What | Where |
|---|---|
| Bar width | `BAR_WIDTH=20` (each block = 100/N percent) |
| Colors | ANSI codes near `COLOR=` lines. Red `\033[31m`, orange `\033[38;5;208m` (256-color), green `\033[32m`, dim `\033[2m`, reset `\033[0m` |
| Bar characters | `▓` (used) and `░` (empty) in the `BAR=` lines |
| Dialog wording | The `case "$threshold"` block — keep `\n\n` for line breaks |
| Notification threshold (33%) | `ALERT_33` block |
| Add/remove escalation tiers | The `for threshold in 85 90 95` loop + matching `case` arms |
| Show cost / git branch / etc. | Add `jq` extraction of `.cost.total_cost_usd`, `.workspace.repo.name`, etc. See <https://code.claude.com/docs/en/statusline> for full JSON schema |

---

## Uninstall

Rename instead of removing (safer; lets you restore):

1. Rename script: `mv ~/.claude/statusline.sh ~/.claude/TO-DELETE-<DATE>-statusline.sh`
2. Read `~/.claude/settings.json`, remove the `statusLine` block (keep all other keys)
3. Optionally clean up `~/.claude/.statusline-alerts/` (rename with timestamp prefix, don't `rm`)

The status line disappears on next assistant message.

---

## Notes

- Requires `jq` on `$PATH` (preinstalled on most macOS setups; `brew install jq` otherwise).
- macOS-only for the popups (`osascript`). On Linux, the dialog blocks are silently skipped — the status line still renders.
- Alert markers live at `~/.claude/.statusline-alerts/<session-id>-<threshold>`. To re-arm an alert in the same session, rename the corresponding marker.
- Reference docs: <https://code.claude.com/docs/en/statusline>
