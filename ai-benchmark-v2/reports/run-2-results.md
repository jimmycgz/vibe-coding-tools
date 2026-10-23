# Run 2 results (2026-10-22)

Run 2 ran 12 arms for 2 more trials of the notebook's 10 claims, streamed, in a rotated arm order, with timing. It follows the [run 2 plan](run-2-plan.md), which was committed before the run. Run 1 is in the [run 1 results](run-1-results.md).

Navigation: [index](../README.md) · [method](method.md) · [how caching is switched](how-caching-is-switched.md) · [raw records](../results/run2) · [table builder](../build_results_table.py)

## Result

All 12 arms passed 10 of 10 claims in both run 2 trials: 24 of 24 trials, 240 adjudications. That includes Sonnet 5.5 at medium effort with auto cache, which missed one claim in run 1; across the two runs it is perfect in 3 of its 4 trials. The arm with the explicit system breakpoint, whose two misses in run 1 were the open question, was not in run 2, so that result is neither confirmed nor refuted here.

- **No arm is separated on quality.** With every arm at 10 of 10 in run 2, the differences below are cost and time. Ten claims did not separate the arms on quality; the notebook itself says to use about 50 cases and at least 5 trials before a production decision.
- **Effort and quality, Sonnet 5.5 with auto cache, across both runs:** 4 of 4 trials perfect at high effort, 3 of 4 at medium and 4 of 4 at low. These runs show no drop with lower effort; the only miss was at medium effort. These are counts, with no claim about why.
- **Cost per task reproduces run 1** within 3.5 percent on every arm that ran in both (table below), well inside the trial-to-trial spread of the no-cache arms, which reached 10 percent.
- **Caching about halves the cost on all three models.** Without cache against with auto cache, both at high effort: Opus 5.5 $0.1972 to $0.0972 (2.0 times), Sonnet 5.5 $0.0919 to $0.0487 (1.9 times), Fable 5.1 $0.5329 to $0.2720 (2.0 times).
- **Effort moves cost less.** High against low effort with auto cache: Opus 5.5 $0.0972 to $0.0911 (6 percent lower), Sonnet 5.5 $0.0487 to $0.0465 (5 percent), Fable 5.1 $0.2720 to $0.2501 (8 percent). With two trials these are small differences, and the Opus and Sonnet ones are within the spread.
- **Time per claim, median over both trials:** Sonnet 5.5 8.0 to 8.8 seconds; Opus 5.5 11.2 to 11.9 seconds at high and medium effort and 8.8 at low effort; Fable 5.1 13.0 to 19.2 seconds. Fable's first event arrives sooner than the others (0.8 to 1.1 seconds against 1.4 to 2.0), but its claims take longer.
- **Low effort gave shorter claims on Opus and Fable, not on Sonnet.** With auto cache, Opus went from 11.9 to 8.8 seconds (26 percent shorter, inside the trial spread described below) and Fable from 19.2 to 13.0 (32 percent shorter, just outside it). Sonnet went from 8.0 to 8.4.
- **The cache did not shorten the claims.** High effort without cache against with auto cache: Opus 11.5 and 11.9 seconds, Sonnet 8.8 and 8.0, Fable 17.1 and 19.2. At this prefix size of about 13,000 tokens the cache cut cost and not time, within the spread below.
- **A cache write on a claim's first turn did not delay the first event** measurably: first event for first turns against later turns is 1.87 and 1.76 seconds for Opus 5.5 without cache and 1.79 and 1.72 with it, and similar on the other arms.

## The table

One row per arm. Pass counts are per trial, 10 claims each. Cost per task is by the notebook's formula, for each run on its own. The timing columns are run 2 only, because run 1 did not stream. Times are in seconds; the first-token columns are medians for the first turn of a claim and for later turns, separately, because the first turn of every claim pays the cache write. Arms are named by model and setting in words; [arms.json](../arms.json) holds the map to the ids in the raw records, and `python3 build_results_table.py results/run1 results/run2` rebuilds this table.

