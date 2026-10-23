# Run 2 plan (committed before the run)

Status: **run on 2026-10-22; the results are in [run-2-results.md](run-2-results.md).** This file was committed before any run 2 request was made, so the git history shows the plan came first, and the text below is unchanged from then apart from this status line. It extends the design in the [method](method.md); run 1's raw records are in [results/run1](../results/run1).

Navigation: [index](../README.md) · [run 1 results](run-1-results.md) · [method](method.md)

## What run 2 does

Runs 12 arms for 2 more trials of the notebook's 10 claims, streams every request, and records timing. Run 1's trials stay as they were, so each arm that ran in both ends with 4 trials for pass counts and cost. Timing comes from run 2 only, because run 1 did not stream. Arms are named by model and setting; the same names cover run 1 and run 2, so one table lines them up.

| Arm | In run 1 |
|---|---|
| Opus 5.5, high effort, no cache | yes |
| Opus 5.5, high effort, auto cache | yes |
| Opus 5.5, medium effort, auto cache | yes |
| Opus 5.5, low effort, auto cache | yes |
| Sonnet 5.5, high effort, no cache | new |
| Sonnet 5.5, high effort, auto cache | yes |
| Sonnet 5.5, medium effort, auto cache | yes |
| Sonnet 5.5, low effort, auto cache | yes |
| Fable 5.1, high effort, no cache | yes |
| Fable 5.1, high effort, auto cache | yes |
| Fable 5.1, medium effort, auto cache | new |
| Fable 5.1, low effort, auto cache | new |

The arm with an explicit system breakpoint is not in run 2. Ids: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-fable-5-1`. No Haiku arm.

## Order and concurrency

Serial, one request at a time, no concurrency. Trial by trial, with the arm order rotated by half the list in trial 2 (`--order rotate`), so an arm is not always run at the same point in the sequence. The two orders are fixed here:

- Trial 1: Opus high effort no cache; Opus high auto cache; Opus medium auto cache; Opus low auto cache; Sonnet high auto cache; Sonnet medium auto cache; Sonnet low auto cache; Fable high no cache; Fable high auto cache; Sonnet high no cache; Fable medium auto cache; Fable low auto cache.
- Trial 2: Sonnet low auto cache; Fable high no cache; Fable high auto cache; Sonnet high no cache; Fable medium auto cache; Fable low auto cache; Opus high no cache; Opus high auto cache; Opus medium auto cache; Opus low auto cache; Sonnet high auto cache; Sonnet medium auto cache.

Two trials allow one rotation; it moves each arm by six places and spreads time-of-day effects, it does not remove them. Each arm and trial starts with a fresh nonce, shared by its 10 claims. With auto cache, every claim's first turn writes the whole prefix (system prompt and tools, about 13,000 tokens in run 1) and reads nothing, so the cache is cold at the first turn of every claim and warm from the second turn of that claim. Only an explicit system breakpoint carries the prefix across claims; that arm is not in run 2. [How caching is switched](how-caching-is-switched.md) shows the code and the recorded usage.

## Timing (`--stream`)

All times are on the monotonic clock from just before the request is opened:

- `wall_s`: to the end of the stream
- `ttfb_s`: to the first server event (network, queue and prefill)
- `first_delta_s`: to the first content delta of any kind, including thinking
- `first_text_s`: to the first text delta; empty when the reply has no text, which is common on a tool-use turn
- `attempts`: how many tries the request took

Per claim: `claim_wall_s` (first request to the verdict, including local tool time) and `trial_wall_s`. The results table gets one row per arm: pass counts per trial with run 1 and run 2 in separate columns, cost per task, wall seconds per claim, and the median of each first-token measure per arm, for first turns and for later turns separately.

Caveats the results will carry: timing depends on network and API load; cached and uncached time to first token are comparable only when the cache is warm, and the first turn of every claim is cold in every cached arm, so time to first token is reported for first turns and for later turns separately; two trials are too few to call a timing difference between close arms; the streaming path is new and its first live use is a one-claim smoke test.

## Spend

Cap of $100 for the whole run (`--ceiling-usd 100`), enforced before each request by the script's worst-case guard. Run 1's cost is not counted. Estimate from run 1's measured cost per task, times 10 claims: about $20.69 per trial and $41.38 for both; $53.79 if tokens run 30 percent above run 1. Fable is two thirds of it. The cost of the three new arms is estimated, not measured: Sonnet at high effort with no cache from the Opus cold-to-cached ratio of 2.02, and the two new Fable arms from Fable at high effort with auto cache, scaled by the Opus effort ratios.

## Steps and stop rules

1. Smoke test: one claim (CLM-001) of Sonnet 5.5 at low effort with auto cache, streamed. It must return a verdict, the four timing fields and a `usage` block that prices the same way as the non-streaming path.
2. The 12 arms, 2 trials, rotated order.
3. If a restart cuts a trial, the unfinished arms are relaunched with the same settings and the results say so, as in run 1.
4. A claim that cannot finish after retries stops the run and is reported; it is not skipped.

## Pass criterion

Unchanged from the notebook: an arm passes a trial with 10 of 10 claims. The results report each arm's pass count over 4 trials and say plainly that a miss on one claim in one trial is within what two to four trials can show as noise.
