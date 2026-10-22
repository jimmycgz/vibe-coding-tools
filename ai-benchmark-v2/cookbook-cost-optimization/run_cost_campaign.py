#!/usr/bin/env python3
"""Campaign 2: the cookbook's insurance-claims eval as a plain script (stdlib only, raw HTTPS).

Re-implements, from the notebook cost_optimization.ipynb (anthropics/claude-cookbooks a162e01, notebook
sha256 6b5955d79331c70a...), the parts the comparison needs: the adjudicate() loop (cell 15), adjudicate_cm()
(cell 69), the decomposed subagent route (cells 46, 62), the batch one-shot route (cell 73), usage_cost()
(cell 7), the system prompts, tools and rule card. Demonstration-only cells (17-55 except the ones above) are
not reproduced. Nothing is imported from the cookbook repo; its data files were copied into ./assets
(hashes in assets/SOURCE-SHA256.txt).

usage:
  run_c2.py --dry-run [--configs B0,L5,V1] [--claims CLM-001,...] [--dump FILE]
      prints every first-turn request body (key shown as <REDACTED>) and the request count; no network,
      no key read. Later turns of a tool loop depend on the model's replies and cannot be printed in advance.
  run_c2.py --estimate [--trials N] [--configs ...]
      prints the cost arithmetic from the notebook's saved per-task costs; no network.
  run_c2.py --live --ceiling-usd X --trials N --out DIR [--configs ...]
      the paid run. Refuses without both --live and --ceiling-usd. Not run by the preparing worker.

Two cost columns are recorded for every request: notebook_cost (usage_cost() exactly as the notebook wrote it:
cache write 1.25x / 2x, cache read 0.10x, batch 0.5x) and list_cost (same, but the cache-read multiplier is the
model's own list rate from models-c2.json, e.g. 0.05x on claude-opus-5-5).
"""
import argparse
import copy
import csv
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
API = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
LIVE = {"armed": False}  # set only by main() after every live-mode check passes

# ---------------------------------------------------------------- data (notebook cell 10, 13)