| Arm | Run 1 trials | Run 1 $ per task | Run 2 trials | Run 2 $ per task | Wall s per claim (median) | Wall s per request (median) | First event s, first turns / later turns (median) | First content s, first turns / later turns (median) | First text s, first turns / later turns (median) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Opus 5.5, high effort, no cache | 10/10, 10/10 | 0.1934 | 10/10, 10/10 | 0.1972 | 11.53 | 2.95 | 1.87 / 1.76 | 2.02 / 2.54 | 1.66 / 3.21 |
| Opus 5.5, high effort, auto cache | 10/10, 10/10 | 0.0956 | 10/10, 10/10 | 0.0972 | 11.89 | 3.05 | 1.79 / 1.72 | 1.91 / 2.70 | n/a / n/a |
| Opus 5.5, medium effort, auto cache | 10/10, 10/10 | 0.0931 | 10/10, 10/10 | 0.0932 | 11.21 | 2.87 | 1.99 / 1.71 | 1.99 / 2.45 | n/a / n/a |
| Opus 5.5, low effort, auto cache | 10/10, 10/10 | 0.0909 | 10/10, 10/10 | 0.0911 | 8.79 | 2.46 | 1.61 / 1.67 | 1.61 / 1.95 | n/a / 1.94 |
| Sonnet 5.5, high effort, no cache | not run | n/a | 10/10, 10/10 | 0.0919 | 8.80 | 2.30 | 1.51 / 1.47 | 1.51 / 2.24 | n/a / 4.67 |
| Sonnet 5.5, high effort, auto cache | 10/10, 10/10 | 0.0486 | 10/10, 10/10 | 0.0487 | 8.00 | 2.27 | 1.53 / 1.44 | 1.53 / 2.13 | n/a / 2.33 |
| Sonnet 5.5, medium effort, auto cache | 9/10, 10/10 | 0.0472 | 10/10, 10/10 | 0.0488 | 8.00 | 2.20 | 1.49 / 1.48 | 1.49 / 1.98 | n/a / 1.48 |
| Sonnet 5.5, medium effort, explicit system breakpoint | 9/10, 9/10 | 0.0200 | not run | n/a | n/a | n/a | n/a / n/a | n/a / n/a | n/a / n/a |
| Sonnet 5.5, low effort, auto cache | 10/10, 10/10 | 0.0465 | 10/10, 10/10 | 0.0465 | 8.37 | 2.34 | 1.61 / 1.43 | 1.61 / 2.05 | n/a / 2.07 |
| Fable 5.1, high effort, no cache | 10/10, 10/10 | 0.5415 | 10/10, 10/10 | 0.5329 | 17.12 | 3.28 | 0.82 / 0.88 | 1.36 / 3.17 | 1.36 / 1.64 |
| Fable 5.1, high effort, auto cache | 10/10, 10/10 | 0.2781 | 10/10, 10/10 | 0.2720 | 19.20 | 5.22 | 1.07 / 1.12 | 1.70 / 5.67 | 1.70 / 3.10 |
| Fable 5.1, medium effort, auto cache | not run | n/a | 10/10, 10/10 | 0.2628 | 15.86 | 3.24 | 0.87 / 1.05 | 1.54 / 3.58 | 1.54 / n/a |
| Fable 5.1, low effort, auto cache | not run | n/a | 10/10, 10/10 | 0.2501 | 12.96 | 2.95 | 0.89 / 1.03 | 0.89 / 2.95 | 0.89 / 2.40 |

How to read the timing columns:

- **Wall s per claim:** from the first request of a claim to its verdict, including local tool time.
- **Wall s per request:** from just before the request is opened to the end of the stream.
- **First event:** the first server event. **First content:** the first thinking, text or tool-input delta. **First text:** the first text delta, which only replies with text have. Most turns end in a tool call with no text: only 105 of 772 requests had any, so "n/a" is common in the first-text columns and the medians that do show rest on a few requests.

## How much to trust the differences

- **Two trials per arm.** For each arm the median claim time differed between its two trials by up to 30 percent (ratio of trial 2 to trial 1 between 0.76 and 1.30), so timing differences smaller than about 30 percent between close arms are not separable here. Fable against Sonnet is far outside that. The effort effect on time is plausible; confirming it needs more trials.
- **Cost per task between trials** differed by up to 10 percent on the no-cache arms (Opus 5.5 $0.2065 and $0.1878) and under 6 percent on the cached ones. The cost differences between effort levels are of that size.
- **Order and time of day.** The run took 66 minutes. The arm order was rotated by half the list in trial 2, which spreads time-of-day effects over the arms and does not remove them. The network and API load were not measured.
- **Retries.** All 772 requests ended with status 200. Two took a second attempt: a request on Sonnet 5.5 at medium effort (a timeout) and one on Fable 5.1 at low effort (a connection error). Medians are used because the failed attempt's wait is inside that claim's wall time, and one trial's total wall time of 998 seconds is that timeout. A request whose reply was lost may have been billed and is not counted.
- **Cached against uncached first-token times** are comparable only where the cache is warm. The first turn of every claim is cold in every cached arm, which is why first turns and later turns are shown apart.

## Spend and records

772 requests, 24 trials, three model ids from the API's own replies (`claude-opus-5-5` 261 requests, `claude-sonnet-5-5` 247, `claude-fable-5-1` 264). $40.65 by the notebook formula and $38.92 at list price, against an estimate of $41.38 made before the run. One further streamed smoke test (one claim of Sonnet 5.5 at low effort with auto cache, 3 requests, $0.04) ran first and is not in these records. The raw records are in [results/run2](../results/run2) and are unedited.
