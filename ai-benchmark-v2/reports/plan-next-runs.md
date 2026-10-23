# Plan: a repeated agent-loop run with the breakpoint arm, and a cache timing test

Status: **planned, not run. Committed before any paid call.** Nothing here runs until the person running it says go, with a ceiling for each run. This plan answers two questions: does the explicit-breakpoint arm change the picture, and is there a true time saving from the prompt cache.

Navigation: [index](../README.md) · [run 1 results](run-1-results.md) · [how caching is switched](how-caching-is-switched.md) · [method](method.md) · [cache timing script](../cache_timing.py)

## What "warm cache" means, and why the question must change

A cache hit needs the start of the request to be identical to an earlier request that wrote the cache. In real use the start is the same (the policy manual, the ledger) and the question at the end is different each time. That is what a **warm** request is here: the same long prefix, a different question, within the cache lifetime of 5 minutes.

Automatic caching alone does not give that hit. It puts the cache breakpoint at the end of the request, so a new question is a new cache key. [Run 1's records show it](how-caching-is-switched.md): in the nine cached arms, the first turn of every claim wrote the whole prefix again and read nothing (180 of 180 requests). The warm state therefore needs an **explicit breakpoint at the end of the shared prefix**. Then a cold request (prefix plus question A) writes that prefix, and a warm request (the same prefix plus question B) reads it.

## Test A: the agent loop again, with the breakpoint arm

- **What:** the 12 arms of run 1 plus "Sonnet medium cache + breakpoint" (13 arms), 2 trials of the 10 claims, streamed, serial, arm order rotated by half the list in trial 2. Models and settings are the latest: Opus 5.5, Sonnet 5.5, Fable 5.1; high, medium, low = effort level.
- **Orders**, fixed here. Trial 1: Opus high no cache; Opus high cache; Opus medium cache; Opus low cache; Sonnet high cache; Sonnet medium cache; Sonnet low cache; Fable high no cache; Fable high cache; Sonnet high no cache; Fable medium cache; Fable low cache; Sonnet medium cache + breakpoint. Trial 2: Sonnet low cache; Fable high no cache; Fable high cache; Sonnet high no cache; Fable medium cache; Fable low cache; Sonnet medium cache + breakpoint; Opus high no cache; Opus high cache; Opus medium cache; Opus low cache; Sonnet high cache; Sonnet medium cache.
- **Pass criterion, report, charts:** as in the [run 1 plan](run-1-plan.md) and [method](method.md). The table and the four charts come from one command.
- **Replaces run 1:** when it finishes, its records and report take the place of run 1 in this tree. The current run 1 files stay on disk with the person who ran them and leave the repository.
- **Why the breakpoint arm matters:** in run 1 the cache write was 66 to 77 percent of the cost of every cached arm, because each claim's first turn wrote the prefix again. The breakpoint arm carries the prefix across the claims of a trial, so most of those writes should become reads.
- **Cost:** run 1 cost $40.65 for its 12 arms by the notebook formula; the breakpoint arm is estimated at $0.40 (20 claims at about $0.02 each). **About $41, or $53 if tokens run 30 percent above run 1.** About 70 minutes.
- **Smaller alternative:** only the breakpoint arms (Sonnet medium, and Opus high and Fable high, which need two arm entries added), about $4. It would not replace run 1.

## Test B: the cache timing test

**Question:** is there a true time saving from the cache, and does it depend on the size of the prefix?

**Design.** Single requests, not the agent loop, so that time to first token measures reading the prompt and not the model thinking or calling tools. For each model and each prefix size there are 10 repetitions, each a set of three requests, one at a time:

| State | The request |
|---|---|
| no cache | the prefix with no `cache_control` anywhere |
| cold cache | the same prefix with an explicit breakpoint at the end of it: the first request, which writes |
| warm cache | the same prefix and breakpoint again, a **different question**, straight after the cold request: it reads |

- **Models:** Opus 5.5, Sonnet 5.5, Fable 5.1.
- **Two prefix sizes:** "13k", the benchmark's system prompt and tools, about 13,000 tokens; and "long", the same plus the cookbook's claims ledger (a 228,000-character CSV, copied into `assets/` under the same MIT notice), which I estimate at 90,000 to 127,000 tokens and will measure with the token counting endpoint before the run. A cache read can only save the reading of what it skips, so I expect the larger prefix to be where a saving shows; the results will say whether it did.
- **The question** is one of the 10 claims: "In about 100 words, say what you would decide and why. Do not call a tool." Output is capped at 256 tokens, effort low, thinking off and tool choice none if the model accepts them (the smoke test finds out which settings each model accepts, and the accepted settings are recorded); if a model does not accept thinking off, the thinking tokens are recorded and reported.
- **Different questions:** the three requests of a set use three different claims. Which claim goes to which state rotates with the repetition, the model and the prefix, so no state always gets the same question. The schedule is fixed in the script and printed by `--dry-run` (60 sets, 180 requests).
- **Order:** serial, no concurrency. The order inside a set alternates: cold, warm, no cache on even repetitions; no cache, cold, warm on odd ones (cold always before warm). The order of the three models rotates every repetition and prefix size.
- **Fresh cache per set:** a new nonce at the head of the system prompt for every set, so the cold request really writes and the warm request reads that set's entry, and nothing from another set can be hit.
- **Check on every request.** The usage block must match the state: cold shows a write of at least 80 percent of the request's input and almost no read; warm shows a read of at least 80 percent and little write; no cache shows neither. A request that fails is **reported by name and left out of the medians**, never averaged in.
- **What is measured**, per request, on the monotonic clock **started after the connection is open**, just before the request is sent (the connection is made first and its time, DNS, TCP and TLS, is recorded as `connect_s` and kept out of every time below, because it varies from request to request and could hide a saving of the same size; the upload of the prompt is inside the clock and is the same in all three states): time to the first server event; time to the first token (the first text delta, or the first content delta when there is no text); total time; output tokens, and **output tokens per second** as (output tokens minus one) over (total time minus time to first token); cost by the notebook formula.
- **Network context**, for reading the results and never to correct them: before each set the script logs the default route's interface (it changes if the network is switched between Wi-Fi and mobile) and three TCP connect times to the API host. No privilege needed.
- **Reported:** median and quartiles per cell; per-repetition paired differences (warm against cold, warm against no cache, cold against no cache) with the median difference and the number of repetitions in which the second was faster. **Reading rule, fixed now:** the headline is **warm against no cache**, since the question is whether there is a true saving: it counts as seen for a cell when warm was faster in at least 8 of the 10 paired repetitions (by chance alone about 5.5 percent). A stricter secondary reading also needs warm faster than cold in at least 8 (by chance alone about 0.3 percent). Both are stated for every cell, and the number of requests left out by the state check is shown next to each median. This is a reading aid, not a significance test. The table and three charts (first token, total time, tokens per second, by state) come from `python3 cache_timing.py --report DIR`.
- **Steps:** (1) token counts of the two prefixes, which need no spend beyond the key; (2) a smoke test of one set, Sonnet, 13k, to confirm the request shape is accepted and the states show as expected, then one set with the long prefix; (3) the full run. Any restart relaunches the unfinished sets with the same settings and the results say so.
- **Cost:** the upper-bound arithmetic is in `python3 cache_timing.py --estimate`: no cache at 1 times the input price, a cold write at 1.25 times, a warm read at 0.10 times, plus up to 256 output tokens. For the long prefix at 89,000, 101,000 and 127,000 tokens it gives **$39.70, $44.11 and $54.01** for all 180 requests; Fable is about half of it. The smoke tests add under $2. About 20 to 30 minutes.
- **What this does not show:** the agent loop's own time (Test A does); server-side queueing and load, which vary; the effect of the network, which the context log records but does not remove; anything about prefixes smaller than 13,000 tokens or larger than the ledger.

## What the two tests cost together

| Option | Estimate | Range |
|---|---|---|
| Test A and Test B | about $85 | $81 to $107 |
| Test B alone | about $44 | $40 to $54 |
| Test A alone | about $41 | $41 to $53 |
| Test B plus the smaller Test A | about $49 | $45 to $59 |

These are list-price upper bounds from the notebook's multipliers, not measurements. The balance of the credit these runs draw on cannot be read from the script.

## Stop rules

The script stops before any request whose worst case would pass the ceiling given with `--ceiling-usd`. A request that cannot finish after its retries stops the run and is reported. Nothing is skipped silently.
