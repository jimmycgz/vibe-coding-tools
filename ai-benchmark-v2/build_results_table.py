#!/usr/bin/env python3
"""Builds the one results table, with plain arm labels, from the raw records.

usage: build_results_table.py RUN1_DIR [RUN2_DIR]

Each directory holds trials-*.jsonl and, for streamed runs, requests-*.jsonl. Raw records keep the ids they were recorded
with; arms.json maps them to the plain labels used everywhere else. One row per arm: pass counts per trial for each run
(10 claims per trial), mean cost per task by the notebook's formula over all trials listed, and, when a run streamed,
the median of each timing field over that arm's requests and the median wall seconds per claim.
"""
import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARMS = json.load(open(os.path.join(HERE, "arms.json"), encoding="utf-8"))["arms"]
BY_ID = {a["id"]: a for a in ARMS}
BY_RECORDED = {a["run1_id"]: a["id"] for a in ARMS if a.get("run1_id")}


def arm_id(recorded):
    return BY_RECORDED.get(recorded, recorded if recorded in BY_ID else None)


def load(folder):
    trials, requests = {}, {}
    for f in sorted(glob.glob(os.path.join(folder, "trials-*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                t = json.loads(line)
                trials.setdefault(arm_id(t["config"]), []).append(t)
    for f in sorted(glob.glob(os.path.join(folder, "requests-*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                if r.get("timing"):
                    requests.setdefault(arm_id(r["tag"].split()[0]), []).append(r["timing"])
    return trials, requests


def med(xs):
    xs = [x for x in xs if x is not None]
    return "%.2f" % statistics.median(xs) if xs else "n/a"


runs = [load(d) for d in sys.argv[1:]]
if not runs:
    sys.exit(__doc__)
head = ["Arm"] + ["Run %d trials" % (i + 1) for i in range(len(runs))] + ["$ per task"]
streamed = any(r[1] for r in runs)
if streamed:
    head += ["Wall s per claim (median)", "Wall s per request (median)", "First event s (median)",
             "First content s (median)", "First text s (median)"]
rows = [head, ["---"] * len(head)]
for a in ARMS:
    cells, all_trials = [a["label"]], []
    for trials, _ in runs:
        ts = sorted(trials.get(a["id"], []), key=lambda t: t["trial"])
        all_trials += ts
        cells.append(", ".join("%d/%d" % (t["correct"], t["n"]) for t in ts) or "not run")
    if not all_trials:
        continue
    cells.append("%.4f" % statistics.mean(t["per_task_notebook"] for t in all_trials))
    if streamed:
        reqs = [x for _, rq in runs for x in rq.get(a["id"], [])]
        walls = [w for t in all_trials for w in (t.get("claim_wall_s") or {}).values()]
        cells += [med(walls), med([x["wall_s"] for x in reqs]), med([x["ttfb_s"] for x in reqs]),
                  med([x["first_delta_s"] for x in reqs]), med([x["first_text_s"] for x in reqs])]
    rows.append(cells)
print("\n".join("| " + " | ".join(r) + " |" for r in rows))
