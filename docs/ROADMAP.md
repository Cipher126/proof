# Delivery Roadmap

Work in order. Do not expand later milestones while an earlier milestone lacks its acceptance evidence.

## Milestone 0 — Foundation and executable architecture ✅

- Repository structure, tooling, configuration, containers, CI, and migration harness.
- FastAPI application shell with health/readiness and structured error contracts.
- PostgreSQL integration and module boundary checks.
- Seeded fictional tenant and deterministic clock/ID strategy for tests.

**Exit evidence:** project tooling, PostgreSQL Compose service, initial Alembic migration, API shell, CI workflow, tests, and OpenAPI export are implemented. A clean CI run remains required after repository publication.

## Milestone 1 — Verifiable ledger ✅

- Tenants, currencies, accounts, journals, entries, and balance queries.
- Atomic posting service with database constraints.
- Reversals and traceable references.
- Property and concurrency tests.

**Exit evidence:** atomic posting, derived balances, PostgreSQL balance/immutability triggers, reversals, API tests, and direct PostgreSQL invariant tests are implemented and passing.

## Milestone 2 — Idempotent payment commands (transfer slice verified)

- Transfers, holds, fees, refunds, explicit state transitions, and idempotency records.
- Safe concurrent spending rules.
- Transactional outbox written with financial state.

**Evidence:** PostgreSQL tests cover racing retries and competing spends. Holds, refunds, the full payment state machine, and crash-injection evidence remain open.

## Milestone 3 — Provider evidence and failures (demo slice verified)

- Simulated provider adapter, signed webhooks, replay defense, retries, and out-of-order handling.
- Worker processing, dead letters, causal timelines, and failure injection.

**Evidence:** API tests verify signed evidence, duplicate handling, and classification. PostgreSQL tests verify local outbox completion and dead lettering. The worker runs bounded batches against a local sink. External delivery and crash recovery remain open.

## Milestone 4 — Settlement and reconciliation (demo slice verified)

- Statement import, evidence hashing, deterministic matching, discrepancy taxonomy, reruns, and resolution workflows.
- Adjustment and reversal accounting.

**Evidence:** the guided demo imports a normalized JSON statement, reconciles it, and posts an audited adjustment. Settlement batch lifecycle, timing discrepancy rules, and concurrent import and resolution tests remain open.

## Milestone 5 — Operations console and guided demo ✅

- Money-flow view, ledger explorer, causal timeline, settlement view, discrepancy queue, and scenario controls.
- Recruiter-oriented guided walkthrough with explicit fictional-data labeling.

**Exit evidence:** the TypeScript console builds successfully and browser QA at 1440×1000 verified the real one-click incident, evidence views, causal timeline, and controlled resolution without terminal access.

## Milestone 6 — Production evidence and portfolio packaging 🚧

- Threat model, runbooks, telemetry dashboards, load and fault reports, architecture diagrams, public case study, and hosted demo.
- Honest limitations and architectural tradeoffs.

**Evidence:** the local container serves the dashboard after migration. The sandbox issues expiring, tenant-scoped credentials and attributes resolution audits to the authenticated credential. Public hosting still requires rate limits and demo-data retention.
