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

#### Custom Skills

| Skill | Description |
|---|---|
| [**slidedeck**](./agent-skills/slidedeck) | Generate professional slide PNGs (Python/Pillow) with optional PPTX assembly, speaker notes, and configurable branding |

#### Anthropic Skills (submodule)

Included via git submodule from [anthropics/skills](https://github.com/anthropics/skills). See their repo for license terms.

| Skill | Description |
|---|---|
| [**pptx**](./agent-skills/anthropic-skills/skills/pptx) | Create, edit, and read PowerPoint files via pptxgenjs or XML editing |
| [**docx**](./agent-skills/anthropic-skills/skills/docx) | Create and edit Word documents |
| [**xlsx**](./agent-skills/anthropic-skills/skills/xlsx) | Create and edit Excel spreadsheets |
| [**pdf**](./agent-skills/anthropic-skills/skills/pdf) | Parse, extract, and work with PDF files |
| [**canvas-design**](./agent-skills/anthropic-skills/skills/canvas-design) | Design visual assets using HTML Canvas |
| [**frontend-design**](./agent-skills/anthropic-skills/skills/frontend-design) | Build polished frontend UI components |
| [**web-artifacts-builder**](./agent-skills/anthropic-skills/skills/web-artifacts-builder) | Create interactive web artifacts |
| [**webapp-testing**](./agent-skills/anthropic-skills/skills/webapp-testing) | Test web applications systematically |
| [**algorithmic-art**](./agent-skills/anthropic-skills/skills/algorithmic-art) | Generate algorithmic and generative art |
| [**brand-guidelines**](./agent-skills/anthropic-skills/skills/brand-guidelines) | Create and apply brand identity systems |
| [**theme-factory**](./agent-skills/anthropic-skills/skills/theme-factory) | Build design themes and style systems |
| [**internal-comms**](./agent-skills/anthropic-skills/skills/internal-comms) | Draft internal communications and memos |
| [**doc-coauthoring**](./agent-skills/anthropic-skills/skills/doc-coauthoring) | Collaborative document writing |
| [**mcp-builder**](./agent-skills/anthropic-skills/skills/mcp-builder) | Build Model Context Protocol servers |
| [**skill-creator**](./agent-skills/anthropic-skills/skills/skill-creator) | Meta-skill for creating new skills |
| [**slack-gif-creator**](./agent-skills/anthropic-skills/skills/slack-gif-creator) | Create animated GIFs for Slack |

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
