---
name: distill-user
description: Mine the user's local Claude Code transcript history for their REPEATED requests, suggestions, checks, challenges, preferences, and dislikes, then distill them into candidate memory rules with verbatim evidence and persist the approved ones. Use whenever the user asks to distill/learn their preferences, refresh or build their user profile from history, complains about repeating themselves ("I already told you", "why do I keep saying this"), wants memory rules generated from past sessions, or when a fresh correction hints at a long-standing preference worth back-checking against history.
---

# Distill User

Turn transcript history into durable user knowledge. A user who has worked with Claude Code for
weeks has already *demonstrated* their preferences hundreds of times — in corrections, repeated
asks, standing checks, and things they pushed back on. This skill mines that evidence so the user
never has to say the same thing twice.

## Why this exists

Memory systems capture what gets noticed in the moment. But the strongest signal of what a user
cares about is **repetition across sessions** — and no single session can see it. The transcripts
on disk (`~/.claude/projects/**/*.jsonl`) are the ground truth: every user message, timestamped,
across every project. Mining them finds the rules the user has been teaching implicitly all along.

## What counts as a signal

Look for these six shapes in USER messages (each maps to a candidate rule type):

| Shape | Sounds like | Candidate rule |
|---|---|---|
| **Repeated request** | the same ask appearing in 2+ sessions | do it by default |
| **Suggestion** | "would be better to…", "next time…" | adopt as standing practice |
| **Check** | "verify against official docs", "which is latest?", "good to push?" | run the check proactively |
| **Challenge** | "are you sure?", "confirm X?", "how solid is this?" | pre-empt with evidence in answers |
| **Preference** | "I like/love/enjoy…", "always use…" | preserve and lean into it |
| **Dislike** | "I don't like…", "why do you keep…", "never…" | hard avoid |

Corrections are the highest-value signal: a user interrupting to redirect ("wait, careful about…",
"no — what I meant was…") is teaching, and the lesson usually generalizes beyond the moment.

## Workflow

### 1. Scope

