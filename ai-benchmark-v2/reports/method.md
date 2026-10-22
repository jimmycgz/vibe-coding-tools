# Method

Navigation: [index](../README.md) · [run 1 results](run-1-results.md) · [run 2 plan](run-2-plan.md)

- **Task:** the notebook's claims-adjudication agent. One model call per turn, at most six turns per claim, with twelve local tools over the notebook's fictional data (claims, policy manual, repair parts, prior claims, photo metadata, estimates). A claim ends at the first terminal tool (approve, deny, route to supervisor, refer to the special investigation unit), at a reply with no tool use, or after turn 6.
- **Pass criterion, from the notebook:** an arm passes when it gets 10 of 10 claims right in every trial.
- **Cost:** per request, from the `usage` block, by the notebook's formula (`notebook_cost`) and with the model's own cache-read rate (`list_cost`). They differ only where that rate is not 0.10 times the input price.
- **Fresh cache per trial:** a new nonce at the head of the system prompt, as in the notebook, so each trial starts cold.
- **Spend guard:** before every request the script adds a generous worst case (input at twice the price plus the full output cap) and stops if that would pass `--ceiling-usd`.
- **Retries:** transient network errors and HTTP 429, 500, 502, 503 and 529 are retried up to four times.
- **Pre-registration:** run 1's plan was written down before its first paid call but is not in this repository, only its design as described here. [Run 2's plan](run-2-plan.md) is committed before run 2 starts.
- **Run 1** did not stream and recorded a timestamp after each reply only. **Run 2** streams every request and records time to first event, first content delta and first text delta, total wall time, and wall time per claim.
- **Arm names:** every report and table names an arm by model and setting in words. Raw records keep the ids they were recorded with, and [arms.json](../arms.json) maps them to the plain labels.
- **Table:** [build_results_table.py](../build_results_table.py) builds the one results table from the raw records.

The notebook was read as data (its JSON parsed) and no code from the cookbook repository was run or imported.
