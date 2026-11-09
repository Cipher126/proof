# PostgreSQL performance case study

The [recorded drill](operational-drill.json) captures two local experiments. The [recovery drill](../RECOVERY.md) reproduces both on a disposable database and writes fresh results. The [earlier single-account baseline](local-latest.json) remains available as historical evidence.

## Contention during transfers

The packaged API handles 100 one-unit transfers at concurrency eight in each run. The hot workload uses one account pair. The spread workload assigns each worker its own pair. Both runs verify every response and check that each funded source reaches zero and each destination receives the expected amount.

The sampler queries `pg_stat_activity` about every 10 ms for sessions tagged with the drill API's application name and waiting on a PostgreSQL lock. Sample counts indicate observed contention. They do not measure per-request wait time, and waits between samples can be missed. End-to-end latency also includes client, API, database, and outbox work.

The comparison saves both workload outcomes, including HTTP status counts, transport failures, and validation errors. A failed workload makes the command exit nonzero after saving the report.

| Workload | HTTP 201 | p95 | Transfers/s | Samples with lock waiters | Peak waiters |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hot pair | 100/100 | 392.63 ms | 30.71 | 177/182 | 7 |
| Spread pairs | 100/100 | 337.16 ms | 31.94 | 0/196 | 0 |

The protected-account lock remains in place. It serializes competing spending on the same account so two transfers cannot both spend the same available balance.

## Reconciliation query plan

The fixture contains 40,000 successful fictional transfers with balanced posted journals. Eight fall inside the settlement window and one older transfer is explicitly named in the statement. The profile compiles the same candidate query the application runs and checks that all nine expected references match before and after migration 0012. PostgreSQL runs `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` five times per revision.

| Revision | Candidate lookup plan | Median execution | Shared buffer hits in the recorded plan |
| --- | --- | ---: | ---: |
| 0011 | Sequential scan | 5.663 ms | 1,001 |
| 0012 | Bitmap OR over both indexes | 0.215 ms | 8 |

The partial index on tenant and completion time covers the posted-window branch. The existing unique index covers the explicit-reference branch. The new index adds work when a transfer posts, and the one-time transactional build requires a quiet write window on populated databases. See [ADR-014](../DECISIONS.md#adr-014-index-the-posted-transfer-window-used-for-reconciliation).

These runs use a single local Docker host and synthetic data. The query timings describe the candidate lookup. Total reconciliation time also includes statement processing, findings, and audit writes.
