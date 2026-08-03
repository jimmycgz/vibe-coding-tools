# Markdown Render QA

Catches Markdown that **reads fine as raw text but renders wrong** — merged header lines,
silently-dropped line breaks, ineffective hard breaks — and helps decide whether a given
deliverable should be Markdown or HTML in the first place.

Markdown's worst failure mode is invisible. There's no parser error and no lint warning by
default: the source looks exactly like what you intended, and the rendered output quietly
isn't. A four-line `**Field:** value` block becomes one run-on paragraph. A two-line title
collapses into one heading. You don't find out until someone reads the published version.

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

## What it checks

| Finding | Severity | Meaning |
|---|---|---|
| `SETEXT-MULTILINE` | WARN | Multi-line title above a `===`/`---` underline — collapses to one rendered line |
| `LITERAL-BACKSLASH-HEADING` | WARN | Trailing `\` on an ATX heading renders as a literal backslash, not a break |
| `INEFFECTIVE-HARD-BREAK` | WARN | Exactly one trailing space — CommonMark needs 2+, or a backslash |
| `BOLD-LABEL-MERGE` | WARN | Consecutive `**Field:**` lines with nothing between them — join into one paragraph |
| `FRAGILE-HARD-BREAK` | INFO | A working 2-space break — correct, but invisible and easy to strip by accident |

Deliberately narrow and low-noise. It does **not** flag ordinary soft-wrapped prose — a
paragraph wrapped across lines and joined with a space at render time is CommonMark working as
designed. Fenced code blocks and YAML frontmatter are skipped automatically.

## Install

Symlink into your skills directory:

```bash
ln -s "$PWD/agent-skills/markdown-render-qa" ~/.claude/skills/markdown-render-qa
```

No dependencies — `md_lint.py` is pure Python 3 stdlib (`argparse`, `re`, `sys`). Nothing to
install, no network access, no permission-allowlist changes needed.

## Use

**With an agent.** Just ask — the skill triggers on requests like "check this markdown renders
right", "the header lines merged", "should this report be markdown or HTML?", or before
finalizing any doc.

**Standalone**, as a plain CLI:

```bash
python3 ~/.claude/skills/markdown-render-qa/scripts/md_lint.py path/to/doc.md
```

Takes one or more paths. Exit `0` = clean, `1` = findings, so it wires straight into a
pre-commit or pre-publish gate:

```bash
python3 scripts/md_lint.py docs/*.md || echo "fix the findings above before publishing"
```

Try it against the bundled fixtures to see every finding type at once:

```bash
python3 scripts/md_lint.py scripts/test-fixtures.md
```

## The linter is not the whole job

Same discipline as `svg-diagram-qa`: the linter is a heuristic that tells you *where to look*.
It does not replace **rendering the file and reading it** — in VS Code (`Cmd+Shift+V`), and in
whichever renderer the doc will actually be read through, since fidelity varies by engine. For
a doc going to several destinations, check the least forgiving one.

`SKILL.md` covers the rest: how to tell a collapsed setext heading from a soft-line-break
problem (the fix differs), why to prefer a visible `\` or `<br>` over invisible trailing
spaces, and a per-case table for choosing Markdown vs HTML.

## What's in the box

- `SKILL.md` — the agent-facing guidance, diagnosis walkthrough, and format-choice table.
- `scripts/md_lint.py` — the deterministic checker.
- `scripts/test-fixtures.md` — a worked example exercising all five finding types plus the
  false-positive guards (frontmatter, fenced code, ordinary prose, a real `---` thematic break).
  Useful as a regression check if you modify the linter.