def _read_csv(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


CLAIMS = {r["id"]: r for r in _read_csv("claims.csv")}
PARTS = _read_csv("repair_parts.csv")
PHOTOS = {}
for _r in _read_csv("damage_photos.csv"):
    PHOTOS.setdefault(_r["claim_id"], []).append(_r)
PRIORS = {}
for _r in _read_csv("prior_claims.csv"):
    PRIORS.setdefault(_r["policyholder_id"], []).append(
        {k: _r[k] for k in ("prior_ref", "loss_date", "type", "amount_usd", "shop", "flagged")})
EVAL_CLAIMS = _read_csv("eval_set.csv")
with open(os.path.join(ASSETS, "policy_manual.txt"), encoding="utf-8") as _f:
    POLICY_MANUAL = _f.read()

_CLAIM_COLS = ("id", "policyholder_id", "loss_date", "reported_date", "loss_state", "description",
               "other_parties", "estimate_usd")
_POLICY_COLS = ("policyholder_id", "collision", "comprehensive", "deductible_usd", "status", "inception_date",
                "exclusions", "excluded_drivers")
_HIST_COLS = ("policyholder_id", "prior_claims_12mo", "prior_claims_5yr", "tenure_years", "on_watch_list")
_FRAUD_COLS = ("siu_score", "indicators", "fraud_note")


def _slice(cid, cols):
    return json.dumps({k: CLAIMS.get(cid, {}).get(k, "") for k in cols})


def _estimate_text(cid):
    c = CLAIMS.get(cid, {})
    total = float(c.get("estimate_usd", 0))
    areas = set((c.get("damage_area") or "front").split(";"))
    parts = [p for p in PARTS if p["area"] in areas and (c.get("severity") == "major" or p["tier"] == "1")] or PARTS
    hrs = [float(p["labor_hrs"]) for p in parts]
    rows, remaining = [], total
    for i, (p, h) in enumerate(zip(parts, hrs, strict=True), 1):
        amt = round(total * h / sum(hrs), 2) if i < len(parts) else round(remaining, 2)
        remaining -= amt
        rows.append(f"{i:02d}  {p['part']:22s}  R&R   labor {p['labor_hrs']}h "
                    f"@ ${p['rate_per_hr']}/hr   part OEM #{p['oem_no']}   ${amt:>9,.2f}")
    return (f"CERTIFIED COLLISION CENTER — ESTIMATE OF RECORD\n"
            f"Claim {cid} · prepared {CLAIMS.get(cid, {}).get('reported_date', '')}\n\n"
            + "\n".join(rows)
            + f"\n\nSUBTOTAL PARTS+LABOR ${total:,.2f}\n"
            "Notes: OEM where available; supplements pending teardown; "
            "photos on file; labor rates per §3.4 regional caps.")


def _photo_metadata(cid):
    return "\n".join(f"IMG_{cid[-3:]}_{r['seq']:>02s}.jpg  3024x4032  {r['timestamp']}  appraiser: {r['note']}"
                     for r in PHOTOS.get(cid, []))


def _manual_section(query):
    q = str(query).lower().replace("section", "").strip(" .:#")
    lines = POLICY_MANUAL.split("\n")
    heads = [(i, len(ln) - len(ln.lstrip("#")), ln.lstrip("# ").removeprefix("Section "))
             for i, ln in enumerate(lines) if ln.startswith(("## ", "### "))]
    for k, (i, level, head) in enumerate(heads):
        num, title = head.replace(":", "").split(" ", 1)
        if q and (q == num or q in title.lower()):
            end = next((j for j, lv, _ in heads[k + 1:] if lv <= level), len(lines))
            return "\n".join(lines[i:end])
    return "No matching section. Contents:\n" + "\n".join(h for _, lv, h in heads if lv == 2)


TERMINAL = {"approve_claim": "APPROVE", "deny_claim": "DENY", "route_to_supervisor": "SUPERVISOR",
            "refer_to_siu": "FRAUD"}


def execute_tool(name, args):
    cid = args.get("claim_id", "")
    ph = args.get("policyholder_id", "")
    if ph and not cid:
        cid = next((k for k, v in CLAIMS.items() if v["policyholder_id"] == ph), "")
    if name in TERMINAL:
        return json.dumps({"recorded": name, **args})
    if name == "get_claim":
        return _slice(cid, _CLAIM_COLS)
    if name == "get_policy":
        return _slice(cid, _POLICY_COLS)
    if name == "get_customer_history":
        hist = {k: CLAIMS.get(cid, {}).get(k, "") for k in _HIST_COLS}
        hist["prior_claims"] = PRIORS.get(hist.get("policyholder_id", ""), [])
        return json.dumps(hist)
    if name == "check_fraud_signals":
        return _slice(cid, _FRAUD_COLS)
    if name == "lookup_repair_estimate":
        doc = os.path.join(ASSETS, "estimates", f"{cid}.txt")
        if os.path.exists(doc):
            with open(doc, encoding="utf-8") as f:
                return f.read()
        return _estimate_text(cid)
    if name == "get_damage_photos":
        return _photo_metadata(cid) or "No photos on file."
    if name == "read_manual":
        return _manual_section(args.get("section", ""))
    if name == "calculate_payout":
        c = CLAIMS.get(cid, {})
        est, ded = float(c.get("estimate_usd", 0)), float(c.get("deductible_usd", 0))
        return json.dumps({"claim_id": cid, "estimate": est, "deductible": ded, "payout": max(est - ded, 0)})
    return json.dumps({"tool": name, "args": args, "result": "ok"})


# ---------------------------------------------------------------- prompts and tools (cells 11, 27, 31, 38, 62, 69)

SYSTEM_PROMPT = (
    "You are a Senior Adjuster in Acme Insurance's auto claims unit; your payment "
    "and denial authority is set out in Section 6 of the underwriting manual below. "
    "Standard investigation on every claim: retrieve the claim record, the policy, "
    "the policyholder's claim history, and the SIU fraud-indicator score before "
    "deciding; pull the estimate, photos, or additional documents only when the "
    "decision turns on them. Adjudicate strictly per the manual: decide claims within "
    "your authority yourself, and escalate only where the manual requires it: "
    "`route_to_supervisor` for the supervisor review or higher-authority approval the "
    "manual specifies, `refer_to_siu` for the manual's mandatory SIU referrals. Conclude "
    "every adjudication by calling exactly one of `approve_claim`, `deny_claim`, "
    "`route_to_supervisor`, or `refer_to_siu`.\n\n"
    "=== UNDERWRITING MANUAL ===\n"
    f"{POLICY_MANUAL}\n"
    "=== END MANUAL ==="
)

SYSTEM_LEAN = (
    "You are a Senior Adjuster in Acme Insurance's auto claims unit; your payment "
    "and denial authority is set out in Section 6 of the underwriting manual, which "
    "you can consult via `read_manual` when you need a specific rule. "
    "Standard investigation on every claim: retrieve the claim record, the policy, "
    "the policyholder's claim history, and the SIU fraud-indicator score before "
    "deciding; pull the estimate, photos, or additional documents only when the "
    "decision turns on them. Adjudicate strictly per the manual: decide claims within "
    "your authority yourself, and escalate only where the manual requires it: "
    "`route_to_supervisor` for the supervisor review or higher-authority approval the "
    "manual specifies, `refer_to_siu` for the manual's mandatory SIU referrals. Conclude "
    "every adjudication by calling exactly one of `approve_claim`, `deny_claim`, "
    "`route_to_supervisor`, or `refer_to_siu`."
)


def _tool(name, description, params):
    return {"name": name, "description": description,
            "input_schema": {"type": "object",
                             "properties": {k: {"type": "string", "description": v} for k, v in params.items()},
                             "required": list(params)}}


TOOLS = [
    _tool("get_claim", "Retrieve the full claim record.", {"claim_id": "Claim ID, e.g. CLM-001"}),
    _tool("get_policy", "Retrieve the policy bound to a claim.", {"claim_id": "Claim ID"}),
    _tool("get_customer_history", "List the policyholder's prior claims.", {"policyholder_id": "Policyholder ID"}),
    _tool("lookup_repair_estimate", "Get the itemized repair estimate for a claim.", {"claim_id": "Claim ID"}),
    _tool("check_fraud_signals", "Run SIU fraud-indicator scoring on a claim.", {"claim_id": "Claim ID"}),
    _tool("get_damage_photos", "Retrieve damage-photo metadata for a claim.", {"claim_id": "Claim ID"}),
    _tool("calculate_payout", "Compute payout after deductible and depreciation.", {"claim_id": "Claim ID"}),
    _tool("request_docs", "Request additional documentation from the insured.",
          {"claim_id": "Claim ID", "docs": "Comma-separated doc types"}),
    _tool("approve_claim", "Record an APPROVE decision.", {"claim_id": "Claim ID", "amount": "Payout in USD"}),
    _tool("deny_claim", "Record a DENY decision with an exclusion code.", {"claim_id": "Claim ID", "code": "Exclusion code"}),
    _tool("route_to_supervisor",
          "Send the claim up for the supervisor review or higher-authority approval the manual "
          "requires (fraud-indicator score in the 3-5 band; payment above your authority).",
          {"claim_id": "Claim ID", "reason": "Why"}),
    _tool("refer_to_siu",
          "File the mandatory referral to the fraud unit (SIU, form SIU-REF-1) when the manual requires it: "
          "fraud-indicator score of 6 or higher, or any Section 5.2 mandatory trigger.",
          {"claim_id": "Claim ID", "reason": "Why"}),
]
READ_MANUAL = _tool("read_manual", "Look up a section of the underwriting manual.",
                    {"section": "Section number or heading, e.g. '4.2' or 'Exclusions'"})
TOOL_SEARCH = {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"}
ALWAYS_ON = {"get_claim", "approve_claim", "deny_claim", "route_to_supervisor", "refer_to_siu"}
DEFERRED = [TOOL_SEARCH] + [({**t, "defer_loading": True} if t["name"] not in ALWAYS_ON else t) for t in TOOLS]
CODE_EXEC = {"type": "code_execution_20260120", "name": "code_execution"}
CE_EDITS = [{"type": "clear_thinking_20251015"}, {"type": "clear_tool_uses_20250919"}]
PRECEDENTS = _tool("search_precedents", "Return the historical claims ledger for the given state and loss type.",
                   {"state": "Loss state", "type": "Loss type"})
TERMINAL_TOOLS = [t for t in TOOLS if t["name"] in TERMINAL]

RULE_CARD = """You are a Senior Adjuster deciding auto claims from findings gathered by junior staff. \
Decision rules, condensed from the underwriting manual:
- DENY when a listed exclusion applies: EXCL-01 intentional act, 02 racing, 03 unlicensed or excluded driver, \
04 wear and tear or mechanical breakdown, 05 commercial use without endorsement, 06 DUI, 07 lapsed policy, \
08 non-permissive use, 10 unscheduled custom equipment over $1,000, 11 first-party diminished value, 12 misrepresentation.
- The FNOL fraud score is a snapshot; re-score it at estimate review from the facts. Rubric points: loss reported \
more than 30 days after occurrence without documented reason 2; policy incepted or coverage increased 30 days or \
less before loss 3; 3 or more prior claims in 36 months 2; damage inconsistent with described facts 3; no police \
report on theft, vandalism, or hit-and-run 2; pushes for quick cash or refuses inspection 2; vehicle purchased 60 \
days or less before total-loss theft or fire 3; all damage pre-existing 4; evasive or contradictory statement 2; \
medical treatment disproportionate to impact 2; same shop, clinic, or attorney in 3 or more flagged claims in 12 \
months 3; altered documents 4; financial distress 1; VIN inconsistencies 4.
- refer_to_siu when the re-scored total is 6 or higher, or on any mandatory trigger regardless of score: theft or \
fire total loss over $25,000; an intentional-act or fraud denial is contemplated; staged-accident pattern match; \
owner give-up indicators; any involved party on the internal watch list.
- route_to_supervisor when the re-scored total is 3 to 5, or gross indemnity exceeds Senior Adjuster authority \
($50,000, halved while a score of 3 or more is open).
- Otherwise approve_claim.
Take exactly one action via the tools provided."""

SUBAGENT_SYSTEM = ("You are a claims sub-adjuster. Use the tools to gather what "
                   "you need, then answer the task in one terse line.")
SUBAGENT_TASKS = [
    ("Report the loss date, reported date, loss description, and any other parties involved.", {"get_claim"}),
    ("Report coverage in force, policy status, inception date, exclusion codes, and excluded drivers.", {"get_policy"}),
    ("Report watch-list status and list every prior claim with its date and type.",
     {"get_claim", "get_customer_history"}),
    ("Report the fraud score, listed indicators, and any note on the fraud record verbatim.", {"check_fraud_signals"}),
    ("Report the repair estimate total and the payout after deductible.", {"lookup_repair_estimate", "calculate_payout"}),
]
STANDARD = ["get_claim", "get_policy", "get_customer_history", "check_fraud_signals"]
SUPPLEMENTARY = ["lookup_repair_estimate", "calculate_payout", "get_damage_photos"]

# ---------------------------------------------------------------- the grid (labels as in the notebook)
# saved: the notebook's own saved per-trial $/task and requests (cells 15, 57, 60, 62, 69, 73); used by --estimate only.

CONFIGS = [
    dict(id="O0", old_id="B0", label="opus · high · cold (baseline)", kind="loop", role="opus", effort="high", cache=False,
         cell=15, tier="core", saved=[(0.2906, 36)]),
    dict(id="O1", old_id="L1", label="opus · effort=high", kind="loop", role="opus", effort="high", cache=True, cell=57,
         tier="core", saved=[(0.1498, 34), (0.1512, 35)]),
    dict(id="O2", old_id="L2", label="opus · effort=medium", kind="loop", role="opus", effort="medium", cache=True, cell=57,
         tier="core", saved=[(0.1367, 34), (0.1370, 34)]),
    dict(id="O3", old_id="L3", label="opus · effort=low", kind="loop", role="opus", effort="low", cache=True, cell=57,
         tier="core", saved=[(0.1206, 33), (0.1205, 33)]),
    dict(id="S1", old_id="L4", label="sonnet · effort=high", kind="loop", role="sonnet", effort="high", cache=True, cell=57,
         tier="core", saved=[(0.0526, 33), (0.0548, 32)]),
    dict(id="S2", old_id="L5", label="sonnet · effort=medium", kind="loop", role="sonnet", effort="medium", cache=True, cell=57,
         tier="core", saved=[(0.0500, 32), (0.0494, 33)]),
    dict(id="S3", old_id="L6", label="sonnet · effort=low", kind="loop", role="sonnet", effort="low", cache=True, cell=57,
         tier="core", saved=[(0.0484, 32), (0.0519, 33)]),
    dict(id="L7", label="haiku", kind="loop", role="haiku", effort=None, cache=True, cell=57, tier="core",
         saved=[(0.0200, 30), (0.0189, 29)]),
    # F0, F1: Fable arms, not in the notebook's grid.
    # Their "saved" values are NOT the notebook's: they are B0 and L1 scaled by the price ratio Fable 5.1 ($10/$50)
    # to claude-opus-5 ($5/$25) = 2, assuming equal token counts. Used by --estimate only.
    dict(id="F0", label="fable · high · cold", kind="loop", role="fable", effort="high", cache=False,
         cell=15, tier="fable", saved=[(0.5812, 36)]),
    dict(id="F1", label="fable · effort=high", kind="loop", role="fable", effort="high", cache=True, cell=57,
         tier="fable", saved=[(0.3024, 35)]),
    # Run 2 arms: S0 is Sonnet high cold, F2 and F3 are Fable medium and
    # low with auto cache. Their "saved" values are estimates from run 1 (cold/cached ratio 2.02 on Opus; Fable cached
    # x effort ratio of the Opus rows), not the notebook's. Used by --estimate only.
    dict(id="S0", label="sonnet · high · cold", kind="loop", role="sonnet", effort="high", cache=False,
         cell=15, tier="run2", saved=[(0.0983, 33)]),
    dict(id="F2", label="fable · effort=medium", kind="loop", role="fable", effort="medium", cache=True, cell=57,
         tier="run2", saved=[(0.2710, 34)]),
    dict(id="F3", label="fable · effort=low", kind="loop", role="fable", effort="low", cache=True, cell=57,
         tier="run2", saved=[(0.2650, 33)]),
    dict(id="S2b", old_id="V1", label="  + explicit system breakpoint", kind="loop", role="sonnet", effort="medium", cache=True,
         cache_system=True, cell=69, tier="core", saved=[(0.0223, 33), (0.0228, 33)]),
    dict(id="S2m", old_id="V2", label="  + manual → read_manual tool", kind="loop", role="sonnet", effort="medium", cache=True,
         system="lean", tools="read_manual", cell=69, tier="extended", saved=[(0.0207, 39), (0.0210, 37)]),
    dict(id="S2t", old_id="V3", label="  + tool search deferral", kind="loop", role="sonnet", effort="medium", cache=True,
         tools="deferred", cell=69, tier="extended", saved=[(0.0543, 30), (0.0537, 30)]),
    dict(id="S2x", old_id="V4", label="  + code execution tool", kind="loop", role="sonnet", effort="medium", cache=True,
         tools="code_exec", cell=69, tier="extended", saved=[(0.0589, 32), (0.0581, 33)]),
    dict(id="S2e", old_id="V5", label="  + context editing", kind="loop_cm", role="sonnet", effort="medium",
         betas=["context-management-2025-06-27"], edits=CE_EDITS, cell=69, tier="extended",
         saved=[(0.0500, 33), (0.0497, 33)]),
    dict(id="S2k", old_id="V6", label="  + compaction", kind="loop_cm", role="sonnet", effort="medium",
         betas=["context-management-2025-06-27", "compact-2026-01-12"], edits=[{"type": "compact_20260112"}],
         cell=69, tier="extended", saved=[(0.0505, 33), (0.0502, 32)]),
    dict(id="S3a", old_id="A1", label="sonnet · low + opus advisor", kind="loop", role="sonnet", effort="low", cache=True,
         tools="advisor", betas=["advisor-tool-2026-03-01"], cell=60, tier="extended",
         saved=[(0.0754, 34), (0.0498, 31)]),
    dict(id="A2", label="haiku + opus advisor", kind="loop", role="haiku", effort=None, cache=True, tools="advisor",
         betas=["advisor-tool-2026-03-01"], cell=60, tier="extended", saved=[(0.1266, 32), (0.0952, 34)]),
    dict(id="D1", label="haiku subagents + sonnet decide", kind="decomposed", cell=62, tier="extended",
         saved=[(0.0188, 120), (0.0187, 120)]),
    dict(id="S2p", old_id="X1", label="sonnet · medium · batch (one-shot)", kind="batch_oneshot", cell=73, tier="extended",
         saved=[(0.0060, 10), (0.0194, 10)]),
]

# ---------------------------------------------------------------- models and cost


def load_models(path):
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    for role, mid in m["roles"].items():
        if mid not in m["prices"]:
            raise SystemExit("models file: no price for %s (role %s)" % (mid, role))
    return m


def usage_cost(usage, model, models, batch=False, read_mult=None):
    """notebook cell 7, on the raw usage dict. read_mult None = the notebook's 0.10; else the given multiplier."""
    p = models["prices"][model]
    m = 1_000_000
    cc = usage.get("cache_creation") or {}
    w5m = cc.get("ephemeral_5m_input_tokens", 0) or 0
    w1h = cc.get("ephemeral_1h_input_tokens", 0) or 0
    if not (w5m or w1h):
        w5m = usage.get("cache_creation_input_tokens") or 0
    rm = 0.10 if read_mult is None else read_mult
    cost = ((usage.get("input_tokens") or 0) * p["in"] / m
            + w5m * p["in"] * 1.25 / m
            + w1h * p["in"] * 2.00 / m
            + (usage.get("cache_read_input_tokens") or 0) * p["in"] * rm / m
            + (usage.get("output_tokens") or 0) * p["out"] / m)
    for it in usage.get("iterations") or []:  # advisor iterations bill at the advisor model's rate
        if it.get("type") == "advisor_message":
            it_mult = None if read_mult is None else models["prices"][it["model"]]["list_cache_read_mult"]
            cost += usage_cost(it, it["model"], models, read_mult=it_mult)
    return cost * (0.5 if batch else 1.0)


def both_costs(usage, model, models, batch=False):
    return (usage_cost(usage, model, models, batch),
            usage_cost(usage, model, models, batch, read_mult=models["prices"][model]["list_cache_read_mult"]))


# ---------------------------------------------------------------- request builders


def loop_body(cfg, claim, models, nonce, messages):
    """The body adjudicate() sends (cell 15), or adjudicate_cm() (cell 69) for kind loop_cm."""
    roles = models["roles"]
    model = roles[cfg["role"]]
    if cfg["kind"] == "loop_cm":
        return {"model": model, "max_tokens": 4096, "system": f"[trial {nonce}]\n\n{SYSTEM_PROMPT}", "tools": TOOLS,
                "messages": messages, "cache_control": {"type": "ephemeral"}, "thinking": {"type": "adaptive"},
                "output_config": {"effort": "medium"}, "context_management": {"edits": cfg["edits"]}}
    base = SYSTEM_LEAN if cfg.get("system") == "lean" else SYSTEM_PROMPT
    system = f"[trial {nonce}]\n\n" + base
    if cfg.get("cache_system"):
        system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    tools = {None: TOOLS, "read_manual": TOOLS + [READ_MANUAL], "deferred": DEFERRED, "code_exec": TOOLS + [CODE_EXEC],
             "advisor": TOOLS + [{"type": "advisor_20260301", "name": "advisor", "model": roles["opus"]}]}[cfg.get("tools")]
    body = {"model": model, "max_tokens": 4096, "system": system, "tools": tools, "messages": messages}
    if cfg["role"] != "haiku":  # notebook: Haiku takes neither thinking nor effort
        body["thinking"] = {"type": "adaptive"}
        body["output_config"] = {"effort": cfg["effort"]}
    if cfg.get("cache"):
        body["cache_control"] = {"type": "ephemeral"}
    return body


def first_messages(claim):
    return [{"role": "user", "content": f"Adjudicate claim {claim['id']}: {claim['summary']}"}]


def subagent_body(models, task, tool_names, messages):
    sub_tools = [t for t in TOOLS + [PRECEDENTS] if t["name"] in tool_names]
    return {"model": models["roles"]["haiku"], "max_tokens": 512, "system": SUBAGENT_SYSTEM, "tools": sub_tools,
            "messages": messages}


def decide_body(models, claim, facts):
    return {"model": models["roles"]["sonnet"], "max_tokens": 2048, "thinking": {"type": "adaptive"},
            "output_config": {"effort": "medium"}, "system": RULE_CARD, "tools": TERMINAL_TOOLS,
            "messages": [{"role": "user", "content": f"Claim {claim['id']}: {claim['summary']}\n\nFindings:\n"
                          + "\n".join(facts)}]}


def casefile(c):
    def fetch(names):
        return "\n".join(f"{n}: {execute_tool(n, {'claim_id': c['id']})}" for n in names)
    return (f"Adjudicate claim {c['id']}: {c['summary']}\n\n"
            f"Case file, standard investigation (pre-fetched):\n{fetch(STANDARD)}\n\n"
            f"Supplementary records:\n{fetch(SUPPLEMENTARY)}\n\n"
            "The case file above is complete and there is no way to request more records. "
            "Review the claim record, the policy, the claim history, and the fraud-indicator "
            "score in that order, as the standard investigation requires, then decide per the "
            "manual by calling exactly one terminal tool.")


def batch_body(models, claims, nonce):
    return {"requests": [{"custom_id": c["id"], "params": {
        "model": models["roles"]["sonnet"], "max_tokens": 16_000, "thinking": {"type": "adaptive"},
        "output_config": {"effort": "medium"},
        "system": [{"type": "text", "text": f"[trial {nonce}]\n\n{SYSTEM_PROMPT}", "cache_control": {"type": "ephemeral"}}],
        "tools": TERMINAL_TOOLS, "messages": [{"role": "user", "content": casefile(c)}]}} for c in claims]}


def headers(betas=None, key=None):
    h = {"content-type": "application/json", "anthropic-version": ANTHROPIC_VERSION,
         "x-api-key": key if key else "<REDACTED>"}
    if betas:
        h["anthropic-beta"] = ",".join(betas)
    return h


# ---------------------------------------------------------------- dry run


def _elide(obj, limit):
    if isinstance(obj, str):
        if len(obj) <= limit:
            return obj
        return "<%d chars, sha256 %s, starts %r>" % (len(obj), hashlib.sha256(obj.encode()).hexdigest()[:16], obj[:60])
    if isinstance(obj, list):
        return [_elide(x, limit) for x in obj]
    if isinstance(obj, dict):
        return {k: _elide(v, limit) for k, v in obj.items()}
    return obj


def dry_run(cfgs, claims, models, dump_path, show_limit):
    nonce = 0  # live runs use time.time_ns() per trial, as the notebook does; the dry run shows 0
    printed, records = 0, []

    def show(cfg, claim_id, what, method, url, hdrs, body):
        nonlocal printed
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        printed += 1
        print("#%d  %s  %s  %s" % (printed, cfg["id"], claim_id, what))
        print("  %s %s" % (method, url))
        print("  headers " + json.dumps(hdrs))
        print("  body bytes %d sha256 %s" % (len(raw), hashlib.sha256(raw).hexdigest()))
        print("  body " + json.dumps(_elide(body, show_limit), ensure_ascii=False))
        records.append({"n": printed, "config": cfg["id"], "claim": claim_id, "what": what, "method": method,
                        "url": url, "headers": hdrs, "body": body})

    for cfg in cfgs:
        if cfg["kind"] in ("loop", "loop_cm"):
            for c in claims:
                body = loop_body(cfg, c, models, nonce, first_messages(c))
                show(cfg, c["id"], "turn 1 of up to 6", "POST", API + "/messages", headers(cfg.get("betas")), body)
        elif cfg["kind"] == "decomposed":
            for c in claims:
                for k, (task, tools) in enumerate(SUBAGENT_TASKS, 1):
                    body = subagent_body(models, task, tools, [{"role": "user", "content": f"Claim {c['id']}: {task}"}])
                    show(cfg, c["id"], "subagent %d turn 1 of up to 3" % k, "POST", API + "/messages", headers(), body)
                print("  (the decide call for %s depends on the five subagent replies and is not printable in advance)" % c["id"])
        elif cfg["kind"] == "batch_oneshot":
            show(cfg, "ALL", "batch create (%d requests)" % len(claims), "POST", API + "/messages/batches", headers(),
                 batch_body(models, claims, nonce))
    if dump_path:
        os.makedirs(os.path.dirname(dump_path), exist_ok=True)
        with open(dump_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("full bodies written to", dump_path)
    expected = sum(sum(s[1] for s in cfg["saved"]) / len(cfg["saved"]) for cfg in cfgs)
    print("printed request bodies: %d (first turns only; no network call was made and no key was read)" % printed)
    print("configs: %d; claims: %d; expected API requests per trial of all printed configs, from the notebook's saved"
          " 'requests' column: %.1f" % (len(cfgs), len(claims), expected))
    return printed


# ---------------------------------------------------------------- estimate (no network)


def estimate(cfgs, trials):
    print("Upper bound from the notebook's saved per-task costs: for each config, the HIGHER of its saved trials'"
          " $/task, x 10 claims x %d trials." % trials)
    total = 0.0
    by_tier = {}
    for cfg in cfgs:
        hi = max(s[0] for s in cfg["saved"])
        mean = sum(s[0] for s in cfg["saved"]) / len(cfg["saved"])
        cost = hi * 10 * trials
        total += cost
        by_tier[cfg["tier"]] = by_tier.get(cfg["tier"], 0) + cost
        print("  %-3s %-36s saved $/task %s  mean %.4f  max %.4f  -> %.4f x 10 x %d = $%.2f" % (
            cfg["id"], cfg["label"].strip(), "/".join("%.4f" % s[0] for s in cfg["saved"]), mean, hi, hi, trials, cost))
    for t, v in by_tier.items():
        print("  tier %-8s $%.2f" % (t, v))
    print("  TOTAL $%.2f" % total)
    return total


# ---------------------------------------------------------------- live (never reached in --dry-run or --estimate)


def load_key():
    """The API key comes from the environment and from nowhere else: ANTHROPIC_API_KEY, and ANTHROPIC_WORKSPACE_ID
    when the key is not scoped to a workspace. Nothing is read from a file and nothing is printed."""
    out = {}
    if os.environ.get("ANTHROPIC_API_KEY"):
        out["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
    if os.environ.get("ANTHROPIC_WORKSPACE_ID"):
        out["ANTHROPIC_WORKSPACE_ID"] = os.environ["ANTHROPIC_WORKSPACE_ID"]
    if "ANTHROPIC_API_KEY" not in out:
        raise SystemExit("set ANTHROPIC_API_KEY in the environment (and ANTHROPIC_WORKSPACE_ID if your key needs it)")
    return out


def http(method, url, hdrs, body=None, timeout=900):
    if not LIVE["armed"]:
        raise RuntimeError("network path reached while not armed; refusing")
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    # Added 2026-10-22 16:4x EDT after the first live call died on a TLS "bad record mac" at turn 3 of the smoke run:
    # transient network errors and 429/5xx/529 are retried up to 4 times with a growing pause. A request whose reply
    # was lost on the wire may still have been billed; that spend is not seen by the guard, and the count of such
    # retries is printed to stderr so the report can state it.
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 529) and attempt < 4:
                print("RETRY %d: HTTP %s" % (attempt + 1, e.code), file=sys.stderr)
                time.sleep(5 * (attempt + 1))
                continue
            return e.code, dict(e.headers), body_txt
        except (urllib.error.URLError, ssl.SSLError, ConnectionError, TimeoutError, OSError) as e:
            if attempt < 4:
                print("RETRY %d: %s" % (attempt + 1, type(e).__name__), file=sys.stderr)
                time.sleep(5 * (attempt + 1))
                continue
            raise


# ---------------------------------------------------------------- streaming and timing (run 2)
# Added 2026-10-22 for run 2. Run 1 did not stream; the non-streaming path above is unchanged and is what run 1 used.
# Definitions:
#   wall_s          monotonic clock from just before the request is opened to the message_stop event
#   ttfb_s          request opened -> first server-sent event (message_start): network, queue and prefill
#   first_delta_s   request opened -> first content delta of any kind (thinking, text or tool-input JSON)
#   first_text_s    request opened -> first TEXT delta (the benchmark's first_text_token_s; None when the reply has no text)

# Arm names for the results table.
# Arm ids: model letter plus a digit. O Opus, S Sonnet, F Fable. The digit is the setting:
# 0 high cold, 1 high cached, 2 medium cached, 3 low cached. A trailing letter marks a notebook lever on that arm
# (b explicit system breakpoint, m manual behind a tool, t tool search, x code execution, e context editing,
# k compaction, a advisor, p batch). The notebook's own labels (L ladder, V levers, A, D, X) survive only as old_id.
ALIAS = {"O0": "Opus0", "O1": "Opus1", "O2": "Opus2", "O3": "Opus3", "S0": "Sonnet0", "S1": "Sonnet1",
         "S2": "Sonnet2", "S3": "Sonnet3", "F0": "Fable0", "F1": "Fable1", "F2": "Fable2", "F3": "Fable3"}
RUN2_ARMS = ["O0", "O1", "O2", "O3", "S0", "S1", "S2", "S3", "F0", "F1", "F2", "F3"]


def parse_sse(lines, clock=time.monotonic, t_open=None):
    """Assemble a Messages API stream (an iterable of bytes lines) into the dict a non-streaming call returns,
    plus the timing fields above. Raises RuntimeError on an in-stream error event or a stream that ends early."""
    t_open = clock() if t_open is None else t_open
    msg, blocks, partial = None, {}, {}
    tm = {"ttfb_s": None, "first_delta_s": None, "first_text_s": None, "wall_s": None}
    done = False
    for raw in lines:
        line = raw.decode("utf-8", "replace").strip() if isinstance(raw, (bytes, bytearray)) else raw.strip()
        if not line.startswith("data:"):
            continue
        ev = json.loads(line[5:].strip())
        now = clock() - t_open
        et = ev.get("type")
        if tm["ttfb_s"] is None and et != "ping":
            tm["ttfb_s"] = now
        if et == "error":
            raise RuntimeError("stream error event: %s" % json.dumps(ev.get("error"))[:300])
        if et == "message_start":
            msg = ev["message"]
            msg.setdefault("content", [])
        elif et == "content_block_start":
            blocks[ev["index"]] = dict(ev["content_block"])
            partial[ev["index"]] = ""
        elif et == "content_block_delta":
            d, i = ev["delta"], ev["index"]
            dt = d.get("type")
            if dt in ("text_delta", "thinking_delta", "input_json_delta") and tm["first_delta_s"] is None:
                tm["first_delta_s"] = now
            if dt == "text_delta":
                if tm["first_text_s"] is None:
                    tm["first_text_s"] = now
                blocks[i]["text"] = blocks[i].get("text", "") + d["text"]
            elif dt == "thinking_delta":
                blocks[i]["thinking"] = blocks[i].get("thinking", "") + d["thinking"]
            elif dt == "signature_delta":
                blocks[i]["signature"] = blocks[i].get("signature", "") + d["signature"]
            elif dt == "input_json_delta":
                partial[i] += d["partial_json"]
        elif et == "content_block_stop":
            i = ev["index"]
            if blocks[i].get("type") in ("tool_use", "server_tool_use"):
                blocks[i]["input"] = json.loads(partial[i]) if partial[i].strip() else {}
        elif et == "message_delta":
            msg["stop_reason"] = ev["delta"].get("stop_reason")
            msg["stop_sequence"] = ev["delta"].get("stop_sequence")
            msg.setdefault("usage", {}).update(ev.get("usage") or {})
        elif et == "message_stop":
            tm["wall_s"] = now
            done = True
            break
    if not done or msg is None:
        raise RuntimeError("stream ended before message_stop")
    msg["content"] = [blocks[k] for k in sorted(blocks)]
    return msg, tm


def stream_http(url, hdrs, body, timeout=900):
    """POST with stream:true. Returns (status, response dict or error text, timing, attempts). Retries transient network
    errors and 429/5xx/529 up to 4 times; a retry after bytes were received may bill the partial stream twice, so the
    number of attempts is returned and logged, and the timing is that of the successful attempt only."""
    if not LIVE["armed"]:
        raise RuntimeError("network path reached while not armed; refusing")
    data = json.dumps(dict(body, stream=True), ensure_ascii=False).encode("utf-8")
    for attempt in range(1, 6):
        req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
        t_open = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                msg, tm = parse_sse(r, time.monotonic, t_open)
                return r.status, msg, tm, attempt
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 529) and attempt < 5:
                print("RETRY %d: HTTP %s" % (attempt, e.code), file=sys.stderr)
                time.sleep(5 * attempt)
                continue
            return e.code, txt, None, attempt
        except (urllib.error.URLError, ssl.SSLError, ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            if attempt < 5:
                print("RETRY %d: %s" % (attempt, type(e).__name__), file=sys.stderr)
                time.sleep(5 * attempt)
                continue
            raise


class Run:
    def __init__(self, a, models, env):
        self.a, self.models, self.env = a, models, env
        self.spent_notebook = 0.0
        self.spent_list = 0.0
        self.log = open(os.path.join(a.out, "requests.jsonl"), "a", encoding="utf-8")

    def worst_case(self, body, batch=False):
        p = self.models["prices"][body["model"]]
        tin = len(json.dumps(body)) / 3.0  # generous: well above the real chars-per-token
        cost = (tin * p["in"] * 2.0 + body["max_tokens"] * p["out"]) / 1e6
        return cost * (0.5 if batch else 1.0)

    def guard(self, extra):
        if max(self.spent_notebook, self.spent_list) + extra > self.a.ceiling_usd:
            raise SystemExit("STOP before the next call: spent $%.4f + worst case $%.4f > ceiling $%.2f" % (
                max(self.spent_notebook, self.spent_list), extra, self.a.ceiling_usd))

    def keyed(self, betas=None):
        h = headers(betas, self.env["ANTHROPIC_API_KEY"])
        if self.env.get("ANTHROPIC_WORKSPACE_ID"):
            h["anthropic-workspace-id"] = self.env["ANTHROPIC_WORKSPACE_ID"]
        return h

    def record(self, tag, model, body, status, resp, batch=False, timing=None, attempts=None):
        resp = resp if isinstance(resp, dict) else {"raw": str(resp)[:600]}
        usage = (resp or {}).get("usage") or {}
        nb, lst = both_costs(usage, model, self.models, batch) if usage else (0.0, 0.0)
        self.spent_notebook += nb
        self.spent_list += lst
        self.log.write(json.dumps({"t": time.time(), "tag": tag, "model": model, "status": status,
                                   "resolved_model": (resp or {}).get("model"), "stop": (resp or {}).get("stop_reason"),
                                   "usage": usage, "notebook_cost": nb, "list_cost": lst,
                                   "body_sha256": hashlib.sha256(json.dumps(body).encode()).hexdigest(),
                                   "timing": timing, "attempts": attempts,
                                   "error": None if status == 200 else resp}) + "\n")
        self.log.flush()
        return nb, lst

    def create(self, tag, body, betas=None):
        self.guard(self.worst_case(body))
        if getattr(self.a, "stream", False):
            status, resp, tm, attempts = stream_http(API + "/messages", self.keyed(betas), body)
            text = resp if isinstance(resp, str) else ""
            nb, lst = self.record(tag, body["model"], body, status, resp, timing=tm, attempts=attempts)
            if status != 200:
                raise RuntimeError("HTTP %s on %s: %s" % (status, tag, text[:600]))
            return resp, nb, lst
        status, _, text = http("POST", API + "/messages", self.keyed(betas), body)
        resp = json.loads(text) if text.strip().startswith("{") else {"raw": text[:600]}
        nb, lst = self.record(tag, body["model"], body, status, resp)
        if status != 200:
            raise RuntimeError("HTTP %s on %s: %s" % (status, tag, text[:600]))
        return resp, nb, lst


def run_loop(run, cfg, claim, nonce, tag):
    messages = first_messages(claim)
    nb_tot = lst_tot = 0.0
    verdict, turns = None, 0
    for turns in range(1, 7):
        body = loop_body(cfg, claim, run.models, nonce, messages)
        r, nb, lst = run.create("%s t%d" % (tag, turns), body, cfg.get("betas"))
        nb_tot, lst_tot = nb_tot + nb, lst_tot + lst
        messages.append({"role": "assistant", "content": r["content"]})
        calls = [b for b in r["content"] if b.get("type") == "tool_use"]
        for tu in calls:
            if tu["name"] in TERMINAL:
                verdict = TERMINAL[tu["name"]]
        if verdict or not calls:
            break
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tu["id"], "content": execute_tool(tu["name"], tu["input"])}
            for tu in calls]})
    return verdict or "NONE", nb_tot, lst_tot, turns


