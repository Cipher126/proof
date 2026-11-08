# PostgreSQL performance case study

The [recorded drill](operational-drill.json) captures two local experiments. The [recovery drill](../RECOVERY.md) reproduces both on a disposable database and writes fresh results. The [earlier single-account baseline](local-latest.json) remains available as historical evidence.

## Contention during transfers

The packaged API handles 100 one-unit transfers at concurrency eight in each run. The hot workload uses one account pair. The spread workload assigns each worker its own pair. Both runs verify every response and check that each funded source reaches zero and each destination receives the expected amount.

The sampler queries `pg_stat_activity` about every 10 ms for sessions tagged with the drill API's application name and waiting on a PostgreSQL lock. Sample counts indicate observed contention. They do not measure per-request wait time, and waits between samples can be missed. End-to-end latency also includes client, API, database, and outbox work.

| Workload | HTTP 201 | p95 | Transfers/s | Samples with lock waiters | Peak waiters |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hot pair | 100/100 | 508.86 ms | 18.83 | 268/276 | 7 |
| Spread pairs | 100/100 | 513.33 ms | 19.17 | 0/281 | 0 |

The spread workload removed the sampled lock waits. HTTP latency was similar in this run, so the data supports a contention diagnosis without attributing end-to-end latency to that lock alone.

The protected-account lock remains in place. It serializes competing spending on the same account so two transfers cannot both spend the same available balance.

## Reconciliation query plan

The fixture contains 40,000 successful fictional transfers with balanced posted journals. Eight fall inside the settlement window and one older transfer is explicitly named in the statement. The profile compiles the same candidate query the application runs and checks that all nine expected references match before and after migration 0012. PostgreSQL runs `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` five times per revision.

| Revision | Candidate lookup plan | Median execution | Shared buffer hits in the recorded plan |
| --- | --- | ---: | ---: |
| 0011 | Sequential scan | 17.892 ms | 1,001 |
| 0012 | Bitmap OR over both indexes | 0.276 ms | 8 |

The partial index on tenant and completion time covers the posted-window branch. The existing unique index covers the explicit-reference branch. The new index adds work when a transfer posts, and the one-time transactional build requires a quiet write window on populated databases. See [ADR-014](../DECISIONS.md#adr-014-index-the-posted-transfer-window-used-for-reconciliation).

These runs use a single local Docker host and synthetic data. The query timings describe the candidate lookup. Total reconciliation time also includes statement processing, findings, and audit writes.
