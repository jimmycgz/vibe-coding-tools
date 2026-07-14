# internet-search

A Claude Code / agent skill for **efficient, route-independent internet search**. It prefers precise
domain catalogs (GitHub, Stack Overflow, arXiv, Hugging Face, package registries) over generic web
search, treats every result as unverified until a live fetch confirms it, and fans out parallel
workers only when a question is genuinely broad. It needs **no WebSearch tool and no API keys** —
so it works even on hosts where the built-in web search is blocked by org policy.

The model-facing instructions live in [`SKILL.md`](SKILL.md); endpoint templates in
[`references/endpoints.md`](references/endpoints.md); worked scenarios in
[`references/use-cases.md`](references/use-cases.md).

## Why this exists

Two problems with the reflexive "just call web search":

1. **It can be turned off under you.** The native WebSearch tool runs *server-side* on the model
   provider, so a cloud/org policy (e.g. Claude routed through Vertex AI or Bedrock) can disable it —
   and then every search, in the main session and every subagent, fails with a policy error. This
   skill runs over your machine's own client-side HTTPS, which no provider policy can switch off.
2. **Generic web rank is the wrong tool for most technical questions.** A question about code,
   packages, papers, or models has a *purpose-built index* — GitHub stars, Stack Overflow votes,
   Hugging Face downloads, arXiv citations — that understands the question far better than open-web
   PageRank, and returns structured JSON at a fraction of the token cost. Web search is the
   last-resort catalog, not the first.

The governing rule is **"the index is a rumor; the fetch is the fact."** Search indexes serve
cached/stale entries, so any hit — from any engine, including native WebSearch — is a *candidate*
until a live fetch confirms it. Nothing gets cited that wasn't fetched this turn.

## How it relates to (and competes with) `deep-research`

Claude Code ships a built-in **`deep-research` workflow** (Scope → parallel Search → Fetch → 3-vote
adversarial Verify → Synthesize into a cited report). This skill overlaps it deliberately but sits
in a different niche:

| | **internet-search** (this skill) | **deep-research** (built-in workflow) |
|---|---|---|
| Trigger | Any search/lookup, no opt-in | Requires explicit opt-in ("use a workflow" / ultracode) |
| Depends on WebSearch tool | **No** — client-side catalogs + WebFetch | **Yes** — server-side web search (so it's blocked on a Vertex/Bedrock route) |
| API keys | None | None, but needs the working WebSearch route |
| Weight | Scales down to one inline catalog call | Always a multi-agent fan-out (heavier) |
| Verification | Fetch-validate each cited hit | 3 skeptic votes per claim, 2/3 refutes to kill |
| Best for | The everyday default; anything on a blocked route; dev/domain questions | A deliberately exhaustive, adversarially-verified cited report |

**Rule of thumb:** reach for **internet-search** by default and for everything on a search-blocked
host. Escalate to **deep-research** when you explicitly want a heavyweight, adversarially-verified
report *and* you're on a route where WebSearch actually works (e.g. a personal-account session).
They're complementary: on a blocked host, internet-search is the *only* one that runs; where both
work, internet-search is the cheaper default and deep-research is the deep dive.

## Install (Claude Code)

Symlink into your skills directory:

```bash
ln -s "$PWD/agent-skills/internet-search" ~/.claude/skills/internet-search
```

Optional but recommended — pre-allow the **read-only** commands so the skill runs without prompts.
See the security note in [`SKILL.md`](SKILL.md); the short version is: allowlist the read-only
*verbs* (`gh search`, `gh {issue,pr,repo} view`, `jq`, `grep`, `head`, `tail`, `sort`, `WebFetch`)
and, for raw GitHub API reads, the bundled GET-only wrapper [`scripts/gh-get`](scripts/gh-get) as
`Bash(gh-get:*)`. Do **not** blanket-allow `curl` or bare `gh api` — they can mutate, and prefix
rules can't restrict them to GET. A ready-to-merge example (allow + deny + risk disclaimer + the
real-boundary options like a read-scoped token) is in
[`references/example-permissions.md`](references/example-permissions.md) — **merge it, don't replace
your settings, and adopt at your own risk.**

## Portability

The doctrine and endpoints are tool-agnostic (public HTTP APIs any runtime can call). Only WebFetch
and background-subagent fan-out are Claude-Code-specific, and both have generic equivalents (an HTTP
GET; any parallel-task primitive, or run the queries sequentially).
