# PostgreSQL recovery drill

## Reproduce locally

```bash
uv sync --frozen
docker build -t proof:verification .
uv run python scripts/recovery_drill.py
```

The drill creates a randomly named Docker network and containers with dynamically assigned loopback ports. It uses PostgreSQL 17 and the packaged API on port 10000. Each resource is removed when the drill exits normally or raises an error. The regular Compose database is outside this network.

1. Start at revision 0011, run the full fictional scenario with the restricted runtime login, and create 40,000 balanced synthetic transfers. Capture the reconciliation query plan and record a checksum and row count for seven business tables.
2. Take a custom-format `pg_dump` and apply migration 0012 while the API remains running. Compare query candidates and business records before and after the upgrade. Insert a post-backup canary in the original database.
3. Stop PostgreSQL. Confirm that `/health` returns 200 and `/ready` returns 503 with `database_unavailable`. Restart PostgreSQL and measure the time until readiness returns.
4. Restore the archive into a separate database. Check the prior migration revision, exact checkpoint contents for the sampled tables, absence of the post-backup canary, and balanced journals. Upgrade to the current revision. Reapply grants, confirm the runtime role cannot change posted entries, and run the full HTTP smoke scenario on the restored database.
5. Run the hot and spread HTTP benchmark against the restored database, using a development-mode API reachable on loopback only.

The [recorded drill](benchmarks/operational-drill.json) includes the query plans, lock samples, restore timings, and recovery checks. It measures a local logical restore on one Docker host. An isolated archive is the recovery point. The canary shows that writes after that point require another recovery source. The timings exclude provider failover, DNS or secret changes, and traffic cutover.

In the recorded run, readiness returned 1.25 seconds after the restart command began. The archive restored in 4.75 seconds, and the migration and full HTTP smoke scenario finished 32.23 seconds after restore began. The restored checkpoint included 80,006 journal entries across 40,003 journals, with zero unbalanced journals. PostgreSQL rejected the attempted posted-entry mutation.

## Respond to a hosted incident

Check `/health`, `/ready`, application request IDs and database provider status. Use the migration-owner connection from a trusted host to distinguish a database availability issue from a credential or migration failure. Hold new deploys while investigating. After connectivity recovers, verify readiness and run a fictional smoke case.

If data recovery is needed, stop writes and preserve the original database. Take the latest available backup and restore it into a fresh target using the database owner. Review the recovery point against confirmed writes, then check revision, row counts, journal balances, trigger behavior and the full smoke scenario with the runtime login. Reapply the [runtime grants](../deploy/runtime_grants.sql) after migration. Switch the runtime connection only after validation, keep the former target available for investigation, and record the outage and any writes outside the recovery point.

For recurring logical backups, store encrypted archives outside the API container and periodically restore one to an isolated database. Keep the backup and restore credentials outside the image and Git. For a backward-compatible schema change such as 0012, roll back the application first and keep the schema in place.
