---
name: markdown-render-qa
description: Catch Markdown that reads fine as raw text but renders wrong — merged header lines, silently-dropped line breaks, ineffective single-trailing-space "hard breaks" — and judge when a report/doc should be Markdown vs HTML in the first place. Use before finalizing any markdown doc/report, whenever multi-line titles or headers look suspicious, or when deciding output format for a deliverable.
---

# Markdown Render QA

Markdown's biggest failure mode is invisible: the raw text looks exactly like
what you intended, and it renders as something else. No parser error, no lint
warning by default — just a header that quietly became one line, or a
paragraph break that vanished. This skill catches that class of bug, and
separately, helps decide whether Markdown is even the right format to begin
with.

## Part 1 — Why "the header lines merged" almost never means what it sounds like

If a heading looks fine in the source but merges at render time, resist the
instinct to blame "a missing trailing double-space." **ATX headings
(`#`/`##`/etc.) are structurally single-line in CommonMark** — even a stray
trailing backslash on one renders as a literal `\` character, not a line
break. Headings cannot span multiple raw lines, full stop.

What's actually happening is almost always one of:
1. **A setext heading** (`Title\n===` or `Title\n---` underline style) whose
   title text spans more than one raw line — setext content parses as a
   single inline run, so multi-line titles collapse into one rendered line.
   This is the most common real cause of "my header merged."
2. **A paragraph or bold-text line being used as a pseudo-heading** — hitting
   CommonMark's default soft-line-break rule: a single `\n` renders as a
   space, not a break, unless the line ends in 2+ spaces or a backslash.

Diagnose which one you actually have before reaching for a fix — the fix is
different (restructure the setext heading vs. add a real hard break).

## Part 2 — Run the linter

```bash
python3 <skill>/scripts/md_lint.py path/to/doc.md
```

Deliberately narrow, deliberately low-noise — it does **not** flag ordinary
soft-wrapped prose (a paragraph wrapped across lines and joined with a space
at render time is CommonMark working as designed, not a bug). It flags only
the well-understood, usually-unintentional failure modes:

| Finding | Meaning |
|---|---|
| `SETEXT-MULTILINE` | multi-line title before a `===`/`---` underline — will collapse to one rendered line |
| `LITERAL-BACKSLASH-HEADING` | trailing `\` on an ATX heading renders literally, not as a break |
| `INEFFECTIVE-HARD-BREAK` | exactly one trailing space — needs 2+, or a backslash |
| `FRAGILE-HARD-BREAK` (info, not an error) | a working 2-space hard break — correct, but invisible and easy to strip by accident |
| `BOLD-LABEL-MERGE` | consecutive `**Field:**`-style lines with no blank line/hard break between them — collapse into one paragraph. Caught this exact bug live in production (a 4-line speaker/format/audience/predecessor block rendering as one line). |

Skips fenced code blocks and YAML frontmatter automatically. Exit 0 = clean,
1 = findings — wire it as a pre-commit/pre-publish gate if useful.

## Part 3 — Render and look (the step no existing tool does)

The linter is a heuristic, same discipline as `svg-diagram-qa`: it tells you
where to look, it doesn't replace looking. After lint is clean, actually
render the file and read it:

- VS Code: `Cmd+Shift+V` (Markdown preview) — fastest loop for iterating.
- Any renderer the doc will actually be READ through if it differs (GitHub's
  own preview, a wiki, a docs site) — render fidelity varies by engine, and
  the linter can't know which one matters for a given doc.

For a doc going to multiple destinations (e.g., committed to GitHub *and*
pasted into Slack *and* opened in VS Code), check the riskiest one — usually
whichever renders the least forgivingly.

## Part 4 — The fix pattern (prefer visible over invisible)

When a hard break is genuinely needed, prefer:
1. **A trailing backslash** (`\`) — visible in the raw text, survives
   trim-trailing-whitespace editor/linter settings, safe in git diffs.
2. **An explicit `<br>`** — unambiguous, CommonMark passes raw inline HTML
   through untouched, renders identically almost everywhere.

Avoid relying on invisible double-trailing-spaces for anything that matters —
it's real CommonMark syntax and it works, but it's silently strippable by an
editor's "trim trailing whitespace on save," a linter with `MD009 br_spaces`
misconfigured to 0, or a teammate who can't see it's there. (If you're
already running `markdownlint`, its `MD009` rule defaults to `br_spaces: 2`
specifically so it won't eat real hard breaks — verify that hasn't been
overridden to 0 in your config, which is the most common way teams break
their own intentional line breaks.)

## Part 5 — Markdown vs. HTML: judging the format itself

Sometimes the real fix isn't a better hard break — it's realizing the
destination doesn't want Markdown at all. There's a real, sourced argument
(an Anthropic Claude Code engineer's "Unreasonable Effectiveness of HTML"
piece) that HTML's structural precision beats Markdown's ambiguity for
finished, read-only, presentational output — at the honest cost of more
tokens and harder hand-editing. It's one engineer's view, not an Anthropic
institutional position (Anthropic's own tool-design guidance explicitly says
"no one-size-fits-all — evaluate for your case" and doesn't endorse a format).

Use this table to make the call per case, not by default:

| Signal | Format | Why |
|---|---|---|
| Will be hand-edited later (specs, CLAUDE.md, README, PR body) | **Markdown** | Diff-friendly, editable anywhere, degrades to readable plain text if a renderer fails |
| Destination is GitHub/GitLab/Jira/Slack | **Markdown** | Native renderers; raw HTML often gets stripped or escaped |
| Terminal/CLI chat pane, no HTML renderer available | **Markdown (light)** | Unrendered HTML shows as literal tags |
| Needs real interactivity (tabs, filters, live state) | **HTML/artifact** | Markdown can't express interactivity at all |
| Finished, read-only, presentational report/deck, viewed once or exported to PDF | **HTML** | Precise layout/structure Markdown can't guarantee |
| High-volume/automated pipeline, token- or cost-constrained | **Markdown or plain text** | Markdown is meaningfully cheaper in tokens; verbosity compounds at scale |
| Might be piped/emailed/viewed in an unknown or failing renderer | **Markdown or plain text** | Degrades gracefully; broken HTML looks visibly broken |
| No clear signal, quick conversational answer | **Plain Markdown, minimal formatting** | Don't reach for HTML "for richness" on a short-lived interaction |

## Reference implementation

- `scripts/md_lint.py` — the deterministic checker (Part 2).
- `scripts/test-fixtures.md` — a worked example exercising all four finding
  types plus the false-positive guards (frontmatter, fenced code, ordinary
  prose, a real thematic-break `---`) — useful as a regression check if you
  ever modify the linter.
