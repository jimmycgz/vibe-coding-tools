#!/usr/bin/env python3
"""Extract genuine USER messages from Claude Code transcripts into analysis batches.

Transcripts (~/.claude/projects/**/*.jsonl) mix real user text with tool results,
command output, system reminders, and pasted blobs. Workers analyzing user behavior
need ONLY what the human actually typed. This extractor is deterministic so the
filtering never depends on an LLM's mood.

Output: batch-NN.jsonl files, each line {"session","project","ts","text"},
size-capped so one batch fits comfortably in one subagent context.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

# Markers that mean "not the human talking" when a message starts with them.
SKIP_PREFIXES = (
    "<local-command-stdout",
    "<command-name>",
    "<command-message>",
    "<task-notification>",
    "<system-reminder>",
    "Caveat: The messages below",
    "[Request interrupted",
)

SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
CAVEAT_RE = re.compile(r"<local-command-caveat>.*?</local-command-caveat>", re.DOTALL)

MAX_MSG_CHARS = 1500          # long pastes: keep head+tail, the middle is payload not preference
BATCH_BYTE_BUDGET = 90_000    # ~one comfortable subagent read per batch


def clean_text(text: str) -> str:
    text = SYSTEM_REMINDER_RE.sub("", text)
    text = CAVEAT_RE.sub("", text)
    text = text.strip()
    if len(text) > MAX_MSG_CHARS:
        head, tail = text[:1000], text[-300:]
        text = f"{head}\n[...{len(text) - 1300} chars of pasted content omitted...]\n{tail}"
    return text


def user_text_from_record(rec: dict) -> str | None:
    if rec.get("type") != "user":
        return None
    msg = rec.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        # keep only text blocks; tool_result blocks are machine payloads
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    else:
        return None
    text = "\n".join(p for p in parts if p).strip()
    if not text:
        return None
    if text.startswith(SKIP_PREFIXES):
        return None
    text = clean_text(text)
    # after cleaning, drop shells of removed markup or trivial acks
    if len(text) < 2:
        return None
    return text


def iter_transcripts(projects_dir: Path, min_mtime: float):
    for path in projects_dir.rglob("*.jsonl"):
        # memory dirs and subagent transcripts add noise; user intent lives in top-level session files
        rel = path.relative_to(projects_dir).as_posix()
        if "/memory/" in rel or "/subagents/" in rel or "/tasks/" in rel:
            continue
        try:
            if path.stat().st_mtime < min_mtime:
                continue
        except OSError:
            continue
        yield path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--projects-dir", default=str(Path.home() / ".claude" / "projects"))
    ap.add_argument("--days", type=int, default=30, help="only sessions modified in the last N days")
    ap.add_argument("--max-sessions", type=int, default=0, help="0 = no cap")
    ap.add_argument("--out", required=True, help="output directory for batch files")
    args = ap.parse_args()

    projects_dir = Path(args.projects_dir).expanduser()
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    min_mtime = time.time() - args.days * 86400

    paths = sorted(iter_transcripts(projects_dir, min_mtime),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if args.max_sessions:
        paths = paths[: args.max_sessions]

    batch_idx, batch_bytes, batch_fh = 1, 0, None
    sessions_used = messages = 0

    def open_batch(i: int):
        return (out_dir / f"batch-{i:02d}.jsonl").open("w", encoding="utf-8")

    batch_fh = open_batch(batch_idx)
    for path in paths:
        session_id = path.stem
        project = path.parent.name
        wrote_any = False
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    text = user_text_from_record(rec)
                    if text is None:
                        continue
                    row = json.dumps(
                        {"session": session_id, "project": project,
                         "ts": rec.get("timestamp", ""), "text": text},
                        ensure_ascii=False)
                    if batch_bytes + len(row) > BATCH_BYTE_BUDGET and batch_bytes > 0:
                        batch_fh.close()
                        batch_idx += 1
                        batch_bytes = 0
                        batch_fh = open_batch(batch_idx)
                    batch_fh.write(row + "\n")
                    batch_bytes += len(row) + 1
                    messages += 1
                    wrote_any = True
        except OSError as e:
            print(f"warn: skipped {path}: {e}", file=sys.stderr)
        if wrote_any:
            sessions_used += 1

    batch_fh.close()
    # drop a possibly-empty last batch file
    last = out_dir / f"batch-{batch_idx:02d}.jsonl"
    if last.exists() and last.stat().st_size == 0:
        last.unlink()
        batch_idx -= 1

    print(json.dumps({"sessions": sessions_used, "messages": messages,
                      "batches": batch_idx, "out": str(out_dir)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
