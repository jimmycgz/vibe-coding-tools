# Cookbook cost optimisation, re-run on current models

Anthropic's cookbook has a notebook, `cost_optimization/cost_optimization.ipynb`, that takes an insurance-claims agent and lowers its cost per task step by step: prompt caching, effort levels, a cheaper model, and a few tool-side levers. Its headline is that Sonnet at medium effort with one explicit cache breakpoint on the system prompt is about 13 times cheaper than Opus at high effort with no cache, at the same pass rate. This folder re-runs that on current models, with a plain script instead of a notebook, and records what came back.

Navigation: [script](run_cost_campaign.py) · [model ids and prices](models.json) · [run 2 pre-registration](PREREGISTRATION-run2.md) · [run 1 raw records](results/run1) · [cookbook licence](LICENSE-claude-cookbooks) · [data hashes](assets/SOURCE-SHA256.txt) · [parent folder](../README.md)

## Result of run 1 (2026-10-22)

The cost ratio held roughly, and the quality result did not repeat once. Sonnet 5.5 at medium effort with the explicit system breakpoint was about 9.7 times cheaper than Opus 5.5 at high effort with no cache (9.65), against the notebook's 12.9, which is 10.3 at today's Opus price. The breakpoint cut Sonnet medium's cost per task by 57.5 percent, from $0.0472 to $0.0200. It missed one claim of ten in both trials, on two different claims, where the notebook's got 10 of 10 in both. Two trials cannot separate a real drop from noise.

10 claims per trial, 2 trials per arm, 662 requests, all HTTP 200. Cost per task is by the notebook's formula (its own cache multipliers), in dollars, mean of the two trials. The notebook column is the mean of its two saved trials, billed at its own prices.

| Arm | Model and setting | Trial 1 | Trial 2 | $ per task | Notebook $ per task | Both trials 10/10 |
|---|---|---|---|---|---|---|
| O0 (notebook B0) | Opus 5.5, high, no cache | 10/10 | 10/10 | 0.1934 | 0.2906 (one trial) | yes |
| O1 (L1) | Opus 5.5, high, auto cache | 10/10 | 10/10 | 0.0956 | 0.1505 | yes |
| O2 (L2) | Opus 5.5, medium, auto cache | 10/10 | 10/10 | 0.0931 | 0.1368 | yes |
| O3 (L3) | Opus 5.5, low, auto cache | 10/10 | 10/10 | 0.0909 | 0.1205 | yes |
| S1 (L4) | Sonnet 5.5, high, auto cache | 10/10 | 10/10 | 0.0486 | 0.0537 | yes |
| S2 (L5) | Sonnet 5.5, medium, auto cache | 9/10 | 10/10 | 0.0472 | 0.0497 | no |
| S3 (L6) | Sonnet 5.5, low, auto cache | 10/10 | 10/10 | 0.0465 | 0.0502 | yes |
| S2b (V1) | S2 plus an explicit system breakpoint | 9/10 | 9/10 | 0.0200 | 0.0226 | no |
| F0 | Fable 5.1, high, no cache | 10/10 | 10/10 | 0.5415 | not in the notebook | yes |
| F1 | Fable 5.1, high, auto cache | 10/10 | 10/10 | 0.2781 | not in the notebook | yes |

The ids in brackets are the notebook's own labels (L for its ladder list, V for its levers list), kept once here so the arms can be matched to the notebook. The new ids are a model letter (O Opus, S Sonnet, F Fable) and a digit for the setting: 0 high effort with no cache, 1 high cached, 2 medium cached, 3 low cached. A trailing letter marks a notebook lever on that arm. Run 1's raw files keep the old ids.

