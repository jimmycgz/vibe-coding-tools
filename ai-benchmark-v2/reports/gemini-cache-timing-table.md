Hit threshold: a repeat request (follow-up turn) is a valid hit when at least 92.9 percent of its own prompt tokens were read from the cache (fixed before the run).

| Model | State | Requests | Valid | First token s (median, quartiles) | Total s (median) | Output tokens/s (median) | Thinking tokens (median) | $ per request (mean of valid) |
|---|---|---|---|---|---|---|---|---|
| Gemini 3.8 Flash | first request | 10 | 9 | 4.73 (4.54 to 5.13) | 5.98 | 146.1 | 235 | 0.1292 |
| Gemini 3.8 Flash | repeat request (follow-up turn) | 10 | 8 | 2.37 (2.25 to 2.61) | 3.29 | 153.8 | 214 | 0.0161 |
| Gemini 3.8 Flash | second first request | 10 | 10 | 4.82 (4.49 to 5.86) | 5.77 | 160.3 | 348 | 0.1294 |

Total spent: $2.8624 over 30 requests.

Hit rate: whether each repeat request (follow-up turn) read its prefix from the cache.

| Model | Set | Claim of the repeat request (follow-up turn) | Cached share | Valid hit |
|---|---|---|---|---|
| Gemini 3.8 Flash | 1 | CLM-004 | 0.0 percent | no |
| Gemini 3.8 Flash | 2 | CLM-005 | 97.9 percent | yes |
| Gemini 3.8 Flash | 3 | CLM-006 | 97.5 percent | yes |
| Gemini 3.8 Flash | 4 | CLM-007 | 0.0 percent | no |
| Gemini 3.8 Flash | 5 | CLM-008 | 97.7 percent | yes |
| Gemini 3.8 Flash | 6 | CLM-009 | 97.9 percent | yes |
| Gemini 3.8 Flash | 7 | CLM-010 | 97.9 percent | yes |
| Gemini 3.8 Flash | 8 | CLM-001 | 97.9 percent | yes |
| Gemini 3.8 Flash | 9 | CLM-002 | 97.8 percent | yes |
| Gemini 3.8 Flash | 10 | CLM-003 | 97.9 percent | yes |

Hit rate, Gemini 3.8 Flash: 8 of 10 repeat requests were valid hits.
Hit rate, overall: 8 of 10 repeat requests were valid hits.

Missed repeat requests (left out of the medians and the pairs, shown here): 2.

- flash set1 repeat CLM-004: cached share 0.0 percent, first token 4.86 s, total 5.68 s; repeat request read 0.0 percent from the cache, below the threshold of 92.9 percent
- flash set4 repeat CLM-007: cached share 0.0 percent, first token 4.48 s, total 5.76 s; repeat request read 0.0 percent from the cache, below the threshold of 92.9 percent

Repeat requests not sent or not on record (counted above as not valid hits): 0.

Paired differences, per set, valid pairs only (negative = the first-named was faster):

| Model | Pair | First token s, median difference | Sets where the first-named was faster | Total s, median difference |
|---|---|---|---|---|
| Gemini 3.8 Flash | repeat request (follow-up turn) minus first request | -2.13 | 7 of 7 | -2.22 |
| Gemini 3.8 Flash | first request minus second first request (noise floor) | -0.16 | 5 of 9 | -0.20 |

Excluded pairs: 4.

- Gemini 3.8 Flash, repeat request (follow-up turn) minus first request, set 1: repeat request (follow-up turn) not valid (repeat request read 0.0 percent from the cache, below the threshold of 92.9 percent)
- Gemini 3.8 Flash, repeat request (follow-up turn) minus first request, set 3: first request not valid (first request shows 167113 cached tokens (97.5 percent): its prefix was not fresh)
- Gemini 3.8 Flash, repeat request (follow-up turn) minus first request, set 4: repeat request (follow-up turn) not valid (repeat request read 0.0 percent from the cache, below the threshold of 92.9 percent)
- Gemini 3.8 Flash, first request minus second first request (noise floor), set 3: first request not valid (first request shows 167113 cached tokens (97.5 percent): its prefix was not fresh)

Reading rule (fixed before the run). Headline: repeat request (follow-up turn) against first request. Fewer than 8 valid hits of the 10 repeat requests: inconclusive. Otherwise seen when the repeat was faster in at least 8 valid pairs, with at least 8 valid pairs; else not seen. First request against second first request is a noise floor: two requests of the same state, so a count far from half shows noise, load or the network, not the cache.

| Model | Headline: repeat request (follow-up turn) against first request | Valid hits | Noise floor: first request against second first request |
|---|---|---|---|
| Gemini 3.8 Flash | not seen (repeat faster in 7 of 7 valid pairs) | 8 of 10 | first faster in 5 of 9 valid pairs |

Negative control: output tokens per second should not depend on the state, since a cache read skips reading the prompt and not generating tokens. Flagged only when the largest gap between the state medians is both more than 10 percent and larger than the widest interquartile range inside a state.

| Model | Tokens/s: first request, repeat request (follow-up turn), second first request | Largest relative difference | Widest within-state spread (interquartile range) | Flag |
|---|---|---|---|---|
| Gemini 3.8 Flash | 146.1, 153.8, 160.3 | 8.8 percent | 36.5 tokens/s | none |

Longest wait between a first request ending and its repeat request (follow-up turn) starting: 0.0 s.

First and second first requests that failed their state check (left out of the medians): 1 of 20.

- flash set3 first CLM-003: cached share 97.5 percent, first token 9.25 s, total 10.18 s; first request shows 167113 cached tokens (97.5 percent): its prefix was not fresh

Model: Gemini 3.8 Flash. Prefix: the benchmark's system prompt and tools plus the claims ledger. Thinking level: LOW; time to first token includes that thinking.

These three states do not map onto the Anthropic cold, warm and no-cache states (a Gemini first request may be stored implicitly with no write field, and no request runs without the cache), so they are never drawn on one chart with them. The repeat request is a follow-up turn: the first request, its reply and a new question, so it measures a turn that carries the earlier turn, not a new user reading a shared document; it is not comparable with the Anthropic warm cache.
