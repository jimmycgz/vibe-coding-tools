# Model benchmark

A curated, optimized benchmark for model cost and timing, in plain stdlib-only Python scripts: `model_benchmark.py`, `cache_timing.py` and `build_results_table.py`. The first runs a tool-using agent task on Opus 5.5, Sonnet 5.5 and Fable 5.1 and reports cost per task and timing (`--measure cost|timing|both`), for each model, effort level and cache setting. The second tests the prompt cache one request at a time. The third builds the table and charts. Two more scripts run the same two tests on Gemini 3.8 Flash through Vertex AI: `gemini_benchmark.py` and `gemini_cache_timing.py`. The legacy folder, [ai-benchmark](../ai-benchmark/README.md), is unchanged.

Based on Anthropic's cost-optimisation cookbook notebook (MIT licence): [cost_optimization.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/cost_optimization/cost_optimization.ipynb), copied at the commit-pinned version [a162e01](https://github.com/anthropics/claude-cookbooks/blob/a162e0184e71b60290808a43961a6cbc8060123c/cost_optimization/cost_optimization.ipynb). Its insurance-claims task, its data and its cost formula are the starting point, and the credit is below.

## v1 and v2

| | v1 ([ai-benchmark](../ai-benchmark/README.md)) | v2 (this folder) |
|---|---|---|
| Task | One generation prompt per request, on Vertex AI | A tool-using agent loop: 10 claims, 12 tools, at most 6 turns per claim |
| Measured | Time to first token, output tokens per second, time per task, cost per task | Pass rate, cost per task with a breakdown (uncached input, cache write, cache read, output), and time (first event, first content, first text, wall time per request and per claim) |
| Quality | No scoring | A labelled eval set: every run reports a pass rate beside cost and time |
| Tools | None | 12 local tools over fictional data |
| Cache | None | Prompt cache on and off, effort levels side by side, and a cache timing test with the usage block as proof |
| Process | — | Plans committed before each paid run; table and charts built by default |

## Features

Agent-loop script, [model_benchmark.py](model_benchmark.py):

- **Cost per task**, from the `usage` block of every request, by the notebook's formula and with each model's own cache-read rate. Caching (none, automatic cache) and effort (high, medium, low) are arms, so the same task is priced across models and settings.
- **Timing**: time to first event, time to first content, time to first text, wall time per request, and wall time per claim. `--measure cost|timing|both` (default both) chooses what a run measures and shows; timing streams every request, and cost is always recorded from the usage block. The clock starts after the connection is open; the connection time is recorded apart.
- **Pass rate**: each claim's verdict is compared with the expected verdict; a trial passes at 10 of 10.
- **Spend guard**: stops before any request whose worst case would pass `--ceiling-usd`.
- **Arm choice**: `--configs` takes arm ids from [arms.json](arms.json); with no `--configs` the arms flagged `default` there run.
- **Rotated arm order** (`--order rotate`) so no arm always runs at the same point in the sequence.
- **Offline selftest** and a fault case that must fail: checks the cost formula against numbers the notebook printed, the stream parser against a canned stream, and the arm selection; no key and no network.

Cache timing script, [cache_timing.py](cache_timing.py):

- **Three states**, each with a different question after the same long prefix: no cache, cold (the first request, which writes the cache) and warm (a later request, which reads it). The long prefix is the benchmark's system prompt and tools plus the claims ledger, 148,271 tokens by the token counting endpoint.
- **The usage block is the proof**: every request is checked against its state (cold writes about the prefix size and reads none, warm reads about the prefix size and writes none, no cache neither). A request that fails is named in the report and left out of the medians.
- **Models and prefix sizes**: `--only opus,sonnet,fable` and `--prefixes long|13k|both`.
- **A reading rule fixed before the run**, a paired comparison over the repetitions, and a negative control (output speed should not depend on the cache state).
- **Table and charts by default**: `--report DIR` writes the table and three charts.

Gemini scripts, [gemini_benchmark.py](gemini_benchmark.py) and [gemini_cache_timing.py](gemini_cache_timing.py), with [gemini_models.json](gemini_models.json) for ids and list prices:

- **The same agent task on Gemini 3.8 Flash** (and Gemini 4 Argon when named) at high, medium and low thinking, through Vertex AI's streaming API, with function calling, the model's parts echoed back unchanged, and the same timing fields. Credentials come from the environment only; the project id and the access token are redacted from every record, dry run and error text, with a selftest and a fault case for it.
- **A cache timing test built for an implicit cache**: Gemini's cache cannot be switched off and reports no write, so the states are a first request, a repeat request that is a follow-up turn, and a second first request as a control. The hit threshold comes from a rule written before the run, and a reading with fewer than 8 valid repeat hits is "inconclusive".

