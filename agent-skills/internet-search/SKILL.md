---
name: internet-search
description: >-
  Search the internet efficiently and route-independently. Use this WHENEVER the user asks to
  search the web/internet, "look something up online", find/research current information, discover
  sources, or answer a question that needs live external data — even if they don't say the word
  "search". ESPECIALLY use it when the native WebSearch tool is unavailable, denied, or returns a
  provider/policy error (e.g. Claude routed through Vertex AI / Bedrock where server-side web search
  is blocked): this skill works over plain client-side HTTP and needs no WebSearch tool and no API
  keys. It prefers precise domain catalogs (GitHub, Stack Overflow, package registries, arXiv,
  Hugging Face…) over generic web search, validates every hit with a live fetch, and can fan out
  parallel searches across catalogs for broad questions.
---

# Internet search (route-independent, domain-first)

Generic web search is the *ergonomic* default (one box, no thought), not the *efficient* one. This
skill encodes a better default: search the **specific catalog** that indexes your kind of question,
treat every result as an unverified rumor until a live fetch confirms it, and parallelize across
catalogs when the question is broad. It relies only on ordinary HTTPS (WebFetch + `curl` + authed
CLIs like `gh`), so it works on **any** Claude route — including hosts where the built-in WebSearch
tool is blocked by org policy.

## Two principles that drive everything

1. **Domain-first.** A question about code, packages, papers, or models has a *purpose-built index*
   whose ranking signals (stars, votes, downloads, citations) understand the question in a way
   generic web rank never will — and those indexes return structured JSON, so you spend a fraction
   of the tokens. Reach for generic web search only for the long tail no catalog covers.
2. **The index is a rumor; the fetch is the fact.** Every search result — from any engine, including
   the native WebSearch tool — is a *candidate*. Search indexes serve cached/stale entries, so links
   404, redirect, or misrepresent their content. Never quote or cite a result you haven't fetched
   live this turn. A fetch that fails (404, timeout, bot-block) means drop the candidate or label it
   unreliable — it must never become a cited claim.

## Step 1 — Route the question to a catalog

**First decide breadth. A NARROW question (one topic, one likely catalog) is answered INLINE — do
NOT spawn subagents.** Query the one right catalog, fetch-validate the top hit, answer. Spawning a
parallel fleet for "is there a known fix for X" wastes minutes and tokens on what one `gh search`
resolves in seconds. Fan-out (Step 4) is only for genuinely broad or cross-domain questions.

Pick the most specific catalog first. Most need no key; endpoint templates are in
[references/endpoints.md](references/endpoints.md). Prefer **WebFetch** for plain HTTP GETs where
your tool has it — it's read-only by construction (no keys, no POST, nothing to approve); fall back
to `curl` only where a custom header is required (see the etiquette notes in the reference).

| Question is about… | Use | Key? |
|---|---|---|
| Code, repos, issues, PRs, maintainer answers | `gh search code/repos/issues`, `gh api` | gh auth (already set up) |
| Programming Q&A, error messages, "how do I" | Stack Exchange API (Stack Overflow) | none |
| "Has anyone hit this", prior art, tech discussion | Hacker News (Algolia) API | none |
| AI/ML models & datasets | Hugging Face API | none |
| Academic / ML papers | arXiv API (**https**, not http) | none |
| A JS/Python/Rust/Helm/Docker package | npm / PyPI / crates.io / Artifact Hub / Docker Hub | none |
| Definitions, general facts, entities | Wikipedia API | none |
| Your own cloud resources | provider CLI (e.g. `gcloud asset search-all-resources`) | existing auth |
| **None of the above / open web** | DuckDuckGo HTML endpoint via WebFetch (Step 2) | none |

If the native **WebSearch** tool is available in this session, you may treat it as one more
catalog — but its results are still rumors: fetch-validate before citing.

## Step 2 — Open-web fallback (no catalog fits)

Use the DuckDuckGo HTML endpoint through **WebFetch** — keyless, route-independent:

```
WebFetch("https://html.duckduckgo.com/html/?q=<url-encoded query>",
         "List the top results as title + URL")
```

