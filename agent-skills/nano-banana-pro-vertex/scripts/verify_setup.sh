#!/usr/bin/env bash
# verify_setup.sh — Smoke-test Nano Banana Pro on Vertex AI for the current project.
#
# Checks (in order):
#   1. gcloud auth application-default print-access-token returns a valid token
#   2. Quota project is set on ADC
#   3. The model gemini-3-pro-image-preview is reachable (no 404)
#   4. A tiny test image generation succeeds (HTTP 200, returns an inline image)
#
# Outputs a real test PNG to <workspace>/tmp/nbpv/smoke-test.png on success.
#
# Usage:
#   PROJECT=my-gcp-project ./verify_setup.sh
#   # or, if GOOGLE_CLOUD_PROJECT or `gcloud config get-value project` is set, no env var needed

set -euo pipefail

# ── Color output ────────────────────────────────────────────────
GREEN="\033[1;32m"
RED="\033[1;31m"
YELLOW="\033[1;33m"
DIM="\033[2m"
RESET="\033[0m"

ok()    { echo -e "  ${GREEN}[OK]${RESET}    $*"; }
fail()  { echo -e "  ${RED}[FAIL]${RESET}  $*" >&2; }
warn()  { echo -e "  ${YELLOW}[WARN]${RESET}  $*"; }
info()  { echo -e "  ${DIM}$*${RESET}"; }

# ── Resolve PROJECT ────────────────────────────────────────────
PROJECT="${PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}"
if [[ -z "${PROJECT}" ]]; then
  PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "${PROJECT}" ]]; then
  fail "No project set. Pass PROJECT=<id> env var or run: gcloud config set project <id>"
  exit 1
fi
info "Project: ${PROJECT}"

# ── Resolve workspace tmp directory ───────────────────────────
# Per project file-safety rule: NEVER use /tmp/. Use <workspace>/tmp/nbpv/.
WORKSPACE="${WORKSPACE:-$(pwd)}"
TMP_DIR="${WORKSPACE}/tmp/nbpv"
mkdir -p "${TMP_DIR}"
info "Workspace tmp: ${TMP_DIR}"
echo ""

# ── 1. ADC token ──────────────────────────────────────────────
echo "1. Checking Application Default Credentials..."
TOKEN="$(gcloud auth application-default print-access-token 2>/dev/null || true)"
if [[ -z "${TOKEN}" ]]; then
  fail "ADC not configured. Run:"
  fail "    gcloud auth application-default login"
  fail "    gcloud auth application-default set-quota-project ${PROJECT}"
  exit 2
fi
ok "ADC token present (${#TOKEN} chars)"

# ── 2. Quota project ──────────────────────────────────────────
echo ""
echo "2. Checking ADC quota project..."
ADC_FILE="${HOME}/.config/gcloud/application_default_credentials.json"
if [[ -f "${ADC_FILE}" ]]; then
  QPROJ="$(python3 -c "import json,sys; d=json.load(open('${ADC_FILE}')); print(d.get('quota_project_id', ''))" 2>/dev/null || true)"
  if [[ -z "${QPROJ}" ]]; then
    warn "ADC quota project not set. Run: gcloud auth application-default set-quota-project ${PROJECT}"
    warn "Continuing — will pass via header instead, but persistent setup is recommended"
  elif [[ "${QPROJ}" != "${PROJECT}" ]]; then
    warn "ADC quota project is ${QPROJ}, but PROJECT is ${PROJECT}. Mismatch may cause 403."
  else
    ok "ADC quota project = ${QPROJ}"
  fi
fi

# ── 3. Model reachability ─────────────────────────────────────
echo ""
echo "3. Checking model reachability at locations/global..."
URL="https://aiplatform.googleapis.com/v1beta1/publishers/google/models/gemini-3-pro-image-preview"
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "x-goog-user-project: ${PROJECT}" \
  "${URL}")"
if [[ "${HTTP_CODE}" != "200" ]]; then
  fail "Publisher model lookup returned HTTP ${HTTP_CODE}"
  fail "Likely cause: project not allowlisted for the preview model"
  fail "Action: visit https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/image-generation"
  fail "Workaround: use Imagen 4 (imagen-4.0-generate-001) at us-central1 — GA, no allowlist"
  exit 3
fi
ok "Model gemini-3-pro-image-preview is visible to project ${PROJECT}"

# ── 4. Real generation test ───────────────────────────────────
echo ""
echo "4. Smoke-test image generation (1K tier, 16:9)..."
REQ_FILE="${TMP_DIR}/smoke-request.json"
RES_FILE="${TMP_DIR}/smoke-response.json"
OUT_PNG="${TMP_DIR}/smoke-test.png"

cat > "${REQ_FILE}" <<'EOF'
{
  "contents": [{
    "role": "user",
    "parts": [{"text": "A small abstract icon: a single glowing diff line between two stylized monoliths. 16:9 minimalist composition, deep navy background. No text in image."}]
  }],
  "generationConfig": {
    "responseModalities": ["IMAGE"],
    "imageConfig": {"aspectRatio": "16:9"}
  }
}
EOF

GEN_URL="https://aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/global/publishers/google/models/gemini-3-pro-image-preview:generateContent"

HTTP_CODE="$(curl -s -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "x-goog-user-project: ${PROJECT}" \
  -H "Content-Type: application/json" \
  -d @"${REQ_FILE}" \
  -o "${RES_FILE}" \
  -w "%{http_code}" "${GEN_URL}")"

if [[ "${HTTP_CODE}" != "200" ]]; then
  fail "Generation call returned HTTP ${HTTP_CODE}"
  fail "Response: $(cat "${RES_FILE}" | head -c 400)"
  exit 4
fi

# Extract base64 image to PNG
python3 - "${RES_FILE}" "${OUT_PNG}" <<'PY'
import json, base64, sys
res, out = sys.argv[1], sys.argv[2]
d = json.load(open(res))
parts = d['candidates'][0]['content']['parts']
for p in parts:
    if 'inlineData' in p:
        with open(out, 'wb') as f:
            f.write(base64.b64decode(p['inlineData']['data']))
        usage = d.get('usageMetadata', {})
        print(f"  saved {out} (tokens={usage.get('totalTokenCount', '?')})")
        break
else:
    print("  no inlineData in response", file=sys.stderr)
    sys.exit(1)
PY

if [[ -f "${OUT_PNG}" ]]; then
  SIZE="$(wc -c < "${OUT_PNG}")"
  ok "Generated test PNG: ${OUT_PNG} (${SIZE} bytes)"
else
  fail "Output PNG was not produced"
  exit 5
fi

echo ""
echo -e "${GREEN}All checks passed.${RESET} Skill is ready to use."
echo ""
echo "Next: try generate.py with your own prompt:"
echo "  python3 scripts/generate.py \"your prompt here\" --project ${PROJECT} --out ${TMP_DIR}/hero.png"
