# Use cases

Concrete scenarios showing how the skill routes each kind of question. The pattern is always the
same: **route by topic (deterministic map in SKILL.md), dispatch background subagents — never search
in the main session — fetch to confirm, answer with the fetched source.** Even a one-catalog
question runs as a background worker so the conversation is never blocked.

## 1. "Is there a known fix for <bug/error>?" — dev question → background fan-out

A dev question always fans out **code + Q&A + discussion** (GitHub + Stack Overflow + Hacker News),
dispatched as **parallel background subagents on Sonnet**, so the main session keeps moving. Each
worker runs its catalog and fetch-validates its own top hits; you synthesize when they report back.

Each worker's core query (illustrative):
```bash
# code worker — gh is allowlisted
gh search issues "virtiofs git status all files modified" --limit 8 --json title,repository,state,url
gh-get "search/issues?q=virtiofs+core.checkStat" --jq '.items[].html_url'
# Q&A worker — WebFetch (allowlisted, no prompt), not curl
WebFetch("https://api.stackexchange.com/2.3/search/advanced?q=virtiofs+git+modified&site=stackoverflow&pagesize=5",
         "list the question titles, scores, and links")
# discussion worker — WebFetch
WebFetch("https://hn.algolia.com/api/v1/search?query=virtiofs%20git&hitsPerPage=5",
         "list the story titles and their HN item URLs")
```
Each worker fetches the most relevant hit and confirms the fix appears in the actual thread — never
inferred from a title. The main session merges the three, dedups, and cites the fetched sources.

## 2. "What's the current pricing / limits of <product>?" — open-web fallback, fetch-validated

No catalog indexes a vendor's pricing page, so fall back to DuckDuckGo, then **fetch the pricing
page itself** — never quote a search snippet. Flag anything the page renders via JS that the fetch
can't read.

```
WebFetch("https://html.duckduckgo.com/html/?q=<product> api pricing", "top results as title+URL")
WebFetch("<the vendor pricing URL>", "list the plans and their prices and limits")
```

## 3. "Which <language> package should I use for <task>?" — registry catalog

Go straight to the registry; its download/version signals rank better than web search.

```
WebFetch("https://registry.npmjs.org/-/v1/search?text=<task>&size=10", "top packages + weekly downloads")
WebFetch("https://crates.io/api/v1/crates?q=<task>&per_page=10", "top crates + downloads")  # WebFetch sets its own UA
WebFetch("https://pypi.org/pypi/<name>/json", "latest version + last release date")          # PyPI: exact name
```
Confirm the top candidate is maintained (recent release date) before recommending it.

## 4. "What model should I use for <ML task>?" — Hugging Face + arXiv

```
WebFetch("https://huggingface.co/api/models?search=<task>&limit=10&sort=downloads", "top models + downloads")
WebFetch("https://export.arxiv.org/api/query?search_query=all:<task>&max_results=5&sortBy=relevance", "paper titles + abstract URLs")
```
Downloads/likes rank models; arXiv gives the method behind them. Fetch a model card before citing
its capabilities.

## 5. "Has anyone discussed <approach/tradeoff>?" — Hacker News

```
WebFetch("https://hn.algolia.com/api/v1/search?query=<approach>&hitsPerPage=5", "story titles + item URLs + points")
```
Good for prior art and honest practitioner pushback that vendor pages omit.

## 6. "What's the current best approach to <broad topic>?" — widest fan-out

The broadest case: dispatch background **Sonnet** workers across every matched family (code + papers
+ discussion + models), blind to each other, then merge, dedup, fetch-validate, and synthesize with
per-claim sources. Same background/async execution as every other case — just more workers.

## 7. "Confirm <claim> against an official/primary source" — verify, don't trust memory

Find the authoritative page (vendor docs, standards body, official repo) via the right catalog or
DDG, **fetch it**, and quote the primary source. If it can't be fetched and confirmed, say so rather
than answering from training data. This is the fetch-validation rule applied to fact-checking.

## Anti-patterns

- **Running the search in the main session** instead of dispatching a background subagent — blocks
  the conversation; never do it, even for one catalog.
- Quoting a search snippet without fetching the page it came from.
- Answering a dev question from a single catalog — always fan out code + Q&A + discussion.
- Falling back to open-web search when a specific catalog (gh/registry/HF/arXiv) indexes the answer.
- Treating a stale/404 link as a valid citation because the search index still lists it.
- Downgrading workers to a cheaper model than Sonnet to "save cost" — it poisons the synthesis.