**Default: workspace-scoped** — only the transcript directories of the project folders this session
can already access (the current workspace's `~/.claude/projects/<encoded-path>` entries), last 30
days. This keeps the default run inside the user's existing permission surface.

**Global-wide is opt-in:** scanning ALL project directories under `~/.claude/projects/` (the user's
whole footprint) reads conversations from every project — including ones outside this workspace's
remit — so ASK the user for explicit permission first (a pop-up question, not a buried assumption)
before running the extractor with the full projects dir. Preferences are user-level, so the global
scan gives the best signal — say that when asking — but the user decides.

State the chosen scope and time window before running either way.

### 2. Extract (deterministic, cheap)

Run the bundled extractor — never parse the raw JSONL by hand; transcripts are full of tool
results, command outputs, and system reminders that must be filtered out:

```bash
python3 scripts/extract_user_messages.py \
  --projects-dir ~/.claude/projects \
  --days 30 \
  --out <workspace>/tmp/distill-user/
```

It emits clean, size-capped batch files (`batch-01.jsonl`, …) of genuine user messages only —
`{session, project, ts, text}` — with long pastes truncated. Batches are sized so one batch fits
comfortably in one subagent's context.

### 3. Cost alert, then fan out analysis workers (parallel, background)

**Before launching anything, tell the user what this run will cost.** The extractor's summary
gives the batch count; the fan-out is one worker per batch plus one gatekeeper. State it plainly:

> "N batches → N workers + 1 gatekeeper ≈ ~(N × 50k + 100k) tokens total
> (calibration: a ~90KB batch costs a worker ~45–55k tokens). Proceed?"

**Worker model choice:** use the user's approved default worker model at low/medium effort —
"cheap worker" should mean cheap *effort*, not automatically the smallest model tier. Do not drop
to the smallest tier (e.g. Haiku-class) without the user's explicit approval: preference-mining
needs enough judgment to tell a real preference from noise, and a too-small worker returns
plausible-looking patterns that pollute memory. The gatekeeper is never downgraded.

Fold this into the same confirmation as the scope statement (and the global-scan permission
pop-up when applicable) so the user approves scope + cost in ONE question, not two. Skipping this
on a small run (1–2 batches) is fine; never skip it when fanning out more than a handful of
agents — subagent fan-outs are the dominant token cost of this skill and the user may be on a
metered plan.

One subagent per batch, launched **in a single message, in the background** — the conversation
must keep flowing while they grind. Workers get NO access to existing memory (unbiased: they
report everything they see). Worker brief:

> Read the batch file at <path>. It contains one user's messages across Claude Code sessions.
> Identify every repeated request, suggestion, check, challenge, preference, and dislike —
> anything the user said that implies "this is how I want the AI to behave." For each, return:
> `{pattern: one-sentence rule in imperative form, type: request|suggestion|check|challenge|preference|dislike,
> quotes: [{session, date, verbatim ≤200 chars}], sessions_seen: N}`.
> Include single-occurrence items ONLY if strongly worded (corrections, "never", "always", "I hate").
> Return raw JSON, nothing else.

Use cheap/medium effort for workers; their context is fresh and the task is pattern-spotting,
not judgment.

### 4. Gatekeeper synthesis (high effort)

While workers run, gather the existing-knowledge corpus: the auto-memory index (`MEMORY.md`) +
individual memory files, `~/.claude/CLAUDE.md`, and any user-maintained profile doc it points to.

When workers report, spawn ONE high-effort gatekeeper with (a) all worker JSON, (b) the existing
corpus. Its job:

1. **Cluster** near-duplicate patterns across batches; sum occurrence counts; keep the best quotes.
2. **Diff against existing knowledge** — classify each cluster:
   - `NEW` — not captured anywhere → candidate rule
   - `REINFORCES` — already captured; note the extra evidence (worth strengthening the memory's wording if the evidence is much stronger than the memory implies)
   - `CONTRADICTS` — existing memory says otherwise → surface loudly; the newer/more-repeated signal usually wins, but the USER decides
3. **Rank** by (occurrence count × strength of wording), and drop weak one-offs.
4. Emit the report (format below).

### 5. Report → ONE approval gate

Write the report to `<workspace>/tmp/distill-user/report.md`. **Before asking for any approval,
give the user the reading list first**: the report's FULL path, plus the full paths of the current
knowledge docs it was diffed against (memory index + memory dir, global CLAUDE.md, the curated
profile doc) — so they can read the proposal side-by-side with the current state in their own
editor. Then present the summary in the conversation and ask the single approval question only
after they've had the paths. Report structure:

```markdown
# User distillation — <date> · <N> sessions, <M> messages scanned

## NEW candidate rules (not in memory yet)
### 1. <imperative rule> (<type>, seen in <K> sessions)
> "<verbatim quote>" — <session/date>
> "<verbatim quote>" — <session/date>
Proposed memory: `feedback_<slug>.md` | `user_<slug>.md`

## REINFORCES existing memory (evidence counts, no action needed unless wording should strengthen)
## CONTRADICTS existing memory (user must rule)
```

Ask ONCE which candidates to persist (default: all NEW). This is the single approval gate.

### 6. Persist

For each approved rule, write a memory file in the user's auto-memory directory following its
frontmatter convention (`type: feedback` for behavioral guidance, `type: user` for identity/
preferences), including the **verbatim quotes + dates as evidence**, a **Why**, and a **How to
apply**. Add one index line each to `MEMORY.md`. If the user maintains a curated profile doc that
is owned by a different session (a common pattern), output suggested lines for it — do not edit it.

## Privacy (non-negotiable)

Everything stays local: transcripts are read from disk, analysis runs in local subagents, the
report lands in the workspace tmp dir. Never send transcript content to external services, never
commit the report or batch files to a repo (they contain raw conversation content), and remind the
user the report may quote sensitive material before they share it anywhere.

## The learnings file (self-tuning, adapted from claude-improve)

Keep `distill-learnings.md` next to the user's MEMORY.md. After each approval gate, append one
line per candidate: `date · rule-slug · accepted|rejected|modified · occurrence-count`. Before
building the next report, read it: patterns the user rejected before get proposed again ONLY with
materially stronger evidence, and the gatekeeper can note "similar to X you rejected on <date>".
This keeps the skill from making the user repeat their *no* — the same courtesy as the rest of it.

## Prior art (credit where due)

This skill adapts ideas from two MIT/OSS projects that independently converged on the pattern:
[TerenceBristol/claude-improve](https://github.com/TerenceBristol/claude-improve) (signal-word
filtering, the 2+-recurrence promotion threshold, grep-diff anti-duplication, the learnings file)
and [bokan/claude-skill-self-improvement](https://github.com/bokan/claude-skill-self-improvement)
(the lean JSONL→parallel-subagents→diff→proposal shape). Differences here: global cross-project
scope (preferences are user-level, not project-level), a deterministic extractor script instead of
agents parsing raw JSONL, one batch approval gate instead of per-item questioning, and output
targeting the auto-memory file convention rather than CLAUDE.md.

## Failure honesty

If the extractor finds few sessions or the workers return thin results, say so — do not pad the
report with weak inferences. A rule proposed from one mild mention is worse than no rule: it
pollutes memory with noise the user then has to correct (the exact failure this skill exists to
prevent).
