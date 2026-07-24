"""Claude on Vertex AI — streaming latency & cost benchmark.

Measures, per model:
  - TTFT (time to first stream event, and time to first visible text)
  - Decode rate (output tokens / streaming window)
  - End-to-end latency
  - Cost per request (exact token counts from the API's usage block)

Run:  PROJECT_ID=my-project REGION=global python vertex_benchmark.py
Auth: gcloud auth application-default login
Deps: pip install 'anthropic[vertex]'
"""

import json
import os
import statistics
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import anthropic

PROJECT_ID = os.environ.get("PROJECT_ID", "your-gcp-project")
REGION = os.environ.get("REGION", "global")
NUM_ITERATIONS = int(os.environ.get("N", "5"))
RESULTS_FILE = os.environ.get("RESULTS_FILE", "results.json")

# ---------------------------------------------------------------------------
# Model registry — IDs and $/MTok from Vertex AI pricing (dated in README).
# thinking:
#   "adaptive"  -> {"type": "adaptive"} pinned (Claude 4.6+ family)
#   "always_on" -> parameter omitted; model thinks by design (Fable 5)
#   None        -> parameter omitted; model does not think (Haiku 4.5)
# ---------------------------------------------------------------------------
MODELS: Dict[str, Dict] = {
    # IDs verified live 2026-07-24 against platform.claude.com/docs (Vertex model
    # table) — current-gen models use bare IDs and require the "global" endpoint
    # (regional endpoints like us-east5 only serve Sonnet 4.6 and earlier).
    # Prices are Anthropic list $/MTok; global endpoint carries no premium
    # (us/eu multi-region adds 10%). Authoritative Vertex prices:
    # https://cloud.google.com/vertex-ai/generative-ai/pricing#claude-models
    "claude-fable-5": {
        "label": "Fable 5",
        "thinking": "always_on",
        "input": 10.00,
        "output": 50.00,
    },
    "claude-opus-5": {
        "label": "Opus 5",
        "thinking": "adaptive",  # on by default on Opus 5; pinned for parity
        "input": 5.00,
        "output": 25.00,
    },
    "claude-sonnet-5": {
        "label": "Sonnet 5",
        "thinking": "adaptive",
        "input": 2.00,   # intro pricing through 2026-08-31 ($3 after)
        "output": 10.00,  # intro pricing through 2026-08-31 ($15 after)
        # Sonnet 5's new tokenizer yields ~30% more tokens for the same text
        # (Anthropic migration guide) — normalized columns divide by this.
        "tokenizer_factor": 1.30,
    },
}

TEST_PROMPTS = [
    ("short", "Write a haiku about coding."),
    (
        "long",
        "Create a comprehensive guide to getting started with machine "
        "learning, including key concepts and practical steps.",
    ),
]

MAX_TOKENS_CONFIGS = [256, 1024]


def request_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = MODELS[model]
    return (input_tokens / 1e6) * p["input"] + (output_tokens / 1e6) * p["output"]


def build_kwargs(model: str, prompt: str, max_tokens: int) -> Dict:
    kwargs: Dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if MODELS[model]["thinking"] == "adaptive":
        kwargs["thinking"] = {"type": "adaptive"}
    return kwargs


def benchmark_streaming(
    client: anthropic.AnthropicVertex, model: str, prompt: str, max_tokens: int
) -> Dict:
    """One streamed request; timestamps taken client-side (wall clock)."""
    t_start = time.monotonic()
    t_first_event: Optional[float] = None
    t_first_text: Optional[float] = None

    with client.messages.stream(**build_kwargs(model, prompt, max_tokens)) as stream:
        for event in stream:
            if event.type == "content_block_delta":
                now = time.monotonic()
                if t_first_event is None:
                    t_first_event = now
                if (
                    t_first_text is None
                    and event.delta.type == "text_delta"
                    and event.delta.text
                ):
                    t_first_text = now
        final = stream.get_final_message()

    t_end = time.monotonic()
    input_tokens = final.usage.input_tokens
    output_tokens = final.usage.output_tokens  # includes thinking tokens
    e2e = t_end - t_start
    stream_window = t_end - t_first_event if t_first_event else e2e

    return {
        "model": model,
        "max_tokens": max_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "ttft_first_event_s": (t_first_event - t_start) if t_first_event else None,
        "ttft_first_text_s": (t_first_text - t_start) if t_first_text else None,
        "e2e_s": e2e,
        "decode_tok_per_s": output_tokens / stream_window if stream_window > 0 else 0,
        "cost_usd": request_cost(model, input_tokens, output_tokens),
        "stop_reason": final.stop_reason,
    }


def pct(values: List[float], p: float) -> float:
    s = sorted(values)
    k = max(0, min(len(s) - 1, round(p / 100 * (len(s) - 1))))
    return s[k]


def summarize(rows: List[Dict]) -> Dict:
    def col(name):
        return [r[name] for r in rows if r.get(name) is not None]

    tps, ttft = col("decode_tok_per_s"), col("ttft_first_text_s")
    return {
        "n": len(rows),
        "no_text_count": sum(1 for r in rows if r.get("ttft_first_text_s") is None),
        "truncated_count": sum(1 for r in rows if r.get("stop_reason") == "max_tokens"),
        "decode_tok_per_s_mean": statistics.mean(tps) if tps else None,
        "decode_tok_per_s_p50": pct(tps, 50) if tps else None,
        "ttft_first_text_p50_s": pct(ttft, 50) if ttft else None,
        "ttft_first_text_p99_s": pct(ttft, 99) if ttft else None,
        "e2e_mean_s": statistics.mean(col("e2e_s")),
        "avg_output_tokens": statistics.mean(col("output_tokens")),
        "avg_cost_usd": statistics.mean(col("cost_usd")),
        "total_cost_usd": sum(col("cost_usd")),
    }


