| Model | Prefix | State | Checked ok | First token s (median, quartiles) | First event s (median) | Wall s (median) | Output tokens/s (median) | Connect s (median, not in the times) | $ per request |
|---|---|---|---|---|---|---|---|---|---|
| Sonnet | long | no cache | 10 of 10 | 3.61 (1.91 to 3.74) | 3.61 | 5.57 | 127.2 | 0.049 | 0.2991 |
| Sonnet | long | cold cache (writes) | 10 of 10 | 3.72 (3.46 to 4.08) | 3.72 | 5.72 | 127.8 | 0.047 | 0.3731 |
| Sonnet | long | warm cache (reads) | 10 of 10 | 3.31 (1.84 to 3.66) | 3.31 | 5.31 | 133.9 | 0.051 | 0.0325 |

Paired differences, per repetition, same model and prefix (negative = the second is faster):

| Model | Prefix | Pair | First token s, median difference | Repetitions where the second was faster | Wall s, median difference |
|---|---|---|---|---|---|
| Sonnet | long | cold cache to warm cache | -0.41 | 7 of 10 | -0.31 |
| Sonnet | long | no cache to warm cache | -0.49 | 7 of 10 | -0.52 |
| Sonnet | long | no cache to cold cache | +0.29 | 4 of 10 | +0.18 |

Reading rule (fixed before the run). Headline: warm against no cache; a saving is seen when warm was faster in at least 8 of the 10 paired repetitions. Stricter, secondary: warm also faster than cold in at least 8. Separately, the cost of writing: cold slower than no cache in at least 8.

| Model | Prefix | Headline: warm faster than no cache | Stricter: also faster than cold | Cold slower than no cache (the cost of a write) |
|---|---|---|---|---|
| Sonnet | long | not seen (7 of 10) | not seen (7 of 10) | not seen (6 of 10) |

Negative control: output tokens per second should not depend on the cache state, since a cache read skips reading the prompt and not generating tokens. The flag is raised only when the largest difference between the state medians is both more than 10 percent and larger than the widest scatter inside a state (its interquartile range), and the spread is printed beside it so a reader can see for themselves.

| Model | Prefix | Tokens/s: no cache, cold, warm | Largest relative difference | Widest within-state spread (interquartile range) | Flag |
|---|---|---|---|---|---|
| Sonnet | long | 127.2, 127.8, 133.9 | 5.1 percent | 19.9 tokens/s | none |

Longest wait between a cold request ending and its warm request starting: 0.0 s (the cache lives 5 minutes).

Requests that failed their state check (left out of the medians): 0 of 30.

Models: Opus 5.5, Sonnet 5.5, Fable 5.1, the latest versions. 13k = the benchmark's system prompt and tools, about 13,000 tokens; long = the same plus the claims ledger. no cache = none; cold = first request with a cache breakpoint, writes; warm = a different question after the same prefix, reads.
