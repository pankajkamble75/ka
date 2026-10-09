# Store benchmark — JSON per object (research-01 R16, plan-09)

Machine: this VPS; Python 3.11.15; one run each, no warm-up.

| N nuggets | fill s | size MB | cold load s | by_status ms | active(scope) ms | search ms | put ms | get ms | hits | wiki article ms | wiki search ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10000 | 2.3 | 12.5 | 0.45 | 2 | 4 | 281 | 0.5 | 0.00 | 50 | 15 (333 refs) | 311 |
| 100000 | 24.7 | 125.7 | 7.84 | 21 | 72 | 3674 | 0.7 | 0.00 | 50 | 177 (3333 refs) | 5388 |

**Reading (plan-25, research-04 R13, recorded not interpreted).** The wiki projection of the largest scope is 15 ms at 10k nuggets
(333 refs) and 177 ms at 100k (3,333 refs) — a cache is not justified by these figures. Wiki **search** is the slow path: 311 ms at 10k
and 5.4 s at 100k, because it projects every page and scans tokens, exactly as `ka.search` does (3.7 s at 100k, plan-09). Both slow
paths are the same linear scan; whether an index is wanted is the author's decision when the corpus approaches that size. The live
storage holds 995 nugget versions (51 ACTIVE).