def _f(x: Optional[float], spec: str = ".2f", prefix: str = "") -> str:
    return f"{prefix}{x:{spec}}" if x is not None else "n/a"


def run() -> None:
    client = anthropic.AnthropicVertex(project_id=PROJECT_ID, region=REGION)
    started = datetime.now(timezone.utc).isoformat()
    all_rows: List[Dict] = []

    print(f"Claude Vertex AI benchmark — project={PROJECT_ID} region={REGION} N={NUM_ITERATIONS}")
    for model, meta in MODELS.items():
        for max_tokens in MAX_TOKENS_CONFIGS:
            for tag, prompt in TEST_PROMPTS:
                for i in range(NUM_ITERATIONS):
                    try:
                        row = benchmark_streaming(client, model, prompt, max_tokens)
                        row["prompt"] = tag
                        all_rows.append(row)
                        ttft = row["ttft_first_text_s"]
                        ttft_s = f"{ttft:.2f}s" if ttft is not None else "n/a(no-text)"
                        print(
                            f"  {meta['label']:<10} mt={max_tokens:<5} {tag:<6} #{i+1}: "
                            f"ttft={ttft_s} "
                            f"decode={row['decode_tok_per_s']:.1f} tok/s "
                            f"out={row['output_tokens']} stop={row['stop_reason']} "
                            f"${row['cost_usd']:.5f}"
                        )
                    except anthropic.APIStatusError as e:
                        print(f"  {meta['label']} mt={max_tokens} {tag} #{i+1}: API error {e.status_code}: {e.message}")
                    except anthropic.APIConnectionError as e:
                        print(f"  {meta['label']} mt={max_tokens} {tag} #{i+1}: connection error: {e}")

    # Per-model × max_tokens summary + README-ready markdown.
    # "Norm tok/s" divides by the model's tokenizer_factor so a denser-output
    # tokenizer (Sonnet 5, ~1.3x) doesn't inflate apparent speed.
    # "$/task" = mean billed cost to complete the long prompt (thinking incl.) —
    # the cross-model efficiency unit that self-normalizes tokenizer + verbosity.
    # cost_delay_usd_s = $/task x s/task (lower = better) — the cost-delay
    # product, analogous to the energy-delay product in hardware benchmarking:
    # it rewards being cheap AND fast on the same completed task.
    summary: Dict[str, Dict] = {}
    print("\n| Model | max_tokens | TTFT p50 (s) | Decode tok/s | Norm tok/s | Time/task (s) | $/task | $*s index |")
    print("|---|---|---|---|---|---|---|---|")
    for model, meta in MODELS.items():
        factor = meta.get("tokenizer_factor", 1.0)
        for max_tokens in MAX_TOKENS_CONFIGS:
            rows = [r for r in all_rows if r["model"] == model and r["max_tokens"] == max_tokens]
            if not rows:
                continue
            s = summarize(rows)
            s["decode_tok_per_s_normalized"] = (
                s["decode_tok_per_s_mean"] / factor if s["decode_tok_per_s_mean"] else None
            )
            long_rows = [r for r in rows if r["prompt"] == "long"]
            s["cost_per_long_task_usd"] = (
                statistics.mean([r["cost_usd"] for r in long_rows]) if long_rows else None
            )
            s["time_per_long_task_s"] = (
                statistics.mean([r["e2e_s"] for r in long_rows]) if long_rows else None
            )
            s["cost_delay_usd_s"] = (
                s["cost_per_long_task_usd"] * s["time_per_long_task_s"]
                if s["cost_per_long_task_usd"] and s["time_per_long_task_s"]
                else None
            )
            summary[f"{model}|{max_tokens}"] = s
            flags = ""
            if s["no_text_count"]:
                flags = f" ({s['no_text_count']}/{s['n']} no-text)"
            print(
                f"| {meta['label']} | {max_tokens} | {_f(s['ttft_first_text_p50_s'])}{flags} "
                f"| {_f(s['decode_tok_per_s_mean'], '.1f')} | {_f(s['decode_tok_per_s_normalized'], '.1f')} "
                f"| {_f(s['time_per_long_task_s'], '.1f')} "
                f"| {_f(s['cost_per_long_task_usd'], '.5f', '$')} "
                f"| {_f(s['cost_delay_usd_s'], '.4f')} |"
            )

    artifact = {
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "project": PROJECT_ID,
        "region": REGION,
        "sdk_version": anthropic.__version__,
        "iterations": NUM_ITERATIONS,
        "models": {m: {k: v for k, v in meta.items()} for m, meta in MODELS.items()},
        "rows": all_rows,
        "summary": summary,
        "notes": [
            "output_tokens includes thinking tokens (billed as output).",
            "decode_tok_per_s = output_tokens / (t_end - t_first_event), client wall clock.",
            "ttft_first_text excludes the thinking phase; ttft_first_event includes it.",
            "Thinking pinned: adaptive on 4.6+ family; always-on by design on Fable 5; n/a on Haiku 4.5.",
        ],
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(artifact, f, indent=2)
    total = sum(r["cost_usd"] for r in all_rows)
    print(f"\n{len(all_rows)} requests, total spend ${total:.2f}. Raw data: {RESULTS_FILE}")


if __name__ == "__main__":
    run()