Table and chart builder, [build_results_table.py](build_results_table.py): one command writes the results table and four charts (cost per task, what the cost is made of, time per claim, time to first event) from the raw records, with each arm named by model, effort level and cache setting. With `--consolidated` it reads several results folders and writes one page with the effort levels of Opus 5.5, Sonnet 5.5 and Gemini 3.8 Flash side by side. A second builder, [build_blog_charts.py](build_blog_charts.py), writes a value map (cost against time per claim), the cache savings and the Gemini follow-up turn from the published records. Standard library only; the charts are hand-written SVG.

## Achievements

- **A dataset for LLM evaluation, from the cookbook.** The cookbook's 10 fictional insurance claims, each with an expected verdict, labelled by hand according to the cookbook notebook (3 approve, 2 deny, 3 fraud, 2 supervisor), in [assets/eval_set.csv](assets/eval_set.csv), and the fictional backend data the 12 tools read (claims, prior claims, repair parts, damage photo records, estimates and the policy manual), under Anthropic's MIT licence. The dataset is the cookbook's, not ours. On top of it, this benchmark builds a 148,271-token long prefix from the claims ledger, for long-context cache timing.
- **The agent run** ([results](reports/run-1-results.md)): 10 claims, 2 trials per setting, every setting 10 of 10. The automatic prompt cache about halves cost per task on all three models; effort level moves cost 5 to 8 percent. Time per claim: Sonnet 8.0 to 8.8 s, Opus 8.8 to 11.9 s, Fable 13.0 to 19.2 s.
- **Effort levels side by side** ([results](reports/consolidated/consolidated-results.md)): Opus 5.5, Sonnet 5.5 and Gemini 3.8 Flash at low, medium and high, from the published records; nothing was run again. From low to high, Gemini 3.8 Flash's cost per task changes by +50% and its time per claim by a factor of 2.4, Opus 5.5's cost by +7% and Sonnet 5.5's by +5%. Gemini 3.8 Flash at low is the one arm below 10 of 10 (7 and 8).
- **The cache timing result** ([results](reports/cache-timing-results.md)): Sonnet 5.5, 148,000-token prompt, 10 paired sets. A warm cache read cost 9.2 times less than no cache. Median time to first token was about 8 percent lower warm (3.31 s against 3.61 s), but warm was faster in 7 of 10 pairs, short of the 8 set before the run, so a time saving is not established. Output speed did not change with the cache.
- **The cache-rewrite facts**: automatic caching never hit across different questions (180 of 180 first turns of cached arms wrote the prefix again and read nothing), so a hit with a new question needs an explicit breakpoint at the end of the shared prefix ([how caching is switched](reports/how-caching-is-switched.md)). Switching model writes a new cache. In a small separate check (10 requests, records not published), changing effort on Sonnet 5.5 kept the cache on the system prompt.
- **Gemini 3.8 Flash** ([results](reports/gemini-results.md)): at medium thinking it passed every claim at about half Sonnet 5.5's cost per task ($0.0261 against $0.0488) and took 2.5 times as long per claim (20.0 s against 8.0 s), and at low thinking it failed the pass bar (7 and 8 of 10). On a 171K-token prefix a follow-up turn cost 8.0 times less than a first request and was faster in all 7 valid pairs, but the pre-registered reading is "not seen" because 8 valid pairs were needed. A new question sent as a separate request never hit Gemini's implicit cache, at any size or wait tried; a follow-up turn did, at 52 to 98 percent.
- **The Sonnet quality finding.** In the published run every setting scored 10 of 10. In an earlier run cut short by a restart, whose records are not published, Sonnet 5.5 at medium effort missed one claim in 3 of 4 trials: one of two with automatic cache, and both with the explicit breakpoint (medium effort as defined in that run's plan; the request records store only a body hash). Sonnet 5.5 at low effort did not miss in any trial of either run. The cookbook's own saved run, on Sonnet 5, had low effort at 9 of 10 and 8 of 10. So medium effort, not low, is where Sonnet 5.5 fell short of 100 percent here.

## Run it

```bash
export ANTHROPIC_API_KEY=...            # the key is read from the environment and from nowhere else
export ANTHROPIC_WORKSPACE_ID=...       # only if your key is not scoped to a workspace
python3 model_benchmark.py --selftest                                   # offline checks, no key, no network
python3 model_benchmark.py --dry-run --configs opus-high-nocache        # prints the exact requests, no network
python3 model_benchmark.py --live --ceiling-usd 10 --trials 2 --configs opus-high-nocache,sonnet-medium-cache --out ./out
python3 build_results_table.py ./out --out ./out                        # the results table and four charts, into ./out
python3 cache_timing.py --dry-run                                       # the cache timing schedule, no network, no key
python3 cache_timing.py --live --only sonnet --ceiling-usd 10 --out ./timing   # then: --report ./timing
```

A live run spends real money: run one claim of one arm first (`--claims CLM-001 --trials 1`). With no `--configs`, the script runs the 13 arms flagged `default` in [arms.json](arms.json); `--estimate` prints the upper bound first. Arms are named like "Sonnet medium cache" or "Opus high no cache": the latest model versions (Opus 5.5, Sonnet 5.5, Fable 5.1); high, medium, low = effort level; cache = automatic prompt cache; no cache = none. The script also keeps the notebook's other arms, including three Haiku arms, as the notebook has them; they are not in the default set, none has been run, and the Haiku model id in [models.json](models.json) has not been checked against what a key can call.

## Reports

- [Run 1 results](reports/run-1-results.md): 12 arms, streamed, with cost and timing in one table and four charts.
- [Run 1 plan](reports/run-1-plan.md): the plan, committed before the run.
- [Method](reports/method.md): the task, the pass criterion, how cost and timing are measured.
- [Cache timing results, Sonnet](reports/cache-timing-results.md): is there a time saving from the cache? Cost saving clear, time saving not seen; with charts.
- [Plan for the next runs](reports/plan-next-runs.md): the plan for the cache timing test ([cache_timing.py](cache_timing.py)), run for Sonnet only, and for a repeated agent-loop run with the explicit-breakpoint arm, not run.
- [Effort levels side by side](reports/consolidated/consolidated-results.md): cost and time per claim for Opus 5.5, Sonnet 5.5 and Gemini 3.8 Flash at low, medium and high, with the claims passed under each bar, and the table of every arm.
- [Value map and cache savings](reports/blog/blog-charts.md): cost against time per claim for nine arms, cost with and without the cache for the agent task and for one request on a 148K-token prompt, and the Gemini 3.8 Flash follow-up turn on its own.
- [Gemini 3.8 Flash results](reports/gemini-results.md): the agent task, the cache timing test and what the diagnostic found about Gemini's implicit cache. [Plan and amendment](reports/gemini-plan.md).
- [How caching is switched](reports/how-caching-is-switched.md): the code that turns the prompt cache on and off, and what the recorded usage shows for each case. Pictures: [test flow](reports/test-flow.svg) and [cache switch](reports/cache-switch.svg).

Raw records are in [results/run1](results/run1) (the agent run) and [results/cache-timing-sonnet](results/cache-timing-sonnet) (the cache timing test), and for Gemini in [results/gemini-flash-loop](results/gemini-flash-loop), [results/gemini-flash-cache-timing](results/gemini-flash-cache-timing) and [results/gemini-diagnostic](results/gemini-diagnostic).

## Licence and credit

The data in [assets](assets) and the parts of the script that come from the notebook (the system prompts, the tool definitions, the rule card, the adjudication loop and the cost formula) are from Anthropic's `claude-cookbooks`, which is MIT-licensed. The licence text is in [LICENSE-claude-cookbooks](LICENSE-claude-cookbooks), the source commit is `a162e0184e71b60290808a43961a6cbc8060123c`, and [assets/SOURCE-SHA256.txt](assets/SOURCE-SHA256.txt) records the hash of every copied file. The rest of the scripts (streaming, timing, spend guard, cache timing test, table builder) fall under this repository's licence. The data is the cookbook's fictional insurance claims.

### References

- Anthropic cookbook, cost-optimisation notebook: [main](https://github.com/anthropics/claude-cookbooks/blob/main/cost_optimization/cost_optimization.ipynb) and [pinned to the copied commit](https://github.com/anthropics/claude-cookbooks/blob/a162e0184e71b60290808a43961a6cbc8060123c/cost_optimization/cost_optimization.ipynb).
- The cookbook repository, [anthropics/claude-cookbooks](https://github.com/anthropics/claude-cookbooks), and its [MIT licence](https://github.com/anthropics/claude-cookbooks/blob/main/LICENSE).
- Anthropic documentation: [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [effort](https://platform.claude.com/docs/en/build-with-claude/effort) and [token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting).