def run_decomposed(run, claim, tag):
    nb_tot = lst_tot = 0.0
    turns, facts = 0, []
    for k, (task, tools) in enumerate(SUBAGENT_TASKS, 1):
        messages = [{"role": "user", "content": f"Claim {claim['id']}: {task}"}]
        line = "(max_turns)"
        for t in range(1, 4):
            r, nb, lst = run.create("%s sub%d t%d" % (tag, k, t), subagent_body(run.models, task, tools, messages))
            nb_tot, lst_tot = nb_tot + nb, lst_tot + lst
            messages.append({"role": "assistant", "content": r["content"]})
            calls = [b for b in r["content"] if b.get("type") == "tool_use"]
            if not calls:
                line = next((b["text"] for b in r["content"] if b.get("type") == "text"), "").strip()
                turns += t
                break
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tu["id"], "content": execute_tool(tu["name"], tu["input"])}
                for tu in calls]})
        else:
            turns += 3
        facts.append(line)
    r, nb, lst = run.create("%s decide" % tag, decide_body(run.models, claim, facts))
    verdict = next((TERMINAL[b["name"]] for b in r["content"] if b.get("type") == "tool_use"), "NONE")
    return verdict, nb_tot + nb, lst_tot + lst, turns + 1


def run_batch(run, claims, nonce, tag):
    body = batch_body(run.models, claims, nonce)
    run.guard(sum(run.worst_case(rq["params"], batch=True) for rq in body["requests"]))
    status, _, text = http("POST", API + "/messages/batches", run.keyed(), body)
    if status != 200:
        raise RuntimeError("batch create HTTP %s: %s" % (status, text[:600]))
    bid = json.loads(text)["id"]
    while True:
        time.sleep(10)
        status, _, text = http("GET", API + "/messages/batches/" + bid, run.keyed())
        info = json.loads(text)
        if info.get("processing_status") == "ended":
            break
    status, _, text = http("GET", info["results_url"], run.keyed())
    out = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        res = json.loads(line)
        rr = res["result"]
        if rr.get("type") != "succeeded":
            out[res["custom_id"]] = ("NONE", 0.0, 0.0, 1)
            continue
        msg = rr["message"]
        nb, lst = run.record("%s %s" % (tag, res["custom_id"]), run.models["roles"]["sonnet"], {"batch": bid}, 200, msg,
                             batch=True)
        verdict = next((TERMINAL[b["name"]] for b in msg["content"]
                        if b.get("type") == "tool_use" and b["name"] in TERMINAL), "NONE")
        out[res["custom_id"]] = (verdict, nb, lst, 1)
    return out


