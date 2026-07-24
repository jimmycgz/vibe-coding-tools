# Claude Vertex AI Benchmark Results

## Overview
Performance and cost comparison of Anthropic's Claude models on Google Cloud Vertex AI,
measured with a lightweight streaming harness (`vertex_benchmark.py`): TTFT, effective
throughput, and cost per completed task — exact token counts from the API's usage block.

**Latest run: July 24, 2026 — Claude Opus 5 launch day** (Opus 5 benchmarked within hours
of release). Previous run (October 2025, Haiku 4.5 vs Sonnet 4.5) archived below.

## Benchmark Results — July 24, 2026

Models: **Claude Fable 5 · Claude Opus 5 (launch day) · Claude Sonnet 5** — the current
"5" generation. (Opus 4.8 was also measured but is omitted from the comparison: it costs
the same as Opus 5 with materially lower capability — Anthropic reports Opus 5 at more
than double its Frontier-Bench score — so it is no longer a rational option; see caveats.)
Endpoint: Vertex AI `global` · N=5 per cell · thinking pinned to adaptive (always-on by
design on Fable 5) · 80 requests, $0.86 total.

### Speed (1,024-token generation task)

| Model | TTFT p50 | Effective tok/s | Normalized tok/s* | Time per task |
|-------|----------|-----------------|-------------------|---------------|
| **Sonnet 5** | 0.78s | 110.9 | 85.3 | 9.2s |
| **Fable 5** | 1.62s | 84.4 | 84.4 | 12.1s |
| **Opus 5** | ~8s† | 76.8 | 76.8 | 13.3s |

Effective tok/s = 1,024 output tokens ÷ end-to-end wall clock (p50) — includes TTFT and
any thinking phase, i.e. the pace you actually experience.
\* Sonnet 5's new tokenizer emits ~30% more tokens for the same text (Anthropic migration
guide); the normalized column divides by 1.3 so tokenizer density doesn't inflate speed.
† Opus 5 ships with adaptive thinking ON by default and thinks eagerly: first visible
text arrived 5.5–13.1s into the long task. Latency-sensitive callers should tune
`thinking`/`effort`; batch/agentic callers won't care — its end-to-end pace is Opus-class.

### Cost & efficiency (same 1,024-token task)

| Model | $/task | vs Fable 5 | Cost-delay index ($·s, lower = better) |
|-------|--------|------------|------------------------------------------|
| **Sonnet 5** | $0.0103 | 5.0× cheaper | **0.095** |
| **Opus 5** | $0.0258 | **2.0× cheaper** | 0.350 |
| **Fable 5** | $0.0516 | — | 0.627 |

Cost-delay index = $/task × seconds/task — the API analog of the energy-delay product in
hardware benchmarking: it rewards being cheap **and** fast on the same completed work.

### Key findings

- **The v5 models all finish in the same ~10-second band** (9.2–13.3s on the same task,
  a 1.4× spread) — serving speed is not the differentiator in this generation. Price is
  (5× spread per task), plus first-token latency for interactive feel (0.78s vs ~8s).
- **Opus 5 delivers near-frontier capability at exactly half Fable 5's token price**
  ($5/$25 vs $10/$50 per MTok) and ~1.8× better cost-delay on the same task. Anthropic's
  launch post (Jul 24, 2026) reports it within **0.5% of Fable 5's peak on CursorBench at
  half the cost per task**, and beating Fable 5 outright on OSWorld 2.0 at ~1/3 the cost.
- **Sonnet 5 is the efficiency king**: fastest time-to-done, 5× cheaper per task than
  Fable 5, best cost-delay index by 3× — and intro pricing ($2/$10) runs through Aug 31, 2026.
- **Fable 5 buys the capability ceiling, not speed**: always-on thinking and 2× token
  price make it the choice when correctness matters more than cost.
- **Opus 4.8 is superseded at the same price** — no rational reason to select it for new
  work (Anthropic cites no advantage; its remaining role is safety-classifier fallback).
  One measured footnote worth keeping: 4.8's TTFT was 0.83s p50 vs Opus 5's ~8s on the
  same task, because 4.8's adaptive thinking rarely engaged — so if you want Opus 5
  snappy for interactive use, lower `effort` or disable thinking rather than downgrading.

