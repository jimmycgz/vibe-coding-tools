# ai-benchmark-v2

A re-run of the cost-optimisation notebook from Anthropic's cookbook on current models (Opus 5.5, Sonnet 5.5, Fable 5.1), with a plain stdlib-only script instead of a notebook. The legacy folder, [ai-benchmark](../ai-benchmark/README.md), is unchanged.

## Run it

```bash
export ANTHROPIC_API_KEY=...            # the key is read from the environment and from nowhere else
export ANTHROPIC_WORKSPACE_ID=...       # only if your key is not scoped to a workspace
python3 run_cost_campaign.py --selftest                                   # offline checks, no key, no network
python3 run_cost_campaign.py --dry-run --configs opus-high-nocache        # prints the exact requests, no network
python3 run_cost_campaign.py --live --ceiling-usd 10 --trials 2 --configs opus-high-nocache,sonnet-medium-cache --out ./out
python3 build_results_table.py results/run1                               # the results table, plain arm names
```

A live run spends real money: run one claim of one arm first (`--claims CLM-001 --trials 1`). `--stream` and `--order rotate` are the run 2 options. Arm ids for `--configs` are listed in [arms.json](arms.json), which also holds the plain label each report uses.

## Reports

- [Run 1 results](reports/run-1-results.md): what came back, with the caveats.
- [Run 2 plan](reports/run-2-plan.md): 12 arms, streamed, with timing; committed before the run.
- [Method](reports/method.md): the task, the pass criterion, how cost and timing are measured.

Raw records are in [results/run1](results/run1).

## Licence and credit

The data in [assets](assets) and the parts of the script that reproduce the notebook (the system prompts, the tool definitions, the rule card, the adjudication loop and the cost formula) come from Anthropic's `claude-cookbooks`, which is MIT-licensed. The licence text is in [LICENSE-claude-cookbooks](LICENSE-claude-cookbooks), the source commit is `a162e0184e71b60290808a43961a6cbc8060123c`, and [assets/SOURCE-SHA256.txt](assets/SOURCE-SHA256.txt) records the hash of every copied file. The rest of the script (streaming, timing, spend guard, table builder) falls under this repository's licence. The data is the cookbook's fictional insurance claims.
