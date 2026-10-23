# Gemini 3.8 Flash results

**Gemini 3.8 Flash at medium thinking passed every claim at about half the cost per task of Sonnet 5.5 at medium effort ($0.0261 against $0.0488) and took 2.5 times as long per claim (20.0 s against 8.0 s); at low thinking it failed the pass bar; on a 171K-token prefix a follow-up turn cost 8.0 times less than a first request and was faster in all 7 valid pairs, but the pre-registered reading is "not seen".**

Run on 2026-10-22 and 2026-10-23, Gemini 3.8 Flash (`gemini-3.8-flash`) on Vertex AI, location global, list prices read from the Vertex pricing page on 2026-10-22. The plan, committed before the cache timing sets, is in [gemini-plan.md](gemini-plan.md), with its amendment. The scripts are [gemini_benchmark.py](../gemini_benchmark.py) and [gemini_cache_timing.py](../gemini_cache_timing.py). The task and its data are the cookbook's, credited in the [README](../README.md).

Navigation: [index](../README.md) · [plan and amendment](gemini-plan.md) · [Claude run 1 results](run-1-results.md) · [Claude cache timing results](cache-timing-results.md) · [method](method.md)

## The agent task

**Gemini 3.8 Flash at high and medium thinking passed 10 of 10 in both trials, at $0.0313 and $0.0261 per task; at low thinking it passed 7 and 8 of 10, missing CLM-006 and CLM-010 both times.**

The same 10 claims, 12 tools and 6-turn limit as the Claude runs, 2 trials per arm, streamed, serial. The arm order was high, medium, low in both trials (this script has no rotate option), so time of day is confounded with the arm. 241 requests, all HTTP 200, none retried, $1.57. Cost is priced from each request's usage block at list prices, thinking tokens as output. The full table and charts are in [gemini-loop/](gemini-loop/results-table.md).

| Arm | Trials | $ per task | Wall s per claim | Wall s per request |
|---|---|---|---|---|
| Gemini 3.8 Flash high | 10/10, 10/10 | 0.0313 | 27.97 | 4.20 |
| Gemini 3.8 Flash medium | 10/10, 10/10 | 0.0261 | 20.04 | 3.44 |
| Gemini 3.8 Flash low | 7/10, 8/10 | 0.0209 | 11.48 | 1.85 |
| Sonnet high cache (run 1) | 10/10, 10/10 | 0.0487 | 8.00 | 2.27 |
| Sonnet medium cache (run 1) | 10/10, 10/10 | 0.0488 | 8.00 | 2.20 |
| Sonnet low cache (run 1) | 10/10, 10/10 | 0.0465 | 8.37 | 2.34 |

The Sonnet rows are copied from [run 1](run-1-results.md); they come from a different run, harness path and time of night, so they are context and not a controlled comparison. Gemini counts tokens differently (the system prompt and tools are about 8,000 Gemini tokens against about 13,000 Claude tokens), and its cost per task includes thinking tokens, 128,161 in all over the run.

- **Implicit cache in the loop:** 39.3 percent of all prompt tokens were read from the cache, in part. In the single-claim smoke test the cached part was about 3,870 of about 8,650 tokens on turns 2 to 4. The cache cannot be switched off, so there is no no-cache arm.
- **Low thinking:** the lowest level the model accepts. Its misses are a quality result, not a script fault: all 241 requests succeeded and the verdicts were scored against the same expected answers as the other arms.

## The cache timing test

**On a 171K-token prefix, a follow-up turn read 97.5 to 97.9 percent of its prompt from the cache in 8 of 10 sets and cost $0.0161 against $0.1292 for a first request (8.0 times less); its first token came at a median of 2.37 s against 4.73 s and the repeat was faster in all 7 valid pairs, yet the registered reading is "not seen" because the rule needs 8 valid pairs and 7 were valid.**

The test is in [gemini-plan.md](gemini-plan.md), as amended before the sets: ten sets of three requests on the long prefix (the system prompt, the tools and the claims ledger, 171,360 Gemini tokens), thinking at LOW, output capped. The three kinds of request are the **first request** (a fresh nonce), the **repeat request** (a follow-up turn: the first request, its reply and a new question) and the **second first request**, a control of the same kind as the first. They do not map onto the Claude cold, warm and no-cache states and are not drawn on one chart with them. 30 requests, all HTTP 200, $2.86. The table and three charts are in [gemini-cache-timing-table.md](gemini-cache-timing-table.md) ([first token](gemini-cache-timing-first-token.svg), [total time](gemini-cache-timing-wall.svg), [output speed](gemini-cache-timing-tps.svg)).

