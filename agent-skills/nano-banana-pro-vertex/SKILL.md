---
name: NanoBananaProVertex
description: Generate cinematic 16:9 images via Google's Gemini 3 Pro Image (Nano Banana Pro) on Vertex AI — multi-agent dispatch, editable PPTX-friendly outputs, ADC auth.
---

# NanoBananaProVertex Skill

Generate professional cinematic images via Google's **Gemini 3 Pro Image** (a.k.a. *Nano Banana Pro*) running on Vertex AI. Designed for slide-deck heroes, marketing visuals, and any scriptable hero-image need.

## When to Use

- User asks for an AI-generated hero image, cinematic visual, or illustrative composition
- Slide deck assembly needs a non-trivial title hero or section visual
- Workflow needs **scriptable** image generation (CLI or batch) — not interactive prompting in a UI

## When NOT to Use

- User wants editable text inside the image — overlay text in PowerPoint or Pillow instead, do NOT bake critical text into AI output
- User wants logos, branded marks, or trademarked imagery — use the real asset, never AI-generate
- Quick mockups where Imagen 4 (cheaper, GA, no preview gating) would do — see Cost Strategy below

## Prerequisites

1. **`gcloud` CLI installed and authenticated:**
   ```bash
   gcloud auth login
   gcloud config set project <YOUR_GCP_PROJECT>
   ```

2. **Application Default Credentials (ADC) set up — REQUIRED:**
   ```bash
   gcloud auth application-default login
   gcloud auth application-default set-quota-project <YOUR_GCP_PROJECT>
   ```
   The user-token from `gcloud auth print-access-token` does NOT work for Vertex AI image generation. You MUST use ADC via `gcloud auth application-default print-access-token`.

3. **Vertex AI API enabled in the GCP project:**
   ```bash
   gcloud services enable aiplatform.googleapis.com
   ```

4. **Project allowlisted for the preview model** (Nano Banana Pro is `PUBLIC_PREVIEW`):
   - If `verify_setup.sh` returns 404, request access via [Vertex AI Generative AI signup](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/image-generation)
   - Approval typically takes 1–3 business days
   - Until approved, fall back to **Imagen 4** (`imagen-4.0-generate-001`) — GA, no allowlist, cheaper

5. **Python 3.10+ with cairosvg** (only if you need SVG → PNG conversion for downstream work)

## The Six Verified Pitfalls (all observed during real builds)

| # | Pitfall | Fix |
|---|---|---|
| 1 | Model is at `locations/global`, NOT `us-central1` | Vertex AI catalog metadata lists `us-central1` for the model, but REST calls there return 404. Use `aiplatform.googleapis.com/v1/projects/{P}/locations/global/...` |
| 2 | Wrong auth token | Use ADC token (`gcloud auth application-default print-access-token`), not the user token |
| 3 | Quota project missing → 403 | Run `gcloud auth application-default set-quota-project <P>` once after ADC login |
| 4 | Saving artifacts to `/tmp/` | Always save to `<workspace>/tmp/` — `/tmp/` is forbidden per project hygiene rules |
| 5 | `responseModalities` casing | REST API requires camelCase `responseModalities`; Python SDK examples sometimes show `response_modalities` (snake_case) which fails with a schema error |
| 6 | Python `urllib` SSL failure on corporate proxies | `urllib.request.urlopen` doesn't pick up the system CA bundle. On corporate networks (Palo Alto, Zscaler), it returns `CERTIFICATE_VERIFY_FAILED`. The included `generate.py` and `batch.py` fall back to `curl` automatically (curl uses system CA store). If you write your own client, replicate this fallback. |

## Verified Facts

| Fact | Value |
|---|---|
| Model ID | `gemini-3-pro-image-preview` |
| Endpoint | `POST https://aiplatform.googleapis.com/v1/projects/{P}/locations/global/publishers/google/models/gemini-3-pro-image-preview:generateContent` |
| Status | `PUBLIC_PREVIEW` — model behavior may change before GA |
| Aspect ratios | `16:9` (default for hero), `9:16`, `1:1`, `4:3`, `3:4`, `21:9` + 4 others |
| Default resolution (16:9) | ~1376×768 (1K tier) |
| Max resolution | 3840×2160 (4K tier) |
| Cost (1K) | ~1500 tokens · ~$0.04 |
| Cost (2K) | ~2000 tokens · ~$0.08 |
| Cost (4K) | ~3000 tokens · ~$0.24 |
| Watermark | Invisible SynthID embedded in every output |
| Latency | ~15–25 sec per call at 1K, ~30–60 sec at 4K |

## Workflow

### Phase 1 — Style approval gate (sequential, user-in-the-loop)

**Always start sequentially.** Until visual style is approved, do NOT dispatch parallel agents.

1. Read user's intent / deck content / brand guidelines if any
2. Generate **v1 of the FIRST 1–2 hero images** sequentially via `scripts/generate.py`
3. Show output PNGs to user, capture feedback (style, palette, composition, mood)
4. Iterate prompts until visual direction is locked

