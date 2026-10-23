# Vibe Coding Tools

A model benchmark, AI agent skills and tools for vibe coding workflows.

## Repository Structure

```text
vibe-coding-tools/
├── ai-benchmark-v2/           # Model benchmark: a fine-tuned eval set, cost and timing, prompt cache
├── ai-benchmark/              # Legacy benchmark: speed and cost on Vertex AI
└── agent-skills/              # Reusable agent skills
    ├── claude-code-statusbar/ # Color-coded Claude Code status line + popup alerts
    ├── distill-user/          # Mine transcript history into durable user-preference memory
    ├── internet-search/       # Domain-first, route-independent web search (no API keys)
    ├── markdown-render-qa/    # Catch Markdown that reads fine but renders wrong
    ├── nano-banana-pro-vertex/# Cinematic hero-image generation (Gemini 3 Pro Image on Vertex AI)
    ├── remove-background/     # Transparent PNG generation pipeline
    ├── svg-diagram-qa/        # Render-and-inspect QA for hand-authored SVG diagrams
    ├── vibe-deck/             # Automated PPTX & slide generation
    └── anthropic-skills/      # Anthropics submodule library
```

## [Model Benchmark v2](./ai-benchmark-v2)

A fine-tuned benchmark that scores frontier models on quality, cost and timing on the same task. Standard-library Python only.

- **Fine-tuned eval set:** 10 labelled, fictional insurance claims worked by a tool-using agent (12 tools, up to 6 turns per claim), so every run reports a pass rate. The task comes from Anthropic's cookbook; credits are in the v2 README.
- **Cost per task**, broken down into uncached input, cache write, cache read and output, across models, effort levels and prompt-cache settings.
- **Timing:** time to first event, output tokens per second, and time per request and per claim, with the connection kept out of the clock.
- **Prompt cache test:** no-cache, cold and warm requests on a long prompt, with every cache hit proven from the API's usage block.
- **Repeatable:** a plan committed before each paid run, a spend guard, and one command that builds the results table and charts.

Results, reports and references: [ai-benchmark-v2/README.md](./ai-benchmark-v2/README.md).

## [AI Benchmark (legacy)](./ai-benchmark)

Streaming speed and cost of Claude models on Vertex AI: time to first token, output tokens per second, and time and cost per task. Runs from October 2025 to July 2026. Details: [ai-benchmark/README.md](./ai-benchmark/README.md).

## Tested Frontier Models

These tools are designed for and tested with frontier-class AI models:

| Model | Provider | Notes |
|---|---|---|
| **Claude Fable 5** | Anthropic | Highest-capability long-horizon agentic work |
| **Claude Opus 4.8** | Anthropic | Deep reasoning + complex tasks |
| **Claude Sonnet 5** | Anthropic | Strong planning + execution, daily driver |
| **GPT-5** | OpenAI | Next-gen reasoning / Plan mode |
| **Gemini 3.x Pro** | Google DeepMind | Advanced agentic coding / Plan mode |

> **Note:** These skills require models with tool-use capabilities (file viewing, code execution, image inspection). Smaller or non-agentic models will not produce equivalent results.

## [Agent Skills](./agent-skills)

Reusable AI agent skills — drop into `.agents/skills/` for any agentic coding assistant.

### Custom Skills

| Skill | Description |
|---|---|
| [**claude-code-statusbar**](./agent-skills/claude-code-statusbar) | Color-coded Claude Code `statusLine` showing model, context size, usage bar, with escalating macOS popup alerts at 33%, 85%, 90%, and 95% context usage. |
| [**distill-user**](./agent-skills/distill-user) | Mine your local Claude Code transcript history for what you've said more than once — repeated requests, standing checks, corrections, preferences, dislikes — and distill it into memory rules with verbatim evidence, behind one approval gate. Runs entirely locally; workspace-scoped by default, global scan is opt-in. |
| [**internet-search**](./agent-skills/internet-search) | Domain-first, route-independent web search — prefers specific catalogs (GitHub, Stack Overflow, arXiv, Hugging Face, package registries) over generic web search, validates every hit with a live fetch, and fans out parallel workers for broad questions. Works with no WebSearch tool and no API keys (e.g. on a Vertex/Bedrock-blocked route). |
| [**markdown-render-qa**](./agent-skills/markdown-render-qa) | Catch Markdown that reads fine as raw text but renders wrong — collapsed setext headings, ineffective single-space hard breaks, `**Field:**` blocks merging into one paragraph — plus a per-case table for choosing Markdown vs HTML. Stdlib-only linter, no dependencies. |
| [**nano-banana-pro-vertex**](./agent-skills/nano-banana-pro-vertex) | Scriptable cinematic hero-image generation via Gemini 3 Pro Image (Nano Banana Pro) on Vertex AI — ADC auth, cost-tiered workflow (1K/2K/4K), parallel batch, PPTX-editable text-overlay sidecars. |
| [**remove-background**](./agent-skills/remove-background) | Remove white/light backgrounds from images to create transparent PNGs. Handles logos, icons, product photos, and multi-object images. |
| [**svg-diagram-qa**](./agent-skills/svg-diagram-qa) | Render-to-PNG-and-inspect QA for hand-authored SVG diagrams — catches overlapping boxes, painted-over labels, off-canvas text, and viewBox cropping that well-formed XML hides. |
| [**vibe-deck**](./agent-skills/vibe-deck) | A Streamlined Solution for Generating Professional Slide PNG Images (Python/Pillow) with Optional PPTX Assembly, Speaker Notes, and Configurable Branding |

### Anthropic Skills (submodule)

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

---

## Disclaimer

**Provided "as is", used entirely at your own risk.** These tools run shell commands, make network
calls, and drive AI agents on your machine; some suggest permission-allowlist entries or wrapper
scripts that reduce safety prompts.

- **No warranty (as-is).** All content in this repository — skills, scripts, wrappers, endpoint
  templates, configuration examples, and benchmarks — is provided "AS IS", **without warranty of any
  kind**, express or implied, including but not limited to merchantability, fitness for a particular
  purpose, and non-infringement (consistent with the [MIT License](./LICENSE)).
- **Limitation of liability.** In no event shall the author or contributors be liable for any claim,
  damages, or other liability — including system failures, security breaches, data loss, or
  unintended actions taken by an AI agent or shell command — arising from or in connection with this
  software or its use.
- **User responsibility.** You bear the **sole responsibility** for evaluating safety, testing,
  securing your system and credentials, and complying with your organization's policies before use.
  Adopt only what you understand and accept, and prefer a real security boundary (least-privilege
  credentials, a sandbox/VM) for anything you cannot afford to have go wrong.

---

*Tools for optimizing AI-assisted development workflows*