### Practitioner caveats (learned the honest way)

1. **Thinking can eat your `max_tokens`.** At a 256-token cap, Opus 5 spent the whole
   budget thinking and returned **zero visible text** in 6/10 short-prompt runs
   (`stop_reason: max_tokens`). Give thinking models generous output budgets.
2. **Day-one stream buffering.** Many Opus 5 responses arrived as end-of-stream bursts
   rather than steady deltas on Vertex, making naive inter-token decode rates meaningless
   (apparent 15K+ tok/s). Effective tok/s (wall-clock based) is robust to this.
3. **Tokenizers differ across models** — same prompt bills different `input_tokens`, and
   output token counts aren't comparable units of text across model families. Cross-model
   efficiency claims should use $/task, which self-normalizes.
4. Regional endpoints (e.g. `us-east5`) only serve Sonnet 4.6 and earlier — current-gen
   models require the `global` endpoint (no price premium) or `us`/`eu` multi-region (+10%).

## Recommendations for Cline Usage (July 2026 refresh)

### 🎯 Plan Mode → Opus 5 (Fable 5 for the hardest problems)
Flagship reasoning at half the previous flagship price. Use Fable 5 when correctness on
long-horizon, high-stakes work justifies 2× token cost.

### ⚡ Act Mode → Sonnet 5
Fastest task completion in this benchmark, 2.5× cheaper per task than the Opus tier at
intro pricing, near-Opus coding capability.

## Configuration

**Endpoint:** Vertex AI, region `global` · **SDK:** `anthropic[vertex]` 0.120.0
**Sampling:** N=5 per cell · 2 prompts (short/long) × max_tokens ∈ {256, 1024} · serial requests
**Thinking:** `{"type": "adaptive"}` pinned on Opus 5 / Opus 4.8 / Sonnet 5; always-on by design on Fable 5

**Model IDs (Vertex, verified 2026-07-24):**
- Fable 5: `claude-fable-5` · Opus 5: `claude-opus-5` · Sonnet 5: `claude-sonnet-5`

## Setup & Running the Benchmark

```bash
python3 -m venv ai-venv && source ai-venv/bin/activate
pip install 'anthropic[vertex]'
gcloud auth application-default login
cd ai-benchmark
PROJECT_ID=your-gcp-project REGION=global N=5 python vertex_benchmark.py
```

Raw per-request data (timestamps, token counts, costs, stop reasons) is written to
`results.json` for independent verification.

## Pricing (per MTok, verified 2026-07-24 from Anthropic's pricing page)

| Model | Input | Output |
|-------|-------|--------|
| Claude Fable 5 | $10.00 | $50.00 |
| Claude Opus 5 | $5.00 | $25.00 |
| Claude Sonnet 5 | $2.00 (intro, thru Aug 31 2026; $3.00 after) | $10.00 (intro; $15.00 after) |

Vertex global endpoint carries no premium over list; authoritative Google pricing:
https://cloud.google.com/vertex-ai/generative-ai/pricing#claude-models

---

## Archive — October 2025 run (Haiku 4.5 vs Sonnet 4.5)

### Performance (Tokens/Second)
| Model | max_tokens=256 | max_tokens=512 |
|-------|----------------|----------------|
| **Haiku 4.5** | 86.19 tokens/s | 90.78 tokens/s |
| **Sonnet 4.5** | 36.85 tokens/s | 39.20 tokens/s |
| **Speedup** | 2.34x faster | 2.32x faster |

### Cost per Request
| Model | max_tokens=256 | max_tokens=512 |
|-------|----------------|----------------|
| **Haiku 4.5** | $0.001012 | $0.001703 |
| **Sonnet 4.5** | $0.002991 | $0.005024 |
| **Cost Ratio** | 2.96x cheaper | 2.95x cheaper |

Haiku 4.5 was consistently ~2.3x faster and ~3x more cost-effective than Sonnet 4.5
(non-streaming harness, regional endpoint `us-east5`, N=3).
*October data collected: October 15, 2025.*

---

*Latest benchmark: July 24, 2026 (Claude Opus 5 launch day) · region `global` · total benchmark cost: $0.86*
