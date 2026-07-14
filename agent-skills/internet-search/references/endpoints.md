# Endpoint templates (verified working over plain client-side HTTPS, no keys unless noted)

Replace `<q>` with a URL-encoded query. All return JSON unless noted. Etiquette notes matter —
a few of these reject bare requests without a User-Agent, and one only serves over https.

**On a Claude Code host, call these plain GETs with `WebFetch(url, "extract …")`, not `curl`** —
WebFetch is read-only and allowlisted, so it runs without a prompt; raw `curl` is not allowlisted
(it can POST/exfil) and will prompt. The `curl` forms below are shown for **portability** (other
agent runtimes, shell use) and for the two endpoints that need a custom header. WebFetch sets its
own browser-like User-Agent, so it also covers the UA-required endpoints (crates.io, DuckDuckGo)
without extra flags. For GitHub, use `gh search` / `gh-get` (allowlisted), not `curl`.

## Code / dev (GitHub — uses existing `gh` auth)
```
gh search repos <q> --limit 10 --json fullName,description,stargazersCount,url
gh search issues <q> --limit 10 --json title,repository,state,url
gh search code <q> --limit 10           # code search: needs a logged-in gh
gh api "search/repositories?q=<q>&sort=stars"   # raw API when you need more fields
```

## Programming Q&A — Stack Exchange (Stack Overflow); ~300 req/day/IP, no key
```
https://api.stackexchange.com/2.3/search/advanced?order=desc&sort=relevance&q=<q>&site=stackoverflow&pagesize=5
https://api.stackexchange.com/2.3/search?intitle=<q>&site=stackoverflow&pagesize=5   # title-only, tighter
```
Response items carry `title`, `link`, `score`, `is_answered`. Check `quota_remaining`.

## Tech discussion / prior art — Hacker News (Algolia); no key, generous
```
https://hn.algolia.com/api/v1/search?query=<q>&hitsPerPage=5              # by relevance
https://hn.algolia.com/api/v1/search_by_date?query=<q>&hitsPerPage=5      # newest first
```
Item URL: `https://news.ycombinator.com/item?id=<objectID>`.

## AI/ML models & datasets — Hugging Face; no key
```
https://huggingface.co/api/models?search=<q>&limit=10&sort=downloads
https://huggingface.co/api/datasets?search=<q>&limit=10
```
Model id → page `https://huggingface.co/<id>`.

## Papers — arXiv; no key. MUST use https (http returns 301)
```
https://export.arxiv.org/api/query?search_query=all:<q>&max_results=5&sortBy=relevance
```
Returns Atom XML (not JSON). Entry `<id>` is the abstract URL.

## Package registries — no keys
```
# npm
https://registry.npmjs.org/-/v1/search?text=<q>&size=10
# PyPI (exact-name metadata; there is no great fuzzy search — prefer known names)
https://pypi.org/pypi/<package>/json
# crates.io  — REQUIRES a User-Agent header (403 without one)
https://crates.io/api/v1/crates?q=<q>&per_page=10
# Helm charts / K8s operators
https://artifacthub.io/api/v1/packages/search?ts_query_web=<q>&limit=10
# Docker images
https://hub.docker.com/v2/search/repositories/?query=<q>&page_size=10
```

## General facts / entities — Wikipedia; no key
```
https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=<q>&format=json&srlimit=5
```
Page: `https://en.wikipedia.org/wiki/<title with underscores>`.

## Open-web fallback — DuckDuckGo HTML, keyless
```
# Preferred: via WebFetch (handles the bot challenge, returns readable results)
WebFetch("https://html.duckduckgo.com/html/?q=<q>", "list top results as title + URL")
# If using curl directly, a browser-like User-Agent is REQUIRED (else HTTP 202 challenge):
curl -s -A "Mozilla/5.0" "https://html.duckduckgo.com/html/?q=<q>"
```

## Your own cloud (example — GCP; uses existing auth)
```
gcloud asset search-all-resources --query="<q>" --format=json
```

## curl etiquette cheatsheet (only when not using WebFetch)
- `crates.io` and `html.duckduckgo.com` → send `-A "<user-agent>"`. crates.io's policy asks the UA to
  **identify you with contact info** (e.g. `-A "yourtool (you@example.com)"`); a bare `Mozilla/5.0`
  can get rate-limited.
- `arXiv` → use `https://` (http 301-redirects).
- Add `--compressed -m 8` for gzip + an 8s timeout so a slow endpoint can't hang a sweep.
- **Stack Exchange** is ~300 req/day **per IP** AND throttles via a `backoff` field in the JSON /
  `Retry-After` — a burst fan-out can trip a short-term backoff before the daily cap. If a worker
  loops, honor `backoff`/`Retry-After`.
- **DuckDuckGo HTML is the least stable link** in the chain — it periodically changes its
  challenge/markup and may return a bot page. Treat open-web fallback as best-effort; prefer a
  specific catalog whenever one fits.
- These are public endpoints — keep volume reasonable; for heavy sweeps prefer the APIs with
  explicit quotas (Stack Exchange, HN) over scraping the DDG HTML page repeatedly.
