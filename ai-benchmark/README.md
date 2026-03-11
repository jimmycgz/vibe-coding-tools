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

## Recommendations for Cline Usage (2026 Meta)

> **Note:** The benchmark data above was collected in **October 2025**. As of early 2026, the frontier model landscape has expanded.

### 🎯 Plan Mode → Gemini 3.1 Pro / GPT-5 / Opus 4.6
Use **Gemini 3.1 Pro** or **GPT-5** (or **Claude Opus 4.6**) for Plan Mode when:
- Architecting complex solutions
- Designing system architecture
- Planning multi-step implementations
- Analyzing requirements and edge cases
- Quality and thoroughness are more important than speed

**Why?** These state-of-the-art models provide superior reasoning and design capabilities, making them ideal for the planning phase where thoughtful analysis is critical.

### ⚡ Act Mode → Gemini 3.1 Flash / Haiku 4.5
Use **Gemini 3.1 Flash** or **Claude Haiku 4.5** for Act Mode when:
- Implementing code changes
- Executing planned tasks
- Running iterative development cycles
- Performing routine coding tasks
- Speed and cost-efficiency matter

**Why?** These models deliver ultra-fast execution at a fraction of the cost, making them perfect for rapid implementation and fast agentic tool-looping. *(Note: Claude Haiku 4.6 is not yet available as of early 2026).*

## Configuration

**GCP Project:** `your-gcp-project`  
**Region:** `us-east5`

**Model Versions:**
- Haiku 4.5: `claude-haiku-4-5@20251001`
- Sonnet 4.5: `claude-sonnet-4-5@20250929`

## Setup & Running the Benchmark

### Prerequisites
- Python 3.11 or higher
- Google Cloud account with Vertex AI enabled
- Appropriate GCP permissions for Vertex AI

### Installation

1. **Clone the repository and navigate to the project:**
```bash
cd /your-path/vibe-coding-tools
```

2. **Create a virtual environment:**
```bash
python3 -m venv ai-venv
```

3. **Activate the virtual environment:**
```bash
source ai-venv/bin/activate
```

4. **Install required dependencies:**
```bash
pip install 'anthropic[vertex]'
```

5. **Authenticate with Google Cloud:**
```bash
gcloud auth application-default login
```
This will open a browser window for you to authenticate with your Google Cloud account.

6. **Configure your GCP project:**
Edit `vertex_benchmark.py` and update:
```python
PROJECT_ID = "your-gcp-project-id"
REGION = "us-east5"  # or your preferred region
```

### Running the Benchmark

```bash
cd ai-benchmark
python vertex_benchmark.py
```

### Deactivate Virtual Environment
When finished:
```bash
deactivate
```

## Pricing (Vertex AI)

| Model | Input Tokens | Output Tokens |
|-------|--------------|---------------|
| **Haiku 4.5** | $1.00/M | $5.00/M |
| **Sonnet 4.5** | $3.00/M | $15.00/M |

---

*Benchmark data collected: October 15, 2025*
*Recommendations updated: Early 2026*
