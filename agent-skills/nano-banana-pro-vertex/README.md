# NanoBananaProVertex Skill

Generate cinematic 16:9 images via Google's **Gemini 3 Pro Image** (Nano Banana Pro) on Vertex AI — scriptable from any project, with verified auth setup, 5 known pitfalls codified, and editable-PPTX-friendly output guidance.

## Why this skill exists

Google's docs and the Vertex AI catalog both lie about which region serves this model. Sub-agents repeatedly stumble on auth (user token vs ADC vs API key vs quota project). This skill encodes the verified, working setup so you don't re-discover it.

## Auth: Use ADC (recommended)

API keys do **not** work for Vertex AI's preview-tier image generation. Use Application Default Credentials (ADC). One-time setup:

```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT>
gcloud auth application-default login
gcloud auth application-default set-quota-project <YOUR_PROJECT>
gcloud services enable aiplatform.googleapis.com
```

> **If a user insists on API key auth:** they're likely thinking of the AI Studio Gemini API (`generativelanguage.googleapis.com`), which is a different surface from Vertex AI. Suggest they use that endpoint with their AI Studio API key — but note that preview models like `gemini-3-pro-image-preview` are typically Vertex-only at launch.

## Validate auth before you build anything

The fastest way to confirm setup works:

```bash
PROJECT="<YOUR_PROJECT>"
TOKEN="$(gcloud auth application-default print-access-token)"

# Test 1: token is valid
echo "Token length: ${#TOKEN}"   # Should print >100

# Test 2: project sees the model
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "x-goog-user-project: ${PROJECT}" \
  "https://aiplatform.googleapis.com/v1beta1/publishers/google/models/gemini-3-pro-image-preview"
# Expected: HTTP 200
# If 404: project not allowlisted for the preview model. Apply at:
#   https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/image-generation
# If 403: ADC quota project missing. Run:
#   gcloud auth application-default set-quota-project ${PROJECT}
```

If both tests pass, your setup is good. If not, the error code tells you exactly what to fix.

## Example curl — generate one image

This is the exact request body that works. **Note the camelCase `responseModalities`** — snake_case (`response_modalities`) returns 400.

```bash
PROJECT="<YOUR_PROJECT>"
TOKEN="$(gcloud auth application-default print-access-token)"

# IMPORTANT: locations/global is correct. NOT us-central1, despite what the
# Vertex AI catalog metadata says. REST calls to us-central1 return 404.
URL="https://aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/global/publishers/google/models/gemini-3-pro-image-preview:generateContent"

# Use <workspace>/tmp/, never /tmp/.
mkdir -p ./tmp/nbpv
cat > ./tmp/nbpv/req.json <<'EOF'
{
  "contents": [{
    "role": "user",
    "parts": [{"text": "Cinematic wide 16:9. Two stylized monoliths on polished obsidian, cobalt and crimson lit, single luminous diff bar between them. Blade Runner 2049 production design. No text in image."}]
  }],
  "generationConfig": {
    "responseModalities": ["IMAGE"],
    "imageConfig": {"aspectRatio": "16:9"}
  }
}
EOF

curl -s -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "x-goog-user-project: ${PROJECT}" \
  -H "Content-Type: application/json" \
  -d @./tmp/nbpv/req.json \
  -o ./tmp/nbpv/response.json \
  -w "HTTP %{http_code}, %{size_download} bytes, %{time_total}s\n" \
  "${URL}"

# Extract the inline base64 PNG
python3 -c "
import json, base64
d = json.load(open('./tmp/nbpv/response.json'))
parts = d['candidates'][0]['content']['parts']
for p in parts:
    if 'inlineData' in p:
        with open('./tmp/nbpv/hero.png', 'wb') as f:
            f.write(base64.b64decode(p['inlineData']['data']))
        print(f\"Saved ./tmp/nbpv/hero.png  tokens={d.get('usageMetadata',{}).get('totalTokenCount','?')}\")
"
```

After ~20 seconds: `./tmp/nbpv/hero.png` exists, ~1376×768.

## Example: production CLI

For repeated use, the included scripts wrap this safely:

```bash
# One-shot
python3 scripts/generate.py "your prompt" \
  --project ${PROJECT} \
  --aspect 16:9 \
  --tier 2k \
  --out ./tmp/nbpv/slide-01-hero.png

# Batch (parallel)
python3 scripts/batch.py prompts.json \
  --concurrency 3 \
  --out-dir ./tmp/nbpv/heroes/
```

## Workflow (why a skill, not just scripts)

This skill enforces a specific sequence:

1. **Phase 1 — Style approval gate (sequential).** Generate the first 1–2 heroes one at a time. Show user. Iterate.
2. **Phase 2 — Parallel batch (multi-agent).** Once style is locked, dispatch many agents in parallel via `batch.py`.
3. **Phase 3 — Editability for downstream PPTX.** Never bake critical text into AI heroes. Emit hero PNG + JSON sidecar listing intended overlays for the PPTX assembler to render as native text frames.

See [`SKILL.md`](SKILL.md) for the full workflow.

## What's inside

```
nano-banana-pro-vertex/
├── SKILL.md                      # Full skill instructions for AI agents
├── README.md                     # This file (human-facing)
├── scripts/
│   ├── verify_setup.sh           # Run first to confirm auth + model access
│   ├── generate.py               # Single-shot CLI
│   └── batch.py                  # Parallel multi-prompt CLI
└── references/
    └── prompt-patterns.md        # 5 recipes (cinematic / dual-arena / mythological / minimalist / icon)
```

## Cost reference

| Tier | Resolution (16:9) | ~Tokens | ~Cost |
|---|---|---|---|
| 1K | 1376×768 | 1500 | $0.04 |
| 2K | (scaled) | 2000 | $0.08 |
| 4K | 3840×2160 | 3000 | $0.24 |

Iterate at 1K (cheap), finalize winner at 4K. Typical 10-hero deck: ~$2.70 total.

## Six pitfalls (verified)

| Pitfall | Fix |
|---|---|
| Wrong region (`us-central1` returns 404) | Use `locations/global` |
| Wrong token (user-token returns 403) | Use `application-default print-access-token` |
| Quota project missing (403) | `gcloud auth application-default set-quota-project <P>` |
| Saving artifacts to `/tmp/` | Use `<workspace>/tmp/` |
| `response_modalities` (snake_case) returns 400 | Use camelCase: `responseModalities` |
| Corporate-proxy SSL (`urllib` returns `CERTIFICATE_VERIFY_FAILED`) | Scripts fall back to `curl` automatically. For custom clients, set `REQUESTS_CA_BUNDLE` or shell out to `curl` |

## Related skills

- **slidedeck** — Consumes hero PNGs from this skill, layers native PPTX text frames over them so speakers can edit titles in PowerPoint without re-running AI.
- **web-research** — Use to verify any pricing / model-version claims before citing in user-facing docs (LLM training is 1+ year stale on Vertex AI specifics).

## License

MIT