- **Ratio:** O0 over S2b is 9.65, about 9.7 (9.5 to 9.8 across the two S2b trials). The notebook's 12.9 used Opus at $5/$25 per million tokens; Opus 5.5 is $4/$20, and at those prices the notebook's own ratio is 10.3.
- **Cost per task was lower than the notebook's saved runs on every Opus and Sonnet arm.** Part of that gap on the Opus arms is price: Opus 5.5 is $4/$20 per million tokens against the notebook's $5/$25. Dollars were compared, not token counts, so this does not show that fewer tokens were used.
- **Caching** about halves Opus cost. The effort steps barely move it: Opus high, medium and low cost $0.0956, $0.0931 and $0.0909.
- **S3** kept 10 of 10 in both trials at $0.0465 per task, 4.2 times cheaper than O0. Do not rank S3 above S2 or S1: S2 missed once and S3 did not, which points to noise, and the gaps between the three are inside the spread.
- **Misses:** S2 trial 1 missed CLM-008, S2b trial 1 missed CLM-007 and trial 2 missed CLM-010. Three misses, three different claims.
- **Not established:** 20 adjudications per arm is small. The notebook itself says to use about 50 cases and at least 5 trials before a production decision. I understand that Sonnet 5.5's effort levels were recalibrated from Sonnet 5, so a medium on 5.5 may not be the same step; that comes from Anthropic's API reference and I have not tested it. There is no run on Sonnet 5 to separate the model from the effort calibration.
- **Fable** is not in the notebook, so its arms have nothing to compare against. Cold Fable cost 2.8 times cold Opus 5.5.
- **Spend:** $29.62 by the notebook formula, $28.74 at list price. 24 TLS errors were retried and recovered in the second half; a request whose reply was lost on the wire may have been billed and is not counted.
- **Interruption:** the run was cut after O0, O1 and O2 and the other seven arms were relaunched with the same script and settings, so the raw records are in two parts.

Models that ran, from the API's replies: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-fable-5-1`. No Haiku arm was run.

## Method

- **Task:** the notebook's claims-adjudication agent. One model call per turn, at most six turns per claim, with twelve local tools over the notebook's fictional data (claims, policy manual, repair parts, prior claims, photo metadata, estimates). A claim ends at the first terminal tool (approve, deny, route to supervisor, refer to the special investigation unit), at a reply with no tool use, or after turn 6.
- **Pass criterion, from the notebook:** an arm passes when it gets 10 of 10 claims right in every trial.
- **Cost:** per request, from the `usage` block, by the notebook's formula (`notebook_cost`) and with the model's own cache-read rate (`list_cost`). They differ only where that rate is not 0.10 times the input price.
- **Fresh cache per trial:** a new nonce at the head of the system prompt, as in the notebook, so each trial starts cold.
- **Spend guard:** before every request the script adds a generous worst case (input at twice the price plus the full output cap) and stops if that would pass `--ceiling-usd`.
- **Retries:** transient network errors and HTTP 429, 500, 502, 503 and 529 are retried up to four times.
- **Pre-registration:** run 1's plan was written down before its first paid call but is not in this repository, only its design as described here. [Run 2's plan](PREREGISTRATION-run2.md) is committed before run 2 starts.
- **Run 1** did not stream and recorded a timestamp after each reply only. **Run 2** streams every request and records time to first event, first content delta and first text delta, total wall time, and wall time per claim.

## Running it

```bash
export ANTHROPIC_API_KEY=...            # the key is read from the environment and from nowhere else
export ANTHROPIC_WORKSPACE_ID=...       # only if your key is not scoped to a workspace
python3 run_cost_campaign.py --selftest                    # offline checks against numbers the notebook printed
python3 run_cost_campaign.py --dry-run --configs O0,S2     # prints the exact first-turn requests; no network, no key
python3 run_cost_campaign.py --estimate --trials 2         # upper bound from saved per-task costs
python3 run_cost_campaign.py --live --ceiling-usd 10 --trials 2 --configs O0,S2 --out ./out
```

`--stream` and `--order rotate` are the run 2 options. A live run spends real money; run one claim of one arm first (`--claims CLM-001 --trials 1`). The script uses only the Python standard library.

## Licence and credit

The data in `assets/` and the parts of `run_cost_campaign.py` that reproduce the notebook (the system prompts, the tool definitions, the rule card, the adjudication loop and the cost formula) come from Anthropic's `claude-cookbooks`, which is MIT-licensed. The licence text is kept in [LICENSE-claude-cookbooks](LICENSE-claude-cookbooks), the source commit is `a162e0184e71b60290808a43961a6cbc8060123c`, and [assets/SOURCE-SHA256.txt](assets/SOURCE-SHA256.txt) records the hash of every copied file. The script's streaming, timing, arm naming, spend guard and the rest are this repository's own and fall under its licence. The data is the cookbook's fictional insurance claims.

The notebook was read as data (its JSON parsed) and no code from the cookbook repository was run or imported.
