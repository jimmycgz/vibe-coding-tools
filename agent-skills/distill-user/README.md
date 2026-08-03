# Distill User

Mine your own Claude Code transcript history for the things you've said **more than once** —
repeated requests, standing checks, corrections, preferences, dislikes — and turn them into
durable memory rules, with verbatim evidence, behind a single approval gate.

Memory systems capture what gets noticed in the moment. The strongest signal of what you care
about is repetition *across* sessions, and no single session can see it. Your transcripts on
disk are the ground truth. This skill mines them so you never have to say the same thing twice.

## Disclaimer

**Provided "as is", used entirely at your own risk.**

- **No warranty (as-is).** This skill — including its instructions and scripts — is provided
  "AS IS", **without warranty of any kind**, express or implied, including but not limited to
  merchantability, fitness for a particular purpose, and non-infringement. No guarantee is made
  that it is secure, error-free, or suitable for any purpose.
- **Limitation of liability.** In no event shall the authors or contributors be liable for any
  claim, damages, or other liability — including data loss, privacy exposure, or unintended
  actions taken by an AI agent or a shell command — whether in contract, tort, or otherwise,
  arising from or in connection with this software or its use.
- **You are responsible** for the scope you approve, the token spend you authorise, what the
  generated report contains, and anything you choose to persist to memory or share.

## Read this before running it

This skill reads your **conversation history** — every user message across the projects in
scope. That is inherently sensitive material, so:

- **Everything stays local.** Transcripts are read from disk, analysis runs in local subagents,
  and the report is written to your workspace `tmp/` directory. Nothing is sent to an external
  service.
- **The default scope is the current workspace only**, last 30 days. Scanning *all* projects is
  opt-in and the skill must ask you first.
- **The report and batch files quote your raw conversations verbatim.** Never commit them to a
  repo, and re-read the report before sharing it anywhere — it may quote material you'd rather
  not circulate. Add `tmp/` to `.gitignore` if it isn't already.
- **It costs real tokens.** The skill fans out one subagent per batch plus a gatekeeper, and it
  is required to quote you an estimate and get approval before launching anything.

## Install

Symlink into your skills directory:

```bash
ln -s "$PWD/agent-skills/distill-user" ~/.claude/skills/distill-user
```

The extractor is pure Python 3 stdlib — no dependencies to install.

## Use

Just ask — the skill triggers on requests like "distill my preferences", "build my user profile
from history", "generate memory rules from past sessions", or when you complain about repeating
yourself ("why do I keep telling you this?").

What happens, in order:

1. **Scope** — states the projects and time window; asks permission before any global scan.
2. **Extract** — `scripts/extract_user_messages.py` filters genuine user messages out of the raw
   JSONL (dropping tool results, command output, system reminders) into size-capped batches.
3. **Cost alert** — tells you the batch count and estimated token spend, then asks to proceed.
4. **Analyse** — one background subagent per batch, none of which can see your existing memory,
   so they report what's actually there rather than confirming what's already recorded.
5. **Synthesise** — one high-effort gatekeeper clusters the findings and diffs them against your
   current memory, classifying each as `NEW`, `REINFORCES`, or `CONTRADICTS`.
6. **Approve once** — you get the report path and the paths of everything it was diffed against,
   so you can read them side by side. One question, not a per-item interrogation.
7. **Persist** — approved rules are written as memory files with their verbatim evidence.

Run the extractor standalone if you just want the cleaned batches:

```bash
python3 scripts/extract_user_messages.py \
  --projects-dir ~/.claude/projects \
  --days 30 \
  --out ./tmp/distill-user/
```

`--out` is required. `--days` defaults to 30; `--max-sessions 0` means no cap.

## It learns from your rejections too

A `distill-learnings.md` file is kept next to your `MEMORY.md`, logging each candidate as
accepted, rejected, or modified. Rules you've already turned down are only re-proposed with
materially stronger evidence — so the skill doesn't make you repeat your *no* either.

## What's in the box

- `SKILL.md` — agent-facing guidance: the six signal shapes, the full workflow, worker briefs,
  report format, and the privacy rules.
- `scripts/extract_user_messages.py` — the deterministic transcript extractor.

## Prior art

Adapts ideas from [TerenceBristol/claude-improve](https://github.com/TerenceBristol/claude-improve)
(signal-word filtering, the 2+-recurrence threshold, the learnings file) and
[bokan/claude-skill-self-improvement](https://github.com/bokan/claude-skill-self-improvement)
(the JSONL → parallel subagents → diff → proposal shape). Differences here: cross-project scope,
a deterministic extractor instead of agents parsing raw JSONL, one batch approval gate, and
output targeting the auto-memory file convention rather than `CLAUDE.md`.
