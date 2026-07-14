# Use cases

Concrete scenarios showing how the skill routes each kind of question. The pattern is always the
same: **pick the most specific catalog, fetch to confirm, answer with the fetched source** — and
only fan out when one catalog genuinely can't cover the question.

## 1. "Is there a known fix for <bug/error>?" — single catalog, inline

Route to GitHub issues (and Stack Overflow if it's an error message). One `gh search issues` +
reading the top hit answers it. No subagents.

```bash
gh search issues "virtiofs git status all files modified" --limit 8 --json title,repository,state,url
gh-get "search/issues?q=virtiofs+core.checkStat" --jq '.items[].html_url'
```
Then fetch the most relevant issue and cite it. If the fix is a config line, confirm it appears in
the actual issue thread — don't infer it from the title.

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

```bash
curl -s "https://registry.npmjs.org/-/v1/search?text=<task>&size=10"      # npm
curl -s -A ua "https://crates.io/api/v1/crates?q=<task>&per_page=10"       # crates.io (needs UA)
curl -s "https://pypi.org/pypi/<name>/json"                               # PyPI (exact name)
```
Confirm the top candidate is maintained (recent release date) before recommending it.

## 4. "What model should I use for <ML task>?" — Hugging Face + arXiv

```bash
curl -s "https://huggingface.co/api/models?search=<task>&limit=10&sort=downloads"
curl -s "https://export.arxiv.org/api/query?search_query=all:<task>&max_results=5&sortBy=relevance"
```
Downloads/likes rank models; arXiv gives the method behind them. Fetch a model card before citing
its capabilities.

## 5. "Has anyone discussed <approach/tradeoff>?" — Hacker News

```bash
curl -s "https://hn.algolia.com/api/v1/search?query=<approach>&hitsPerPage=5"
```
Good for prior art and honest practitioner pushback that vendor pages omit.

## 6. "What's the current best approach to <broad topic>?" — parallel fan-out

The one case that justifies subagents: the question spans code + papers + discussion. Dispatch one
**Sonnet-low** worker per catalog family (blind to each other), then merge, dedup, fetch-validate,
and synthesize with per-claim sources. See `SKILL.md` Step 4. Do **not** use this shape for the
narrow questions above — a single catalog call is faster and cheaper.

## 7. "Confirm <claim> against an official/primary source" — verify, don't trust memory

Find the authoritative page (vendor docs, standards body, official repo) via the right catalog or
DDG, **fetch it**, and quote the primary source. If it can't be fetched and confirmed, say so rather
than answering from training data. This is the fetch-validation rule applied to fact-checking.

## Anti-patterns

- Quoting a search snippet without fetching the page it came from.
- Spawning a subagent fleet for a one-catalog question.
- Falling back to open-web search when a specific catalog (gh/registry/HF/arXiv) indexes the answer.
- Treating a stale/404 link as a valid citation because the search index still lists it.