def live(cfgs, claims, models, a):
    env = load_key()
    os.makedirs(a.out, exist_ok=True)
    LIVE["armed"] = True
    run = Run(a, models, env)
    summary = open(os.path.join(a.out, "trials.jsonl"), "a", encoding="utf-8")
    plan = [(cfg, trial) for cfg in cfgs for trial in range(1, a.trials + 1)]  # run 1 order: arm by arm
    if getattr(a, "order", "arm") == "rotate":
        # Run 2: trial by trial, with the arm order rotated by a whole share of the list each trial, so an arm is not
        # always run at the same time of day or at the same place in the sequence. Serial; no concurrency.
        plan = []
        for trial in range(1, a.trials + 1):
            off = ((trial - 1) * len(cfgs)) // a.trials
            plan += [(cfg, trial) for cfg in cfgs[off:] + cfgs[:off]]
    for cfg, trial in plan:
        if True:
            nonce = time.time_ns()  # notebook: a fresh nonce per trial resets the cache
            tag = "%s trial%d" % (cfg["id"], trial)
            t_trial = time.monotonic()
            claim_wall = {}
            if cfg["kind"] == "batch_oneshot":
                results = run_batch(run, claims, nonce, tag)
            else:
                results = {}
                for c in claims:
                    t_claim = time.monotonic()
                    if cfg["kind"] == "decomposed":
                        results[c["id"]] = run_decomposed(run, c, "%s %s" % (tag, c["id"]))
                    else:
                        results[c["id"]] = run_loop(run, cfg, c, nonce, "%s %s" % (tag, c["id"]))
                    claim_wall[c["id"]] = round(time.monotonic() - t_claim, 3)
            misses = sorted(c["id"] for c in claims if results.get(c["id"], ("NONE",))[0] != c["expected"])
            n = len(claims)
            rec = {"config": cfg["id"], "label": cfg["label"].strip(), "trial": trial, "n": n,
                   "correct": n - len(misses), "misses": misses,
                   "per_task_notebook": sum(v[1] for v in results.values()) / n,
                   "per_task_list": sum(v[2] for v in results.values()) / n,
                   "turns": sum(v[3] for v in results.values()),
                   "verdicts": {k: v[0] for k, v in results.items()}, "models": models["roles"],
                   "arm_name": ALIAS.get(cfg["id"]), "streamed": bool(getattr(a, "stream", False)),
                   "order": getattr(a, "order", "arm"), "claim_wall_s": claim_wall,
                   "trial_wall_s": round(time.monotonic() - t_trial, 3)}
            summary.write(json.dumps(rec) + "\n")
            summary.flush()
            print("%-4s %-36s trial %d  %d/%d  requests %d  $/task %.4f (list %.4f)  misses %s  spent $%.2f" % (
                cfg["id"], rec["label"], trial, rec["correct"], n, rec["turns"], rec["per_task_notebook"],
                rec["per_task_list"], ",".join(misses) or "-", max(run.spent_notebook, run.spent_list)), flush=True)


