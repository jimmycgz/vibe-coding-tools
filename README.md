# Vibe Coding Tools

A collection of AI agent skills, tools, and benchmarks for vibe coding workflows.

## Tested Frontier Models

These tools are designed for and tested with frontier-class AI models:

| Model | Provider | Notes |
|---|---|---|
| **GPT-4o / GPT-4.5** | OpenAI | Full agentic coding support |
| **GPT-5** | OpenAI | Next-gen reasoning |
| **Claude Sonnet 4 / 4.5** | Anthropic | Strong planning + execution |
| **Claude Opus 4** | Anthropic | Deep reasoning + complex tasks |
| **Gemini 3.1 Pro** | Google DeepMind | Advanced agentic coding |

> **Note:** These skills require models with tool-use capabilities (file viewing, code execution, image inspection). Smaller or non-agentic models will not produce equivalent results.

## Contents

### [Agent Skills](./agent-skills)
Reusable AI agent skills — drop into `.agents/skills/` for any agentic coding assistant.

| Skill | Description |
|---|---|
| [**slidedeck**](./agent-skills/slidedeck) | Generate professional slide PNGs (Python/Pillow) with optional PPTX assembly, speaker notes, and configurable branding |

### [AI Benchmark](./ai-benchmark)
Performance and cost comparison of Claude models on Vertex AI.

**Key Findings:**
- Haiku 4.5: ~2.3x faster, ~3x cheaper
- Sonnet 4.5: Superior reasoning for complex planning

**Recommended Usage:**
- 🎯 **Plan Mode** → Sonnet 4.5 (best design & architecture)
- ⚡ **Act Mode** → Haiku 4.5 (faster implementation & cost-effective)

See [ai-benchmark/README.md](./ai-benchmark/README.md) for detailed results.

---

*Tools for optimizing AI-assisted development workflows*
