# Plan: Gemini 3.8 Flash in the model benchmark

Status: **amended 2026-10-23 (see "Amendment 1" at the end); the cache timing test was not run before the amendment, and its smoke set is reported there.** Original status: planned, nothing run. The scripts are [gemini_benchmark.py](../gemini_benchmark.py) (the agent task) and [gemini_cache_timing.py](../gemini_cache_timing.py) (the cache timing test), with prices and model ids in [gemini_models.json](../gemini_models.json). This plan is committed before any paid call. Gemini 4 Argon is in the scripts but is not part of this plan; it would get its own plan after the Flash result.

Navigation: [index](../README.md) · [method](method.md) · [Claude cache timing results](cache-timing-results.md) · [plan for the next runs](plan-next-runs.md)

## What is measured

Gemini 3.8 Flash on Vertex AI (model id `gemini-3.8-flash`, location global), on the same claims task and the same long prefix as the Claude runs:

1. **Smoke set**: one claim at medium thinking, one trial, then one cache timing set. It decides the guesses listed below and sets the hit threshold.
2. **Agent task**: three arms, "Gemini 3.8 Flash high", "medium" and "low" (high, medium, low = thinking level); 2 trials of the 10 claims; streamed; pass = 10 of 10 per trial. There is no no-cache arm, because the cache below cannot be switched off.
3. **Cache timing test**: 10 sets on the long prefix (the system prompt, the tools and the claims ledger), three requests per set, one at a time, thinking at the lowest level the model accepts, output capped.

## Why the cache states differ from the Claude ones

Gemini's implicit cache is on for every project and only an administrator can switch it off. The usage block reports a hit (`cachedContentTokenCount`) and reports no cache write. So the Claude states (no cache, cold which writes, warm which reads) cannot be reproduced. This test uses three request kinds, and proves each from its own usage block:

- **first request**: a fresh nonce at the head of the system instruction, so no earlier prefix matches. Valid when `cachedContentTokenCount` is 0 or absent.
- **repeat request**: the same prefix, a different question, straight after the first request. A valid hit when `cachedContentTokenCount` is at least T percent of `promptTokenCount`.
- **second first request**: another fresh nonce and a third question, the same kind as the first request. It is a control: first request against second first request is the noise floor.

Order in a set alternates: odd sets are first, repeat, control; even sets are control, first, repeat. These states do not map onto the Claude states (a Claude cold request pays a visible write; a Claude no-cache request writes nothing; a Gemini first request may be stored with no write field), so they never share a chart.

**T rule, fixed before the smoke set:** T is the smoke set's lowest valid repeat share minus 5 points, never below 50 percent. It is written into the run's record with the smoke shares beside it before the Flash sets start, and is not changed afterwards. If the smoke set has no repeat hit, the sets do not start.

## Reading rule, fixed now

Headline: repeat request against first request, on valid pairs only; excluded pairs are printed with their timings and cached shares. If fewer than 8 of the 10 repeat requests are valid hits, the reading is **inconclusive**. Otherwise it is **seen** when the repeat was faster in at least 8 valid pairs, and **not seen** if not. The hit rate is reported as a finding. Output speed is the negative control, flagged only when the gap between states is over 10 percent and over the widest within-state interquartile range. Time to first token includes the model's thinking (at the lowest level), which the cache does not shorten; that adds noise and the report says so.

## Guesses the smoke set decides

The scripts make these assumptions; the smoke set shows what the API does, and the observed behaviour is recorded beside each before the Flash sets run.

| Assumption in the code | Expected |
|---|---|
| Tool text goes back as `functionResponse.response = {"result": text}` | accepted |
| `functionResponse` echoes the call's `id` when it has one | the API sends an id and needs it back |
| Schema types are sent in capitals | accepted |
| `promptTokenCount` includes implicitly cached tokens (the documentation says so only for explicit caching) | the prompt count includes the cached count |
| No `x-goog-user-project` header is needed | accepted without |
| Usage arrives in the last streamed chunk | yes |
| Thinking level LOW is accepted with tools in mode NONE | accepted |
| The spend guard's allowance of 24,576 thinking tokens a request covers the real thinking | real thinking is well below |

