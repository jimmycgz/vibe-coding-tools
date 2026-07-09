#!/usr/bin/env python3
"""batch.py — Parallel Nano Banana Pro generation across many prompts.

Usage:
    batch.py prompts.json [--concurrency 3] [--out-dir DIR] [--project PROJECT_ID]

prompts.json schema:
    [
      {"name": "slide-01-titans",   "prompt": "...", "aspect": "16:9", "tier": "2k"},
      {"name": "slide-04-monoliths","prompt": "...", "aspect": "16:9", "tier": "2k"}
    ]

Each item produces <out-dir>/<name>.png. Failures are reported per-item;
batch continues even if some prompts fail.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import subprocess
import os
import ssl
import base64
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Honor system CA bundle for corporate proxies.
_CA_BUNDLE = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE")
if _CA_BUNDLE and Path(_CA_BUNDLE).exists():
    _SSL_CTX = ssl.create_default_context(cafile=_CA_BUNDLE)
else:
    _SSL_CTX = ssl.create_default_context()

MODEL = "gemini-3-pro-image-preview"
LOCATION = "global"


def get_adc_token() -> str:
    return subprocess.check_output(
        ["gcloud", "auth", "application-default", "print-access-token"]
    ).decode().strip()


def resolve_project(arg: str | None) -> str:
    if arg:
        return arg
    env = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
    if env:
        return env
    return subprocess.check_output(
        ["gcloud", "config", "get-value", "project"]
    ).decode().strip()


def generate_one(item: dict, project: str, token: str, out_dir: Path) -> dict:
    """Generate one image. Returns {'name', 'ok', 'path'|'error', 'tokens', 'sec'}."""
    name = item["name"]
    prompt = item["prompt"]
    aspect = item.get("aspect", "16:9")
    tier = item.get("tier", "1k")

    cfg = {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}
    if tier == "2k":
        cfg["imageConfig"]["imageSize"] = "2K"
    elif tier == "4k":
        cfg["imageConfig"]["imageSize"] = "4K"

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": cfg,
    }

    url = (
        f"https://aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{LOCATION}/publishers/google/models/{MODEL}:generateContent"
    )

    t0 = time.time()
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
        with urllib.request.urlopen(req, timeout=180, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"name": name, "ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:200]}", "sec": time.time() - t0}
    except (urllib.error.URLError, ssl.SSLError) as e:
        # Corporate-proxy SSL fallback to curl (uses system CA store).
        msg = str(getattr(e, 'reason', e))
        if 'CERTIFICATE_VERIFY_FAILED' in msg or 'self-signed' in msg.lower() or 'SSL' in msg:
            import tempfile
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
                json.dump(payload, f); body_path = f.name
            try:
                r = subprocess.run(
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
            body, _, status = r.stdout.rpartition("\n")
            if status.strip() != "200":
                return {"name": name, "ok": False, "error": f"curl HTTP {status.strip()}: {body[:200]}", "sec": time.time() - t0}
            data = json.loads(body)
        else:
            return {"name": name, "ok": False, "error": f"URL: {msg}", "sec": time.time() - t0}

    parts = data["candidates"][0]["content"]["parts"]
    for p in parts:
        if "inlineData" in p:
            png = base64.b64decode(p["inlineData"]["data"])
            out_path = out_dir / f"{name}.png"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(png)
            usage = data.get("usageMetadata", {})
            return {
                "name": name,
                "ok": True,
                "path": str(out_path),
                "tokens": usage.get("totalTokenCount", 0),
                "sec": time.time() - t0,
            }
    return {"name": name, "ok": False, "error": "no inlineData in response", "sec": time.time() - t0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", help="Path to prompts.json (list of {name, prompt, aspect?, tier?}).")
    ap.add_argument("--project", help="GCP project ID (defaults to GOOGLE_CLOUD_PROJECT or gcloud config).")
    ap.add_argument("--concurrency", type=int, default=3, help="Parallel workers. Default 3. API limits typically allow 5-10.")
    ap.add_argument("--out-dir", default="hero-images", help="Directory for output PNGs. NEVER /tmp.")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    if str(out_dir).startswith("/tmp/"):
        sys.exit("ERROR: refusing to write under /tmp/. Use <workspace>/tmp/ instead.")

    items = json.loads(Path(args.manifest).read_text())
    if not isinstance(items, list):
        sys.exit("ERROR: manifest must be a JSON list of {name, prompt, ...}")

    project = resolve_project(args.project)
    token = get_adc_token()

    print(f"Project:     {project}")
    print(f"Items:       {len(items)}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Output dir:  {out_dir}")
    print(f"Dispatching...\n")

    results = []
    total_tokens = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(generate_one, item, project, token, out_dir): item for item in items}
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            if r["ok"]:
                total_tokens += r.get("tokens", 0)
                print(f"  [OK]   {r['name']}  ({r['sec']:.1f}s, {r['tokens']} tok) -> {r['path']}")
            else:
                print(f"  [FAIL] {r['name']}  ({r['sec']:.1f}s)  {r['error']}")

    elapsed = time.time() - t0
    ok = sum(1 for r in results if r["ok"])
    print(f"\nDone in {elapsed:.1f}s.  {ok}/{len(items)} ok.  ~{total_tokens:,} total tokens.")
    if ok < len(items):
        sys.exit(1)


if __name__ == "__main__":
    main()
