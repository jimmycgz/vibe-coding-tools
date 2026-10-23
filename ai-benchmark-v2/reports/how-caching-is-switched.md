# How caching is switched on and off

The benchmark prices the same task with the prompt cache off and on. This report shows, in the script's own lines, what makes the difference in the request, and what the recorded usage shows for each case. Everything here is taken from [model_benchmark.py](../model_benchmark.py) and from the raw records of run 1 in [results/run1](../results/run1). The arm with an explicit system breakpoint has not been run, so case 3 below is from the code only.

Navigation: [index](../README.md) · [method](method.md) · [run 1 results](run-1-results.md) · [run 1 plan](run-1-plan.md) · picture of the test flow: [test-flow.svg](test-flow.svg) · picture of the cache switch: [cache-switch.svg](cache-switch.svg)

## The short version

Three cases, and the difference is where a `cache_control` field sits in the request. Nothing else changes: model, `max_tokens`, system prompt, tools, messages, thinking and effort are the same.

| Case | Arm setting in the script | What the request carries |
|---|---|---|
| No cache | `cache` off | No `cache_control` field anywhere. |
| Auto cache | `cache` on | One top-level field: `"cache_control": {"type": "ephemeral"}`. |
| Auto cache plus an explicit breakpoint on the system prompt | `cache` on and `cache_system` on | The same top-level field, and the `system` field is a list with one text block that carries its own `cache_control`. |

The explicit-breakpoint arm sends both fields. It is the auto-cache arm with one more breakpoint, as in the notebook. It has not been run.

## The lines that do it

All in `loop_body` (line 361 of `model_benchmark.py`):

```python
system = f"[trial {nonce}]\n\n" + base                                              # line 370
if cfg.get("cache_system"):                                                         # line 371
    system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]   # line 372
...
if cfg.get("cache"):                                                                # line 379
    body["cache_control"] = {"type": "ephemeral"}                                   # line 380
```

Each arm is one entry in the `CONFIGS` list with those two settings. The script never sends a `ttl`, so the cache lifetime is the default 5 minutes. The one-shot Batch API body (`batch_body`, lines 413 to 418) puts a `cache_control` on the system block and none on the request; that arm was not run.

## The nonce

`[trial <time>]` is the first line of the system prompt. It is created once per arm and trial, in `live()` (line 806, `nonce = time.time_ns()`), and passed to every request of that trial. So:

- A new trial gets a new nonce, so no cache from an earlier trial can be hit.
- **All 10 claims of one trial share the same nonce**, so the system prompt and tools are byte-identical from one claim to the next. The nonce does not reset the cache between claims.

Whether an earlier claim's cache is reused is then decided by the cache fields alone, which is what the three cases below show.

## Case 1: no cache

Arm: Opus high no cache. The request, trimmed:

```json
{"model": "claude-opus-5-5", "max_tokens": 4096,
 "system": "[trial <time>]\n\nYou are a Senior Adjuster ... (about 30,000 characters, with the policy manual)",
 "tools": "(12 tool definitions)",
 "messages": [{"role": "user", "content": "Adjudicate claim CLM-001: <the claim summary>"}],
 "thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}
```

Recorded usage, claim 1, turns 1 to 3 (input tokens, cache write, cache read): 13,090 / 0 / 0, then 13,606 / 0 / 0, then 13,744 / 0 / 0. Every turn re-reads the whole prefix at the full input price, and the input grows with the conversation.

## Case 2: auto cache

Arm: Sonnet medium cache. The only difference from case 1 is one field at the top level of the request:

```json
{"model": "claude-sonnet-5-5", "max_tokens": 4096, "system": "[trial <time>]\n\n...", "tools": "...",
 "messages": ["..."], "thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"},
 "cache_control": {"type": "ephemeral"}}
```

Recorded usage, claim 1: turn 1 writes 13,086 tokens and reads 0; turn 2 writes 518 and reads 13,086; turn 3 writes 294 and reads 13,604. So inside one claim the cache is warm from the second turn: each turn reads what the turn before wrote.

Across claims it is not warm. In trial 1, the first turn of each of the 10 claims wrote between 13,071 and 13,090 tokens and read 0. The first turn of every claim pays the cache write again.

## Case 3: auto cache plus an explicit breakpoint on the system prompt

Arm: Sonnet medium cache + breakpoint (not run). The `system` field becomes a list with one text block, and that block carries its own `cache_control`. The top-level field is still there:

```json
{"model": "claude-sonnet-5-5", "max_tokens": 4096,
 "system": [{"type": "text", "text": "[trial <time>]\n\nYou are a Senior Adjuster ...",
             "cache_control": {"type": "ephemeral"}}],
 "tools": "...", "messages": ["..."], "thinking": {"type": "adaptive"},
 "output_config": {"effort": "medium"}, "cache_control": {"type": "ephemeral"}}
```

No usage is recorded for this case. From the code: the system prompt and tools become a prefix with a breakpoint of their own, and the nonce is the same for all claims of a trial, so the prefix is byte-identical from claim to claim. The first turn of claims 2 to 10 should therefore read it from the cache instead of writing it again. That is expected from the code and the API documentation as I understand it; it is not measured here.

Why it matters: in the cached arms the cache write is the largest part of the cost (66 to 77 percent, see the [cost breakdown chart](cost-breakdown.svg)), because every claim's first turn writes the whole prefix again. Carrying the prefix across claims would turn most of those writes into reads, which are a tenth of the price. The arm is the way to measure that.

## What the cost formula does with these fields

`usage_cost()` prices a request from its `usage` block: cache writes at 1.25 times the input price for the 5-minute lifetime (2 times for 1 hour, which the script does not request), cache reads at 0.10 times, uncached input at 1 times, output at the output price. Those are the notebook's multipliers. `list_cost` uses each model's own cache-read rate instead, from [models.json](../models.json): 0.05 times on Opus 5.5 and 0.025 times on Fable 5.1.

## What I have and have not checked

- Checked in the script: the three cases above and the line numbers; the nonce is created once per arm and trial.
- Checked in the records: the three no-cache arms (Opus, Sonnet and Fable at high effort) show write 0 and read 0 on all 197 of their requests. In the nine cached arms, the first turn of every claim in both trials (180 requests) wrote between 13,071 and 13,090 tokens and read 0.
- Not measured: case 3, the explicit breakpoint. No record exists.
- Not tested: why the auto-cache arms do not read across claims. I infer it from the records and from the API documentation as I understand it: the automatic breakpoint sits at the end of the request, and the first user message differs from claim to claim, so no earlier entry is a prefix of the next claim's request. I have not tested the cache's lookback behaviour directly.

To see the three request shapes without a key: `python3 model_benchmark.py --dry-run --configs opus-high-nocache,sonnet-medium-cache,sonnet-medium-breakpoint --claims CLM-001 --dump bodies.jsonl`.