| State | Valid of 10 | First token s (median) | Total s (median) | $ per request |
|---|---|---|---|---|
| first request | 9 | 4.73 | 5.98 | 0.1292 |
| repeat request (follow-up turn) | 8 | 2.37 | 3.29 | 0.0161 |
| second first request | 10 | 4.82 | 5.77 | 0.1294 |

- **Hit rate: 8 of 10.** Sets 2, 3, 5, 6, 7, 8, 9 and 10 read 97.5 to 97.9 percent of their prompt from the cache. Sets 1 and 4 read 0 percent. The registered minimum was 8 of 10, so the reading was not cut to "inconclusive". Why two follow-ups missed is unexplained.
- **Valid pairs: 7.** A pair needs a valid first request and a valid repeat. Sets 1 and 4 lost their pair to the miss. In set 3 the first request, sent with a fresh nonce, came back with 167,113 cached tokens (97.5 percent); that is not a fresh prefix, so it failed its state check and the pair is excluded. This is unexplained too.
- **The reading, by the registered rule, unchanged:** the repeat was faster in 7 of 7 valid pairs, with a median first-token difference of 2.13 s (total time 2.22 s), but the rule needs at least 8 valid pairs, so the headline is **not seen**. The 7 of 7 and the median difference are what the valid pairs showed, and are not a reading.
- **Noise floor:** the first request against the second first request, two requests of the same kind: the first was faster in 5 of 9 valid pairs, median difference 0.16 s.
- **Output speed** (146.1, 153.8 and 160.3 tokens per second) differed by at most 8.8 percent, inside the within-state spread of 36.5: no flag.
- **Time to first token includes the model's thinking** at the lowest level, which the cache does not shorten. Thinking tokens varied from 0 to 635 a request.
- **An observation, not a finding:** every cache hit read exactly 167,885 tokens, whatever the set's nonce or prompt length, and the unexpected hit in set 3 read 167,113. That suggests the implicit cache may not be keyed strictly on the leading nonce. It is a hypothesis; nothing here depends on it.

## What the diagnostic found about the cache

**A new question sent as a separate request never hit Gemini's implicit cache (0 percent in all 6 repeats tried, from 7.6K to 171K tokens, with waits up to 120 s), while an identical request or a follow-up turn did (52 to 98 percent), and the cached part grew with the prompt.**

After the smoke set's repeat read 0 percent, a set of small probes (each a first request and one or two repeats on a fresh prefix, $0.01 to $0.39, about $1.2 in all) asked what makes a repeat hit. The records are in [results/gemini-diagnostic](../results/gemini-diagnostic), and the table is in the plan's amendment. In short:

| Repeat kind | Prefix | Cached share |
|---|---|---|
| new question | 171K (waits 0, 30, 120 s) | 0, 0, 0 percent |
| new question | 48K (ledger as a system part, or in the user message) | 0, 0 percent |
| new question | 7.6K | 0 percent |
| identical request | 7.6K, 48K | 53.6, 93.1 percent |
| follow-up turn | 7.8K, 48K, 171K | 52.1, 92.6, 97.9 percent |

These are single pairs. The explanation (the cache stores whole earlier requests and serves the longest one a new request extends) is a hypothesis, and it does not explain set 3's fresh-nonce first request, which hit. The consequence is a design one: the warm case that can be made to hit is a follow-up turn, which measures a turn that carries the earlier turn, not a new user reading a shared document.

## How the assumptions in the code came out

**All eight assumptions made in the code held in the single-claim smoke test and the cache timing smoke set.** They were: the tool result format and the call id echo (accepted over 4 turns; whether the API sent an id on every call was not checked), capital letters in the tool schema types (accepted), no quota-project header (not needed), usage arriving in the last streamed chunk (it did on every request), `promptTokenCount` including implicitly cached tokens (on every cache hit `promptTokenCount` stayed at the full prompt size (171,5xx) while `cachedContentTokenCount` was 167,885, so the cached tokens are inside the prompt count; if they were not, the prompt count would have dropped to about 3,700), thinking at LOW with tools in mode NONE (accepted), and the spend guard's thinking allowance of 24,576 tokens (the largest thinking count seen was 1,128).

## Limits

**This is one model, one long prefix, ten sets and a two-trial task, so the cost results are firm and the time results are small-sample.**

- The arm order of the agent task is the same in both trials.
- The cache timing reading rests on 7 valid pairs and a registered rule that was not changed after the data.
- Gemini 4 Argon, explicit caching, and a Gemini against Claude comparison under one protocol were not run.
- The Vertex project id, the service account and the access token appear in no record or report; each run was checked for them (counts of 0) before its records were kept.
