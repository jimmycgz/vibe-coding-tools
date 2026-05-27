# claude-code-statusbar

A personal Claude Code skill that installs a color-coded `statusLine` showing model, context window size, a 20-block usage bar, and escalating macOS popup alerts as context fills up.

Invoke with `/claude-code-statusbar` to install, test, customize, or uninstall.

## Visual reference

The bar colors track three thresholds — used portion of the bar **and** the percentage text both change color together.

### Green — under 80%

![Green status bar at 30%](assets/bar-green.svg)

### Orange — 80–84%

![Orange status bar at 82%](assets/bar-orange.svg)

### Red — 85% and above

![Red status bar at 91%](assets/bar-red.svg)

## Alerts (macOS)

Each fires **once per session**:

| Threshold | Type | Message |
|---|---|---|
| 33% | Passive notification | "Context window at NN%" |
| 85% | Blocking dialog (OK) | "Save your session context before auto-compaction." |
| 90% | Blocking dialog (OK) | "Compact now to avoid losing context." |
| 95% | Blocking dialog (OK) | "Auto-compact will trigger soon." |

Markers live at `~/.claude/.statusline-alerts/<session-id>-<threshold>`. To re-arm an alert in the same session, rename (don't delete) the corresponding marker.

## Install

Two options.

### Option A — copy by hand

```bash
mkdir -p ~/.claude
cp statusline.sh ~/.claude/statusline.sh
```

Then merge this into `~/.claude/settings.json` (preserve existing keys):

```json
{
  "statusLine": {
    "type": "command",
    "command": "bash ~/.claude/statusline.sh",
    "padding": 2
  }
}
```

### Option B — let Claude Code do it

Drop this skill folder into `~/.claude/skills/claude-code-statusbar/`, then run `/claude-code-statusbar` and pick **Install**.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | Skill instructions: install / test / restore / customize / uninstall |
| `statusline.sh` | Canonical bash script. Installed to `~/.claude/statusline.sh` |
| `assets/bar-*.svg` | This README's color samples |

## Requirements

- `jq` on `$PATH` (`brew install jq` if missing)
- macOS for the popups (`osascript`). On Linux the bar still renders; dialogs are silently skipped.
- Claude Code with `statusLine` support

## Reference

- [Claude Code statusline docs](https://code.claude.com/docs/en/statusline)
- [Skill format docs](https://code.claude.com/docs/en/skills)

## License

See the repository root `LICENSE` file.
