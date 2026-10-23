# Vibe Coding Tools

A collection of AI agent skills, tools, and benchmarks for vibe coding workflows.

## Repository Structure

```text
vibe-coding-tools/
├── agent-skills/              # Reusable agent skills
│   ├── claude-code-statusbar/ # Color-coded Claude Code status line + popup alerts
│   ├── distill-user/          # Mine transcript history into durable user-preference memory
│   ├── internet-search/       # Domain-first, route-independent web search (no API keys)
│   ├── markdown-render-qa/    # Catch Markdown that reads fine but renders wrong
│   ├── nano-banana-pro-vertex/# Cinematic hero-image generation (Gemini 3 Pro Image on Vertex AI)
│   ├── remove-background/     # Transparent PNG generation pipeline
│   ├── svg-diagram-qa/        # Render-and-inspect QA for hand-authored SVG diagrams
│   ├── vibe-deck/             # Automated PPTX & slide generation
│   └── anthropic-skills/      # Anthropics submodule library
├── ai-benchmark-v2/           # Model benchmark: cost and timing, with the prompt cache (Oct 2026)
└── ai-benchmark/              # AI code & reasoning benchmarks (legacy, Oct 2025)
```

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

## [Model Benchmark v2](./ai-benchmark-v2)

A fine-tuned optimized benchmark for model cost and timing, tested October 2026 on Opus 5.5, Sonnet 5.5 and Fable 5.1. Stdlib-only Python scripts; `--measure cost|timing|both`.

**Key findings (Oct 2026):**

- Agent task, 10 claims, 2 trials per setting, every setting 10 of 10: the automatic prompt cache about halves cost per task on all three models; effort level moves cost 5 to 8 percent. Time per claim: Sonnet 8.0 to 8.8 s, Opus 8.8 to 11.9 s, Fable 13.0 to 19.2 s.
- Cache timing, Sonnet 5.5, 148,000-token prompt, 10 paired sets: a warm cache read cost 9.2 times less than no cache. Median time to first token was about 8 percent lower warm (3.31 s against 3.61 s), but warm was faster in 7 of 10 pairs, short of the 8 set before the run, so a time saving is not established. Output speed did not change with the cache.
- Switching model writes a new cache. In a small separate check (10 requests), changing effort on Sonnet 5.5 kept the cache on the system prompt.

**Strategy:** Sonnet is the worked example, to keep cost and time down. The cache timing script can run Opus and Fable (`--only`) and either prompt size (`--prefixes`); the Opus and Fable runs have not been done.

See [ai-benchmark-v2/README.md](./ai-benchmark-v2/README.md) for the method, the data and the charts.

## [AI Benchmark (legacy, October 2025)](./ai-benchmark)
Performance and cost comparison of Claude models on Vertex AI *(Tests conducted October 2025)*.

**Key Findings (Oct 2025):**
- Haiku 4.5: ~2.3x faster, ~3x cheaper than Sonnet 4.5
- Sonnet 4.5: Superior reasoning for complex planning

**Recommended Usage:**
- 🎯 **Plan Mode** → **Claude Opus 4.x** (Best design, architecture, and reasoning)
- ⚡ **Act Mode** → **Claude Sonnet 4.x** (Ultra-fast implementation & solid reasoning)

**Tooling:**
- Google Antigravity
- Anthropic Claude Code
- Cline


See [ai-benchmark/README.md](./ai-benchmark/README.md) for detailed results.

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
