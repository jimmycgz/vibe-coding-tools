# Method

Navigation: [index](../README.md) · [run 1 results](run-1-results.md) · [run 1 plan](run-1-plan.md) · [how caching is switched](how-caching-is-switched.md)

- **Task:** the notebook's claims-adjudication agent. One model call per turn, at most six turns per claim, with twelve local tools over the notebook's fictional data (claims, policy manual, repair parts, prior claims, photo metadata, estimates). A claim ends at the first terminal tool (approve, deny, route to supervisor, refer to the special investigation unit), at a reply with no tool use, or after turn 6.
- **Pass criterion, from the notebook:** an arm passes when it gets 10 of 10 claims right in every trial.
- **Cost:** per request, from the `usage` block, by the notebook's formula (`notebook_cost`) and with the model's own cache-read rate (`list_cost`). They differ only where that rate is not 0.10 times the input price.
- **Fresh cache per trial:** a new nonce at the head of the system prompt, as in the notebook, so each trial starts cold.
- **Spend guard:** before every request the script adds a generous worst case (input at twice the price plus the full output cap) and stops if that would pass `--ceiling-usd`.
- **Retries:** transient network errors and HTTP 429, 500, 502, 503 and 529 are retried up to four times.
- **Pre-registration:** the [run 1 plan](run-1-plan.md) was committed before the run, so the git history shows the plan came first.
- **Timing:** with `--stream` every request is streamed and the script records time to first event, first content delta and first text delta, total wall time, and wall time per claim. Without `--stream` no timing is kept.
- **Arm names:** every report, table and chart names an arm by model, effort level and cache setting, for example "Sonnet medium cache" or "Opus high no cache". Models are the latest versions: Opus 5.5, Sonnet 5.5, Fable 5.1. high, medium, low = effort level; cache = automatic prompt cache; no cache = none. [arms.json](../arms.json) holds the labels.
- **Table and charts:** [build_results_table.py](../build_results_table.py) builds the results table and four charts (cost per task, what the cost is made of, time per claim, time to first event) from the raw records in one command.

The notebook was read as data (its JSON parsed) and no code from the cookbook repository was run or imported.
