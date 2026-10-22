# Run 1 results (2026-10-22)

Anthropic's cookbook has a notebook, `cost_optimization/cost_optimization.ipynb`, that takes an insurance-claims agent and lowers its cost per task step by step: prompt caching, effort levels, a cheaper model, and a few tool-side levers. Its headline is that Sonnet at medium effort with one explicit cache breakpoint on the system prompt is about 13 times cheaper than Opus at high effort with no cache, at the same pass rate. Run 1 ran the same task on current models.

Navigation: [index](../README.md) · [method](method.md) · [run 2 plan](run-2-plan.md) · [raw records](../results/run1) · [table builder](../build_results_table.py)

## Result

The cost ratio held in order of magnitude, and the quality result did not repeat once. Sonnet 5.5 at medium effort with the explicit system breakpoint was 9.6 times cheaper than Opus 5.5 at high effort with no cache (9.65 before rounding), against the notebook's 12.9. The notebook's own text says "13x"; 12.9 is its table's 0.2906 over 0.0226 (12.86). At the current Opus 5.5 price the notebook's own ratio would be 10.3 against 9.6 here. The breakpoint cut Sonnet medium's cost per task by 57.5 percent, from $0.0472 to $0.0200. It missed one claim of ten in both trials, on two different claims, where the notebook's got 10 of 10 in both. Two trials cannot separate a real drop from noise.

10 claims per trial, 2 trials per arm, 662 requests, all HTTP 200. Cost per task is by the notebook's formula (its own cache multipliers), in dollars, mean of the two trials. The notebook column is the mean of its two saved trials, billed at its own prices.

| Arm | Trial 1 | Trial 2 | $ per task | Notebook $ per task | Both trials 10/10 |
|---|---|---|---|---|---|
| Opus 5.5, high effort, no cache | 10/10 | 10/10 | 0.1934 | 0.2906 (one trial) | yes |
| Opus 5.5, high effort, auto cache | 10/10 | 10/10 | 0.0956 | 0.1505 | yes |
| Opus 5.5, medium effort, auto cache | 10/10 | 10/10 | 0.0931 | 0.1368 | yes |
| Opus 5.5, low effort, auto cache | 10/10 | 10/10 | 0.0909 | 0.1205 | yes |
| Sonnet 5.5, high effort, auto cache | 10/10 | 10/10 | 0.0486 | 0.0537 | yes |
| Sonnet 5.5, medium effort, auto cache | 9/10 | 10/10 | 0.0472 | 0.0497 | no |
| Sonnet 5.5, medium effort, explicit system breakpoint | 9/10 | 9/10 | 0.0200 | 0.0226 | no |
| Sonnet 5.5, low effort, auto cache | 10/10 | 10/10 | 0.0465 | 0.0502 | yes |
| Fable 5.1, high effort, no cache | 10/10 | 10/10 | 0.5415 | not in the notebook | yes |
| Fable 5.1, high effort, auto cache | 10/10 | 10/10 | 0.2781 | not in the notebook | yes |

- **Ratio:** Opus 5.5 at high effort with no cache over Sonnet 5.5 at medium effort with the explicit system breakpoint is 9.65 (9.5 to 9.8 across the two breakpoint trials). The notebook's 12.9 used Opus at $5/$25 per million tokens; Opus 5.5 is $4/$20, and at those prices the notebook's own ratio is 10.3 (0.2906 times 0.8, over 0.0226). I could not check that 10.3 against a run, only against the price.
- **Cost per task was lower than the notebook's saved runs on every Opus and Sonnet arm.** Part of that gap on the Opus arms is price: Opus 5.5 is $4/$20 per million tokens against the notebook's $5/$25. Dollars were compared, not token counts, so this does not show that fewer tokens were used.
- **Caching** about halves Opus cost. The effort steps barely move it: Opus at high, medium and low effort cost $0.0956, $0.0931 and $0.0909.
- **Sonnet 5.5 at low effort with auto cache** kept 10 of 10 in both trials at $0.0465 per task, 4.2 times cheaper than Opus 5.5 at high effort with no cache. Do not rank it above Sonnet at medium or high effort: Sonnet at medium missed once and Sonnet at low did not, which points to noise, and the gaps between the three are inside the spread.
- **Misses:** Sonnet at medium effort with auto cache missed CLM-008 in trial 1; Sonnet at medium effort with the explicit breakpoint missed CLM-007 in trial 1 and CLM-010 in trial 2. Three misses, three different claims.
- **Not established:** 20 adjudications per arm is small. The notebook itself says to use about 50 cases and at least 5 trials before a production decision. I understand that Sonnet 5.5's effort levels were recalibrated from Sonnet 5, so a medium on 5.5 may not be the same step; that comes from Anthropic's API reference and I have not tested it. There is no run on Sonnet 5 to separate the model from the effort calibration.
- **Fable** is not in the notebook, so its arms have nothing to compare against. Fable with no cache cost 2.8 times Opus 5.5 with no cache.
- **Spend:** $29.62 by the notebook formula, $28.74 at list price. The run's console log showed 24 TLS errors retried and recovered in the second half. That count is the author's: the request records do not store retries, and every record has status 200 and an empty error field. Run 2 records an `attempts` field per request. A request whose reply was lost on the wire may have been billed and is not counted.
- **Interruption:** the run was cut after three arms (Opus 5.5 at high effort with no cache, and Opus 5.5 at high and at medium effort with auto cache), and the other seven arms were relaunched with the same script and settings, so the raw records are in two parts. The cut run had already started the next arm (Opus 5.5 at low effort with auto cache): its first six claims, 18 requests costing $0.52, are in the first record file and are counted in the 662 requests and the $29.62, but they are in no trial result, because that arm was run again in full in the second part.

Models that ran, from the API's replies: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-fable-5-1`. No Haiku arm was run.

The raw records keep the arm ids they were recorded with. [arms.json](../arms.json) maps them to the labels above, and [build_results_table.py](../build_results_table.py) builds the arm, pass-count and cost columns from the records through that map. The notebook column and the both-trials column in the table above were added by hand.