## Prices and cost

List prices from the Vertex pricing page, read 2026-10-22, standard tier, text, global, per million tokens, through 2026-12-31: input $0.75, cached input $0.075, output (response and reasoning) $3.75, the same up to 200K input tokens. The long prefix is about 148,000 tokens by Anthropic's counter; Gemini's own count comes from the smoke set and must stay under 200K, or the script stops. Cost is priced from the usage block, thinking tokens as output. Upper bounds with no cache hit at all: the agent task about $2.93 (3 arms, 2 trials, 10 claims), the cache timing test $3.4 to $8.9 depending on whether the output limit also bounds thinking, the smoke set under $0.9. The run's ceiling is set by the person running it.

## What is not in this plan

Explicit caching (a separate cache object with storage cost), Gemini 4 Argon, and any comparison of Gemini and Claude times on one chart. The Vertex project id and the access token are never written to a record, a report or an error message; the scripts take them from the environment and show `<PROJECT>` and `<REDACTED>` in dry runs.

## Amendment 1 (2026-10-23 00:29 EDT, committed before any full cache timing set)

The text above is the plan as committed before any paid call. This amendment changes the repeat request, and says why.

**What the smoke set showed.** The smoke run on 2026-10-22 (23:57 EDT) sent one cache timing set on the long prefix (171,360 Gemini tokens). The repeat request, sent straight after its first request with a new question, had **0 percent** of its prompt cached (`cachedContentTokenCount` absent). Under the T rule above T could not be set (the floor is 50 percent), and the sets did not start.

**What the diagnostic then showed** (Gemini 3.8 Flash, thinking LOW, one fresh prefix per probe, a first request followed by the repeat; every probe is two to three requests, so each line is a single observation):

| Repeat kind | Prefix | Wait before the repeat | Cached share of the repeat |
|---|---|---|---|
| new question (the plan's repeat) | 171K tokens, ledger as a system part | 0 s, 30 s, then 120 s after the first request | 0 percent, 0 percent, 0 percent |
| new question | 48K, ledger as a system part | 0 s | 0 percent |
| new question | 48K, ledger in the user message | 0 s | 0 percent |
| new question | 7.6K | 0 s | 0 percent |
| identical request | 7.6K | 0 s | 53.6 percent |
| identical request | 48K | 0 s | 93.1 percent |
| follow-up turn | 7.8K | 0 s | 52.1 percent |
| follow-up turn | 48K | 0 s | 92.6 percent |
| follow-up turn | 171K (the test's prefix) | 0 s | **97.9 percent** |

A follow-up turn is the first request, its own reply (the model's parts exactly as received) and a new question as a second user turn. A new question as a separate request never hit, at any size or wait tried (up to 120 s); an identical request and a follow-up turn did, and the cached part grew with the prompt. The explanation is a hypothesis only: the implicit cache seems to store whole earlier requests, and a request is served from the longest earlier request it extends.

**The change.** The repeat request becomes a **follow-up turn**: the first request of its set, that request's reply, and a new question. Everything else is as planned: the first request, the second first request (the control), the alternating order, the reading rule, the 8-of-10 minimum, the negative control, the prices. The repeat's prompt is about 200 tokens longer than its first request's, and it carries a model turn.

**What this warm case is.** It measures a turn that carries the earlier turn, as an agent's later turn does. It is not a new user reading a shared document, and **it is not comparable with the Claude warm cache** (a separate request with a new question after an explicit breakpoint). The results are never drawn on one chart with the Claude states, and a comparison says "a different warm case".

**T, by the rule as written.** T is the lowest valid repeat share at the prefix the sets run on, minus 5 points, never below 50 percent. The only diagnostic repeat on the long prefix at the test's layout is the follow-up turn at 97.9 percent, so **T = 92.9 percent**. The other follow-up shares (52.1 percent at 7.8K, 92.6 percent at 48K) are listed above and are not used, because the rule is tied to the prefix the sets run on. T is not changed after this amendment; real hits between 87 and 93 percent would make the reading "inconclusive" and the report would say why.

**Money.** The smoke and diagnostic runs cost about $1.2 in all. The full cache timing sets are estimated in the run's own `--estimate`.