Then **fetch the promising result(s)** to get the actual answer. The search page gives you
candidate URLs; the fetch gives you truth. If you must use `curl` for the DDG endpoint instead of
WebFetch, send a browser-like `User-Agent` header or it returns a bot-challenge (202) instead of
results.

## Step 3 — Validate, then answer

- Fetch each candidate URL you intend to rely on. Discard anything that doesn't resolve.
- Answer with the fetched content, and cite the **fetched** source URL — not the search-result URL,
  unless they're identical and confirmed live.
- If nothing validates, say so plainly. A confident answer from an unfetched snippet is the exact
  failure mode this skill exists to prevent.

## Step 4 — Parallel fan-out (broad or cross-domain questions only)

When one catalog won't cover the question — e.g. "what's the current best approach to X" spanning
code + discussion + papers — run a **multi-modal sweep**: dispatch background subagents, one per
catalog family, each *blind* to the others so their angles stay independent. Then merge, dedup, and
fetch-validate the union before synthesizing.

Recommended families (skip any that don't apply):
- **code** — `gh search`, relevant repos/issues
- **Q&A + discussion** — Stack Exchange + Hacker News
- **packages + registries** — npm/PyPI/crates/Artifact Hub/Docker Hub
- **papers + models** — arXiv + Hugging Face
- **open web** — DuckDuckGo fallback

Effort/model floor: run workers on **Sonnet at low effort — never a smaller/cheaper model.** A
fresh-context worker still has to make real judgment calls (is this source credible? does the quote
support the claim?), and a cut-rate model produces unreliable search judgment that poisons the
synthesis — the fan-out's whole value is independent *quality* angles, not just parallelism. Low
*effort* on Sonnet is the cost lever; a smaller model is a false economy. Reserve higher effort for
the merge/synthesis step that has to reconcile everything. Give each worker the same instruction to
return structured hits
(title, URL, one-line why-relevant) and to fetch-validate its own top picks. **Do not fan out for a
single-catalog question** — a lone `gh search` or one DDG lookup is faster inline than spawning
agents.

Synthesis: dedup semantically (same fact from two catalogs = one finding, both sources), rank by
source quality + agreement, and attach the validated source URL to each claim. Surface what
couldn't be validated as caveats rather than dropping it silently.

## Why this holds on a blocked route

Everything above is plain client-side HTTP your machine already makes. The native WebSearch tool
runs *server-side* on the model provider, so a provider/org policy can disable it — but it cannot
disable your machine's own HTTPS to github.com or stackoverflow.com. That's why this skill is the
reliable path when WebSearch throws a policy error, and a better default even when it doesn't.

## Portability

The doctrine and the endpoint templates ([references/endpoints.md](references/endpoints.md)) are
tool-agnostic — the catalogs are public HTTP APIs any agent runtime can call with `curl`/`fetch`.
Only two things are Claude-Code-specific and have generic equivalents: **WebFetch** (any tool: an
HTTP GET + read) and **background subagents** for fan-out (any tool: its own parallel-task
primitive, or run the catalog queries sequentially). The core idea — route to a specific catalog,
treat results as rumors, validate by fetching — is universal.

## Permissions note (Claude Code host only — not part of the portable skill)

This skill runs shell commands; a Claude Code host prompts for approval unless they're allowlisted.
Safe, **read-only** commands worth pre-allowing in `~/.claude/settings.json` `permissions.allow`:
`Bash(gh search:*)`, `Bash(gh issue view:*)`, `Bash(gh pr view:*)`, `Bash(gh repo view:*)`,
`Bash(jq:*)`, `Bash(grep:*)`, `Bash(cat:*)`, `Bash(head:*)`, `Bash(tail:*)`, `Bash(sort:*)`, and
`WebFetch`. **Deliberately NOT blanket-allowed:** `curl` (can POST/exfil — prefix rules can't
restrict it to GET, so prefer WebFetch and let the rare custom-header `curl` prompt) and
`gh api` (can mutate with `-X`; the `search`/`view` verbs above cover read needs). This is a host
convenience, not a security boundary the skill provides.
