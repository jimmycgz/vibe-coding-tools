# Plan: a repeated agent-loop run with the breakpoint arm, and a cache timing test

Status: **planned; Test B has been run for Sonnet only (results in [cache-timing-results.md](cache-timing-results.md)); Opus, Fable and Test A have not been run.** The plan was committed before any paid call. The cache timing test (Test B) is the one to run first; the repeated agent-loop run (Test A) is kept in the plan for later. Nothing here runs until the person running it says go, with a ceiling for each run. This plan answers two questions: does the explicit-breakpoint arm change the picture, and is there a true time saving from the prompt cache.

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

**Question:** is there a true time saving from the cache for a long shared prefix, and what does a cache write cost?

**Scope, set 2026-10-22:** the long prefix only, for Opus, Sonnet and Fable. A 13,000-token prefix cell was in an earlier version of this plan and is dropped: at that size the reading a cache read skips is small next to the network and queue time, and the agent-loop timing already covers that size. The script can still run it (`--prefixes 13k|both`). Timing as a comparison between the models stays in the benchmark itself (the agent-loop script's `--measure timing`).

**Design.** Single requests, not the agent loop, so that time to first token measures reading the prompt and not the model thinking or calling tools. For each model there are 10 repetitions on the long prefix, each a set of three requests, one at a time:

| State | The request |
|---|---|
| no cache | the prefix with no `cache_control` anywhere |
| cold cache | the same prefix with an explicit breakpoint at the end of it: the first request, which writes |
| warm cache | the same prefix and breakpoint again, a **different question**, straight after the cold request: it reads |

- **Models:** Opus 5.5, Sonnet 5.5, Fable 5.1.
- **The long prefix:** the benchmark's system prompt and tools (about 13,000 tokens) plus the cookbook's claims ledger (a 228,000-character CSV, copied into `assets/` under the same MIT notice), which I estimate at 90,000 to 127,000 tokens in all and will measure with the token counting endpoint before the run. A cache read can only save the reading of what it skips, so the long prefix is where a saving should show; the results will say whether it did.
- **The question** is one of the 10 claims: "In about 100 words, say what you would decide and why. Do not call a tool." Output is capped at 256 tokens, effort low, thinking off and tool choice none if the model accepts them (the smoke test finds out which settings each model accepts, and the accepted settings are recorded); if a model does not accept thinking off, the thinking tokens are recorded and reported.
- **Different questions:** the three requests of a set use three different claims. Over the 10 repetitions each state sees every claim exactly once for a given model, so no state always gets the same question. The schedule is fixed in the script and printed by `--dry-run` (30 sets, 90 requests).
- **Order:** serial, no concurrency. The order inside a set alternates: cold, warm, no cache in repetitions 1, 3, 5, 7 and 9; no cache, cold, warm in repetitions 2, 4, 6, 8 and 10 (cold always before warm). The order of the three models rotates every repetition.
- **Fresh cache per set:** a new nonce at the head of the system prompt for every set, so the cold request really writes and the warm request reads that set's entry, and nothing from another set can be hit.
- **Check on every request.** The usage block must match the state: cold shows a write of at least 80 percent of the request's input and almost no read; warm shows a read of at least 80 percent and little write; no cache shows neither. A request that fails is **reported by name and left out of the medians**, never averaged in.
- **What is measured**, per request, on the monotonic clock **started after the connection is open**, just before the request is sent (the connection is made first and its time, DNS, TCP and TLS, is recorded as `connect_s` and kept out of every time below, because it varies from request to request and could hide a saving of the same size; the upload of the prompt is inside the clock and is the same in all three states): time to the first server event; time to the first token (the first text delta, or the first content delta when there is no text); total time; output tokens, and **output tokens per second** as (output tokens minus one) over (total time minus time to first token); cost by the notebook formula.
- **Network context**, for reading the results and never to correct them: before each set the script logs the default route's interface (it changes if the network is switched between Wi-Fi and mobile) and three TCP connect times to the API host. No privilege needed.
- **Negative control:** output tokens per second should not depend on the cache state, because a cache read skips reading the prompt and does not change how fast tokens are generated. The report flags that something other than the cache is varying (network, load, output length) when the largest difference between the three state medians is **both more than 10 percent and larger than the widest scatter inside a state** (its interquartile range), and it prints that spread beside the difference, so ordinary scatter is not read as a difference between states. The flag is stated next to the headline.
- **Reported:** median and quartiles per cell; per-repetition paired differences (warm against cold, warm against no cache, cold against no cache) with the median difference and the number of repetitions in which the second was faster. **Reading rule, fixed now:** the headline is **warm against no cache**, since the question is whether there is a true saving: it counts as seen for a cell when warm was faster in at least 8 of the 10 paired repetitions (by chance alone about 5.5 percent). A stricter secondary reading also needs warm faster than cold in at least 8 (by chance alone about 0.3 percent, if the two comparisons were independent). **Cold against no cache** is reported on its own as well, with the same rule in the other direction (cold slower in at least 8): a write may cost a little time, and that is the other half of the question. Both are stated for every cell, and the number of requests left out by the state check is shown next to each median. This is a reading aid, not a significance test. The table and three charts (first token, total time, tokens per second, by state) come from `python3 cache_timing.py --report DIR`.
- **How a warm hit is ensured.** The script does each of these, and the report proves it request by request:
  1. The prefix is byte-identical between cold and warm: one nonce per set; the same model, effort, thinking and tool-choice settings (changing any of them would break the cache); the same 12 tools in the same order; the same system blocks.
  2. The explicit breakpoint is on the last block of the prefix (the ledger block), and the question is in the user message after it; the no-cache request has no `cache_control` anywhere.
  3. Warm is sent after cold has fully finished (the stream is read to its end), straight away in the same set, and the wait between them is logged and reported against the 5-minute lifetime.
  4. The prefix is far above any minimum cacheable length I know of (tens of thousands of tokens); the proof is the usage block, because a cold request that did not write shows it at once.
  5. The proof is the usage block of every request: cold writes about the size of the prefix, warm reads about the size of the prefix and writes little, no cache does neither. A failure is named and left out. This is the rule the test follows; cache diagnostics and previous-message ids are not used, because each set has a single breakpoint and so a single cache.
- **What a separate check found, and what the docs say.** A small check made on 2026-10-22 (2 rounds, 10 requests, about $0.22; its records are kept by the person who ran it and are not in this repository) found on Sonnet 5.5, with one explicit breakpoint on the system block: a change of effort from high to low kept the cache hit (read 12,964 tokens, no rewrite), and switching to Opus 5.5 with the same prefix wrote a new cache (write 12,964, read 0). That fits what the documentation and the cookbook say. From Anthropic's prompt-caching and effort documentation (read on 2026-10-22 by the person who ran the check): changing the effort value always invalidates cached message blocks, and the effect on the tool and system caches depends on the model. From Anthropic's cookbook notebook (cell 23): caches are per model; the check confirmed it for Sonnet to Opus. Not tested: effort changes on Opus and Fable, and on a message-level breakpoint. Consequences for this test: each model writes its own cold cache, which the design already has; effort stays the same inside every set, as it does; and the fresh nonce per set keeps sets apart.
- **Measure flag.** `--measure cost|timing|both` (default both) chooses what is reported and charted; cost is always recorded from the usage block. The agent-loop script has the same flag.
- **First paid run: Sonnet only** (`--only sonnet`): 10 sets, 30 requests (10 cold, 10 warm, 10 no cache) plus the smoke set, about $5 to $7. Opus and Fable wait for that result and for the person running it to say go; the Sonnet result decides whether they are worth running.
- **Steps:** (1) the token count of the long prefix, which needs no spend beyond the key; (2) a smoke test of one set, Sonnet, long prefix, to confirm the request shape is accepted, the connection time and response look right and the states show as expected; (3) the full run. Any restart relaunches the unfinished sets with the same settings and the results say so.
- **Cost:** the upper-bound arithmetic is in `python3 cache_timing.py --estimate`: no cache at 1 times the input price, a cold write at 1.25 times, a warm read at 0.10 times, plus up to 256 output tokens. For the long prefix at 89,000, 101,000 and 127,000 tokens it gives **$34.16, $38.57 and $48.47** for all 90 requests; Fable is about half of it. The smoke test adds about $0.50 (one Sonnet set). About 15 to 25 minutes.
- **What this does not show:** the agent loop's own time (Test A does); server-side queueing and load, which vary; the effect of the network, which the context log records but does not remove; anything about prefixes smaller than the long one (the 13,000-token size is not tested here) or larger than the ledger.

## What the two tests cost together

| Option | Estimate | Range |
|---|---|---|
| Test B alone (long prefix, 90 requests) | about $38 | $34 to $48 |
| Test A and Test B | about $79 | $75 to $101 |
| Test A alone | about $41 | $41 to $53 |
| Test B plus the smaller Test A | about $43 | $38 to $52 |

These are list-price upper bounds from the notebook's multipliers, not measurements. The balance of the credit these runs draw on cannot be read from the script.

## Stop rules

The script stops before any request whose worst case would pass the ceiling given with `--ceiling-usd`. A request that cannot finish after its retries stops the run and is reported. Nothing is skipped silently.