**Why not parallel from the start:** sub-agents don't share style judgment. If you dispatch 10 hero generations in parallel before the user approves direction, you get stylistic drift and have to redo everything.

### Phase 2 — Parallel batch (multi-agent, post-approval)

Once style is locked:

1. Build a JSON manifest of remaining hero needs (`prompts.json`)
2. Run `scripts/batch.py prompts.json --concurrency 3` (or higher if API quota allows)
3. Each generation runs in a thread; the API serves them in parallel
4. Collect outputs, present a contact-sheet grid for final review

**Why parallel after approval:** sub-agents are independent at this point. Each owns a clean image with a known target style.

### Phase 3 — Editability for downstream PPTX (the hard rule)

**Never bake critical text into AI hero images.** AI text rendering, even on Nano Banana Pro, is unreliable for stylized titles. Instead:

1. AI generates **mood-and-metaphor only** (titans, monoliths, abstract shapes — no titles, no body text)
2. Skill emits hero PNG **+ optional JSON sidecar** describing intended overlays:
   ```json
   {
     "hero": "slide-01-titans.png",
     "overlays": [
       {"type": "title", "text": "A Clash of Titans", "x": 60, "y": 50, "font": "Helvetica-Bold", "size": 96, "color": "FFFFFF"},
       {"type": "subtitle", "text": "...", "x": 60, "y": 165, "font": "Helvetica", "size": 36, "color": "EBF0FA"}
     ]
   }
   ```
3. Downstream (PPTX assembler, slidedeck skill) renders these as **native PowerPoint text frames** layered over the hero. Speakers can edit titles directly in PowerPoint without re-running the AI.

If user explicitly asks for in-image text, warn them about the risk and proceed only with simple, short, non-stylized strings.

## Cost Strategy

**Iterate cheap, finalize expensive:**

```
Phase 1 (style exploration):  generate.py --tier 1k    # ~$0.04 per try
Phase 2 (style locked):       generate.py --tier 2k    # ~$0.08 per hero
Phase 3 (final selection):    generate.py --tier 4k    # ~$0.24 per winning hero
```

Don't generate at 4K until the prompt is locked. A typical deck of 10 heroes:
- ~30 exploration tries × $0.04 = $1.20
- ~10 locked-style 2K = $0.80
- ~3 final 4K = $0.72
- **Total: ~$2.70 for a fully heroed deck**

## Code Examples

### Verified curl invocation

```bash
PROJECT="${GOOGLE_CLOUD_PROJECT:-my-gcp-project}"
TOKEN="$(gcloud auth application-default print-access-token)"
URL="https://aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/global/publishers/google/models/gemini-3-pro-image-preview:generateContent"

cat > /tmp_workspace/req.json <<EOF
{
  "contents": [{
    "role": "user",
    "parts": [{
      "text": "Cinematic wide shot, 16:9. Two stylized monoliths on polished obsidian floor, cobalt and crimson lit, single luminous diff bar between them. Blade Runner 2049 production design. No text in image."
    }]
  }],
  "generationConfig": {
    "responseModalities": ["IMAGE"],
    "imageConfig": {"aspectRatio": "16:9"}
  }
}
EOF

curl -s -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  "${URL}" -d @/tmp_workspace/req.json -o /tmp_workspace/response.json
```

(Replace `/tmp_workspace/` with `<your-workspace>/tmp/nbpv/`.)

### Production CLI

```bash
generate.py "Two stylized monoliths..." \
  --project my-gcp-project \
  --aspect 16:9 \
  --tier 2k \
  --out workspace/tmp/nbpv/slide-04-monoliths.png
```

## Prompt Patterns

See [`references/prompt-patterns.md`](references/prompt-patterns.md) for recipes:
- Cinematic hero (epic establishing shot)
- Dual-arena composition (two specialists facing one artifact)
- Mythological figures (recognizable but not gamey)
- Minimalist architectural (clean isometric)
- Icon / badge (single symbol on solid background)

Every recipe says **WHAT works, what to AVOID, and what to LEAVE for Pillow overlay** (always: titles, body text, page numbers).

## Reference Implementation

- `scripts/verify_setup.sh` — Preflight: ADC, quota project, model reachable. Run this first.
- `scripts/generate.py` — Single-shot CLI for one prompt.
- `scripts/batch.py` — Parallel CLI for N prompts in a JSON manifest.
- `references/prompt-patterns.md` — Recipes for common slide-deck use cases.

## Related Skills

- **slidedeck** (`~/.claude/skills/slidedeck/`) — Consumes hero PNGs from this skill, overlays them with native PPTX text frames for editable titles.
- **web-research** (`~/.claude/skills/web-research/`) — Use to verify any pricing / model-version claims before citing in user-facing docs (LLM training is 1+ year stale on Vertex AI).
