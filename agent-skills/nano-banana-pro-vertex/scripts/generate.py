#!/usr/bin/env python3
"""generate.py — Single-shot Nano Banana Pro image generation via Vertex AI.

Usage:
    generate.py "your prompt here" \\
        [--project PROJECT_ID] \\
        [--aspect 16:9|9:16|1:1|4:3|3:4|21:9] \\
        [--tier 1k|2k|4k] \\
        [--out PATH]

Auth:
    Uses ADC (Application Default Credentials). Set up once with:
        gcloud auth application-default login
        gcloud auth application-default set-quota-project <PROJECT>

    API key auth is NOT supported by this script — Vertex AI's preview models
    require ADC. If the user insists on API key for some other Google AI surface,
    they should use the AI Studio Gemini API directly (different endpoint).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Honor system CA bundle for environments behind a corporate proxy (e.g. Palo Alto).
# REQUESTS_CA_BUNDLE / CURL_CA_BUNDLE are common env-var conventions.
_CA_BUNDLE = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE")
if _CA_BUNDLE and Path(_CA_BUNDLE).exists():
    _SSL_CTX = ssl.create_default_context(cafile=_CA_BUNDLE)
else:
    _SSL_CTX = ssl.create_default_context()

MODEL = "gemini-3-pro-image-preview"
LOCATION = "global"   # NOTE: NOT us-central1. Catalog metadata lies; REST 404s there.

ASPECT_CHOICES = ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "5:4", "4:5", "2:3", "3:2"]
TIER_TO_RES = {
    "1k": None,        # default ~1376x768 at 16:9
    "2k": "2K",
    "4k": "4K",
}


def get_adc_token() -> str:
    """Fetch ADC access token via gcloud."""
    try:
        out = subprocess.check_output(
            ["gcloud", "auth", "application-default", "print-access-token"],
            stderr=subprocess.PIPE,
        )
        return out.decode().strip()
    except FileNotFoundError:
        sys.exit("ERROR: gcloud CLI not found. Install: https://cloud.google.com/sdk/install")
    except subprocess.CalledProcessError as e:
        sys.exit(
            f"ERROR: ADC token fetch failed.\n"
            f"  stderr: {e.stderr.decode()[:300]}\n"
            f"  Fix: gcloud auth application-default login"
        )


def resolve_project(arg_project: str | None) -> str:
    if arg_project:
        return arg_project
    env = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
    if env:
        return env
    try:
        out = subprocess.check_output(
            ["gcloud", "config", "get-value", "project"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if out:
            return out
    except Exception:
        pass
    sys.exit("ERROR: no GCP project. Pass --project, set GOOGLE_CLOUD_PROJECT, or run gcloud config set project")


def build_payload(prompt: str, aspect: str, tier: str) -> dict:
    cfg = {
        "responseModalities": ["IMAGE"],   # CAREFUL: camelCase. snake_case (response_modalities) returns 400.
        "imageConfig": {"aspectRatio": aspect},
    }
    res = TIER_TO_RES.get(tier)
    if res:
        cfg["imageConfig"]["imageSize"] = res
    return {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": cfg,
    }


def _call_via_curl(url: str, project: str, payload: dict, token: str) -> dict:
    """Fallback when urllib SSL fails (e.g. corporate proxy with self-signed CA chain).
    curl picks up system CA store automatically on most environments.
    """
    import tempfile
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
        json.dump(payload, f)
        body_path = f.name
    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST",
             "-H", f"Authorization: Bearer {token}",
             "-H", f"x-goog-user-project: {project}",
             "-H", "Content-Type: application/json",
             "-d", f"@{body_path}",
             "-w", "\\n%{http_code}", url],
            capture_output=True, text=True, timeout=180,
        )
    finally:
        os.unlink(body_path)
    if result.returncode != 0:
        sys.exit(f"ERROR: curl fallback failed: {result.stderr[:300]}")
    body, _, status = result.stdout.rpartition("\n")
    status = status.strip()
    if status != "200":
        sys.exit(f"ERROR: curl fallback HTTP {status}: {body[:400]}")
    return json.loads(body)


def call_vertex(project: str, payload: dict, token: str) -> dict:
    url = (
        f"https://aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{LOCATION}/publishers/google/models/{MODEL}:generateContent"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-goog-user-project": project,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120, context=_SSL_CTX) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, ssl.SSLError) as e:
        # Corporate-proxy SSL failure → fall through to curl (uses system CA store).
        msg = str(getattr(e, 'reason', e))
        if 'CERTIFICATE_VERIFY_FAILED' in msg or 'self-signed' in msg.lower() or 'SSL' in msg:
            print(f"  (urllib SSL failed: {msg[:80]}. Falling back to curl...)", file=sys.stderr)
            return _call_via_curl(url, project, payload, token)
        sys.exit(f"ERROR: URL error: {msg}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        if e.code == 404:
            sys.exit(
                f"ERROR: HTTP 404. Likely cause: project '{project}' is NOT allowlisted for the\n"
                f"preview model {MODEL}. Apply for access at:\n"
                f"  https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/image-generation\n"
                f"Workaround: use Imagen 4 (imagen-4.0-generate-001) at us-central1 — GA, no allowlist.\n"
                f"Response body: {body}"
            )
        if e.code == 403:
            sys.exit(
                f"ERROR: HTTP 403. Likely cause: ADC quota project not set or wrong.\n"
                f"  Fix: gcloud auth application-default set-quota-project {project}\n"
                f"Response body: {body}"
            )
        sys.exit(f"ERROR: HTTP {e.code}: {body}")


def extract_image(response: dict, out_path: Path) -> tuple[int, dict]:
    """Save the inline image to out_path. Return (bytes_written, usage_metadata)."""
    parts = response["candidates"][0]["content"]["parts"]
    for p in parts:
        if "inlineData" in p:
            raw = base64.b64decode(p["inlineData"]["data"])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(raw)
            return len(raw), response.get("usageMetadata", {})
    sys.exit(f"ERROR: response had no inlineData. Body keys: {list(response.keys())}")


def main():
    ap = argparse.ArgumentParser(description="Generate one image via Nano Banana Pro on Vertex AI.")
    ap.add_argument("prompt", help="Text prompt for the image.")
    ap.add_argument("--project", help="GCP project ID (defaults to GOOGLE_CLOUD_PROJECT or gcloud config).")
    ap.add_argument("--aspect", default="16:9", choices=ASPECT_CHOICES, help="Aspect ratio. Default 16:9.")
    ap.add_argument("--tier", default="1k", choices=list(TIER_TO_RES.keys()),
                    help="Resolution tier. Iterate at 1k (cheap) and finalize at 4k. Default 1k.")
    ap.add_argument("--out", default="hero.png", help="Output PNG path. NEVER use /tmp; use <workspace>/tmp/.")
    args = ap.parse_args()

    project = resolve_project(args.project)
    token = get_adc_token()
    payload = build_payload(args.prompt, args.aspect, args.tier)

    out_path = Path(args.out)
    if str(out_path).startswith("/tmp/"):
        sys.exit(
            "ERROR: refusing to write to /tmp/.\n"
            "Use <workspace>/tmp/ instead — see project file-safety rules."
        )

    print(f"Project:      {project}")
    print(f"Model:        {MODEL} @ locations/{LOCATION}")
    print(f"Aspect:       {args.aspect}")
    print(f"Tier:         {args.tier}")
    print(f"Output:       {out_path}")
    print(f"Calling Vertex AI...")

    response = call_vertex(project, payload, token)
    nbytes, usage = extract_image(response, out_path)

    total_tokens = usage.get("totalTokenCount", "?")
    # Rough cost estimate based on tier
    cost_est = {"1k": 0.04, "2k": 0.08, "4k": 0.24}.get(args.tier, 0.0)
    print(f"Saved:        {out_path} ({nbytes:,} bytes)")
    print(f"Tokens used:  {total_tokens}")
    print(f"Est. cost:    ${cost_est:.2f}")


if __name__ == "__main__":
    main()
