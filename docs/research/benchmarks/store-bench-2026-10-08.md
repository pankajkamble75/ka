# Store benchmark — JSON per object (research-01 R16, plan-09)

Machine: this VPS; Python 3.11.15; one run each, no warm-up.

| N nuggets | fill s | size MB | cold load s | by_status ms | active(scope) ms | search ms | put ms | get ms | hits |
|---|---|---|---|---|---|---|---|---|---|
| 10000 | 2.4 | 12.5 | 0.50 | 2 | 3 | 279 | 0.6 | 0.00 | 50 |
| 100000 | 26.4 | 125.7 | 8.47 | 17 | 61 | 3682 | 0.8 | 0.00 | 50 |

**Reading (plan-09, recorded not interpreted).** At 100k nuggets the per-object JSON store is 126 MB on disk, loads cold in
8.5 s (once per process; every collection caches), answers status and scope queries from the cache in tens of milliseconds,
and writes/reads a single object in under a millisecond. The one slow path is `search` (3.7 s at 100k): the token-overlap
scan is linear over the cache. Whether that calls for an index inside the store or a migration is the author's decision; the
measured 10k figures (0.5 s cold load, 0.28 s search) are within what the console tolerates today.
