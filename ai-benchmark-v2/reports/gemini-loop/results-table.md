| Arm | Trials | $ per task | Wall s per claim | Wall s per request | First event s, first / later turns | First content s, first / later turns | First text s, first / later turns |
|---|---|---|---|---|---|---|---|
| Gemini 3.8 Flash high | 10/10, 10/10 | 0.0313 | 27.97 | 4.20 | 3.64 / 5.40 | 3.64 / 5.40 | n/a / n/a |
| Gemini 3.8 Flash medium | 10/10, 10/10 | 0.0261 | 20.04 | 3.44 | 2.88 / 4.47 | 2.88 / 4.47 | n/a / n/a |
| Gemini 3.8 Flash low | 7/10, 8/10 | 0.0209 | 11.48 | 1.85 | 1.97 / 1.70 | 1.97 / 1.70 | n/a / n/a |

Gemini arms: high, medium, low = thinking level. The Gemini cache is implicit, on for every project and not switchable by a user, so there is no no-cache arm; the cached share is what the usage block reported. Times are medians over all requests of the arm; wall time per claim runs from a claim's first request to its verdict.