def selftest(models, inject_fault=False):
    """Checks against numbers the notebook printed (cells 7, 11, 18, 54). With inject_fault one expectation is
    deliberately wrong, to show the check can fail. Uses the notebook's own ids and prices, not the models file."""
    nb = {"roles": {"opus": "claude-opus-5"}, "prices": {"claude-opus-5": {"in": 5.0, "out": 25.0,
                                                                           "list_cache_read_mult": 0.10}}}
    checks = [
        ("cell 18 auto cache call 1", usage_cost({"input_tokens": 2, "cache_creation_input_tokens": 13097,
                                                  "cache_read_input_tokens": 0, "output_tokens": 13}, "claude-opus-5", nb), 0.0822),
        ("cell 18 auto cache call 2", usage_cost({"input_tokens": 2, "cache_creation_input_tokens": 26,
                                                  "cache_read_input_tokens": 13097, "output_tokens": 82}, "claude-opus-5", nb), 0.0088),
        ("cell 54 batch CLM-005", usage_cost({"input_tokens": 11443, "output_tokens": 428}, "claude-opus-5", nb,
                                             batch=True), 0.0340),
        ("cell 54 sync CLM-001", usage_cost({"input_tokens": 11452, "output_tokens": 603}, "claude-opus-5", nb), 0.0723),
        ("cell 11 system prompt chars", len(SYSTEM_PROMPT), 30395),
        ("cell 11 tools json chars", len(json.dumps(TOOLS)), 3342),
        ("cell 13 eval claims", len(EVAL_CLAIMS), 10),
    ]
    if inject_fault:
        checks.append(("injected fault (must FAIL)", 1.0, 2.0))
    ok = True
    for name, got, want in checks:
        good = round(got, 4) == round(want, 4) if isinstance(want, float) else got == want
        ok &= good
        print("%-4s %-32s got %s want %s" % ("PASS" if good else "FAIL", name, round(got, 4) if isinstance(got, float)
                                             else got, want))
    try:
        http("GET", API + "/models", {})
        print("FAIL network path ran while not armed")
        ok = False
    except RuntimeError as e:
        print("PASS network path refuses while not armed: %s" % e)
    try:
        stream_http(API + "/messages", {}, {})
        print("FAIL streaming path ran while not armed")
        ok = False
    except RuntimeError as e:
        print("PASS streaming path refuses while not armed: %s" % e)
    # Stream parser against a canned stream: thinking + text + a tool_use whose input arrives in two JSON pieces,
    # a ping first, usage split between message_start and message_delta, on a fake clock (1 s per event).
    def ev(o):
        return ("data: " + json.dumps(o)).encode()
    canned = [b"event: ping", ev({"type": "ping"}),
              ev({"type": "message_start", "message": {"id": "m1", "model": "x", "role": "assistant", "content": [],
                                                       "stop_reason": None, "usage": {"input_tokens": 5,
                                                       "cache_creation_input_tokens": 100, "cache_read_input_tokens": 0,
                                                       "output_tokens": 1}}}),
              ev({"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "",
                                                                                "signature": ""}}),
              ev({"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "hm "}}),
              ev({"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "SIG"}}),
              ev({"type": "content_block_stop", "index": 0}),
              ev({"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}}),
              ev({"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "ok"}}),
              ev({"type": "content_block_stop", "index": 1}),
              ev({"type": "content_block_start", "index": 2, "content_block": {"type": "tool_use", "id": "tu1",
                                                                                "name": "deny_claim", "input": {}}}),
              ev({"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta",
                                                                        "partial_json": "{\"reason\": "}}),
              ev({"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta",
                                                                        "partial_json": "\"x\"}"}}),
              ev({"type": "content_block_stop", "index": 2}),
              ev({"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                  "usage": {"output_tokens": 42}}),
              ev({"type": "message_stop"})]
    tick = iter(range(0, 1000))
    msg, tm = parse_sse(canned, clock=lambda: float(next(tick)), t_open=-1.0)
    sse_checks = [
        ("sse: blocks in order", [b["type"] for b in msg["content"]], ["thinking", "text", "tool_use"]),
        ("sse: tool input joined", msg["content"][2]["input"], {"reason": "x"}),
        ("sse: signature kept", msg["content"][0].get("signature"), "SIG"),
        ("sse: stop reason", msg["stop_reason"], "tool_use"),
        ("sse: usage merged", (msg["usage"]["input_tokens"], msg["usage"]["cache_creation_input_tokens"],
                               msg["usage"]["output_tokens"]), (5, 100, 42)),
        ("sse: ping not counted as first event", tm["ttfb_s"] is not None and tm["ttfb_s"] > 1.0, True),
        ("sse: first text after first delta", tm["first_text_s"] > tm["first_delta_s"], True),
    ]
    if inject_fault:
        sse_checks.append(("sse: injected fault (must FAIL)", 1, 2))
    for name, got, want in sse_checks:
        good = got == want
        ok &= good
        print("%-4s %-32s got %s want %s" % ("PASS" if good else "FAIL", name, got, want))
    try:
        parse_sse(canned[:-1], clock=lambda: 0.0, t_open=0.0)
        print("FAIL a stream cut before message_stop was accepted")
        ok = False
    except RuntimeError as e:
        print("PASS stream cut before message_stop is refused: %s" % e)
    print("selftest", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selftest", action="store_true")
    mode.add_argument("--selftest-fault", action="store_true", help="selftest with one wrong expectation; must exit 1")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--estimate", action="store_true")
    mode.add_argument("--live", action="store_true")
    ap.add_argument("--configs", default=None, help="comma-separated config ids; default all")
    ap.add_argument("--claims", default=None, help="comma-separated claim ids; default all ten")
    ap.add_argument("--trials", type=int, default=2)
    ap.add_argument("--models", default=os.path.join(HERE, "models.json"))
    ap.add_argument("--dump", default=None, help="dry run: write full request bodies (JSONL) here")
    ap.add_argument("--show-limit", type=int, default=300, help="dry run: strings longer than this are elided on stdout")
    ap.add_argument("--ceiling-usd", type=float, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--stream", action="store_true",
                    help="run 2: stream every request and record ttfb_s, first_delta_s, first_text_s and wall_s per request")
    ap.add_argument("--order", choices=["arm", "rotate"], default="arm",
                    help="arm: arm by arm (run 1). rotate: trial by trial, arm order rotated each trial (run 2)")
    a = ap.parse_args()
    models = load_models(a.models)
    cfgs = CONFIGS if not a.configs else [c for c in CONFIGS if c["id"] in set(a.configs.split(","))]
    claims = EVAL_CLAIMS if not a.claims else [c for c in EVAL_CLAIMS if c["id"] in set(a.claims.split(","))]
    if not cfgs or not claims:
        raise SystemExit("no configs or claims selected")
    print("models: " + json.dumps(models["roles"]))
    if a.selftest or a.selftest_fault:
        return selftest(models, inject_fault=a.selftest_fault)
    if a.dry_run:
        dry_run(cfgs, claims, models, a.dump, a.show_limit)
        return 0
    if a.estimate:
        estimate(cfgs, a.trials)
        return 0
    if a.ceiling_usd is None or not a.out:
        raise SystemExit("--live needs --ceiling-usd and --out")
    live(cfgs, claims, models, a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
