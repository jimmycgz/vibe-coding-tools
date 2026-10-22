# Model benchmark

A fine-tuned optimized benchmark for model cost and timing, in one plain stdlib-only Python script, `model_benchmark.py`. It runs a tool-using agent task on Opus 5.5, Sonnet 5.5 and Fable 5.1 and reports cost per task, and timing when run with `--stream`, for each model and setting. More model families are planned. The legacy folder, [ai-benchmark](../ai-benchmark/README.md), is unchanged.

It started from the cost-optimization notebook in Anthropic's cookbook (`cost_optimization/cost_optimization.ipynb`): its insurance-claims task, its data and its cost formula are the starting point, and the credit is below.

## Features

- **Cost per task**, from the `usage` block of every request, by the notebook's formula and with each model's own cache-read rate. Caching (none, auto cache) and effort (high, medium, low) are arms, so the same task is priced across models and settings.
- **Timing**, with `--stream`: time to first event, time to first content, time to first text, wall time per request, and wall time per claim. The first live use of the timing path is run 2, which has not run yet.
- **Spend guard**: stops before any request whose worst case would pass `--ceiling-usd`.
- **Rotated arm order** (`--order rotate`) so no arm always runs at the same point in the sequence.
- **Offline selftest**: checks the cost formula against numbers the notebook printed and the stream parser against a canned stream; it needs no key and no network.
- **One results table**: [build_results_table.py](build_results_table.py) builds the arm, pass-count and cost columns from the raw records (and the timing columns for a streamed run), with each arm named by model and setting in words ([arms.json](arms.json)). The notebook comparison column in the run 1 report was added by hand.

## Run it

```bash
export ANTHROPIC_API_KEY=...            # the key is read from the environment and from nowhere else
export ANTHROPIC_WORKSPACE_ID=...       # only if your key is not scoped to a workspace
python3 model_benchmark.py --selftest                                   # offline checks, no key, no network
python3 model_benchmark.py --dry-run --configs opus-high-nocache        # prints the exact requests, no network
python3 model_benchmark.py --live --ceiling-usd 10 --trials 2 --configs opus-high-nocache,sonnet-medium-cache --out ./out
python3 build_results_table.py results/run1                             # the results table, plain arm names
```

A live run spends real money: run one claim of one arm first (`--claims CLM-001 --trials 1`). Arm ids for `--configs` are listed in [arms.json](arms.json). The explicit-breakpoint arm is in run 1 only. The script also keeps the notebook's three Haiku arms as the notebook has them; they have not been run, and the Haiku model id in [models.json](models.json) has not been checked against what a key can call.

## Reports

- [Run 1 results](reports/run-1-results.md): what came back, with the caveats.
- [Run 2 plan](reports/run-2-plan.md): 12 arms, streamed, with timing; committed before the run.
- [Method](reports/method.md): the task, the pass criterion, how cost and timing are measured.
- [How caching is switched](reports/how-caching-is-switched.md): the lines of code that turn the prompt cache on and off, and what the recorded usage shows for each case. Pictures: [test flow](reports/test-flow.svg) and [cache switch](reports/cache-switch.svg).

Raw records are in [results/run1](results/run1).

## Licence and credit

The data in [assets](assets) and the parts of the script that come from the notebook (the system prompts, the tool definitions, the rule card, the adjudication loop and the cost formula) are from Anthropic's `claude-cookbooks`, which is MIT-licensed. The licence text is in [LICENSE-claude-cookbooks](LICENSE-claude-cookbooks), the source commit is `a162e0184e71b60290808a43961a6cbc8060123c`, and [assets/SOURCE-SHA256.txt](assets/SOURCE-SHA256.txt) records the hash of every copied file. The rest of the script (streaming, timing, spend guard, table builder) falls under this repository's licence. The data is the cookbook's fictional insurance claims.
