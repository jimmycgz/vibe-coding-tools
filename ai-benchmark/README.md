# Claude Vertex AI Benchmark Results

## Overview
Performance and cost comparison between Claude Haiku 4.5 and Sonnet 4.5 using Google Cloud Vertex AI.

## Benchmark Results

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

## Key Findings

- **Haiku 4.5** is consistently ~2.3x faster than Sonnet 4.5
- **Haiku 4.5** is ~3x more cost-effective than Sonnet 4.5
- Both models produce similar output quality for the same prompts
- Performance remains consistent across different prompt complexities

## Recommendations for Cline Usage

### 🎯 Plan Mode → Sonnet 4.5
Use **Claude Sonnet 4.5** for Plan Mode when:
- Architecting complex solutions
- Designing system architecture
- Planning multi-step implementations
- Analyzing requirements and edge cases
- Quality and thoroughness are more important than speed

**Why?** Sonnet 4.5 provides superior reasoning and design capabilities, making it ideal for the planning phase where thoughtful analysis is critical.

### ⚡ Act Mode → Haiku 4.5
Use **Claude Haiku 4.5** for Act Mode when:
- Implementing code changes
- Executing planned tasks
- Running iterative development cycles
- Performing routine coding tasks
- Speed and cost-efficiency matter

**Why?** Haiku 4.5 delivers 2.3x faster execution at 1/3 the cost, making it perfect for rapid implementation and iteration during the execution phase.

## Configuration

**GCP Project:** `your-gcp-project`  
**Region:** `us-east5`

**Model Versions:**
- Haiku 4.5: `claude-haiku-4-5@20251001`
- Sonnet 4.5: `claude-sonnet-4-5@20250929`

## Running the Benchmark

```bash
cd /your-path/vibe-coding-tools/ai-benchmark
source ../ai-venv/bin/activate  # Activate virtual environment
python vertex_benchmark.py
```

## Pricing (Vertex AI)

| Model | Input Tokens | Output Tokens |
|-------|--------------|---------------|
| **Haiku 4.5** | $1.00/M | $5.00/M |
| **Sonnet 4.5** | $3.00/M | $15.00/M |

---

*Last updated: October 15, 2025*
