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

**Exit evidence:** atomic posting, derived balances, PostgreSQL balance/immutability triggers, reversals, API tests, generated ledger and replay properties, and direct PostgreSQL invariant tests are implemented and passing.

## Milestone 2 — Idempotent payment commands

- Transfers, holds, fees, refunds, explicit state transitions, and idempotency records.
- Safe concurrent spending rules.
- Transactional outbox written with financial state.

**Evidence:** Immediate transfers and deferred payment intents share account locking. Deferred intents support authorization, submission, capture with fees, failure, cancellation, expiry, and partial or full refunds. PostgreSQL tests cover racing retries and competing holds.

## Milestone 3 — Provider evidence and failures

- Simulated provider adapter, signed webhooks, replay defense, retries, and out-of-order handling.
- Worker processing, dead letters, causal timelines, and failure injection.

**Evidence:** Signed evidence binds tenant, timestamp and event ID. The worker supports external HTTP delivery, bounded retries, dead-letter requeue, and stable IDs after a simulated process crash. Consumers must deduplicate. Provider evidence remains separate from trusted payment transitions.

## Milestone 4 — Settlement and reconciliation

- Statement import, evidence hashing, deterministic matching, discrepancy taxonomy, reruns, and resolution workflows.
- Adjustment and reversal accounting.

**Evidence:** Imported statements serve as settlement batches. Matching checks capture timing and evidence discrepancies. Concurrent imports and adjustments converge. An operator can close a batch after its findings are resolved.

## Milestone 5 — Operations console and guided demo ✅

- Money-flow view, ledger explorer, causal timeline, settlement view, discrepancy queue, and scenario controls.
- Recruiter-oriented guided walkthrough with explicit fictional-data labeling.

**Exit evidence:** the case queue, ledger explorer, and event trail support the end-to-end sandbox workflow. Desktop and narrow viewport checks verified the review, adjustment, and audit trail.

## Milestone 6 — Production evidence and portfolio packaging 🚧

- Threat model, runbooks, telemetry dashboards, load and fault reports, architecture diagrams, public case study, and hosted demo.
- Honest limitations and architectural tradeoffs.

**Evidence:** The local image includes Prometheus metrics, a Grafana dashboard, optional OTLP tracing, named scoped credentials, sandbox admission caps, and opt-in retention. PostgreSQL tests verify schema readiness and the API-to-worker trace using loopback OTLP and webhook receivers. The hosted Compose profile, Render Free Blueprint, and deployment guide are included. The [recovery drill](RECOVERY.md) verifies the packaged image, a database outage, and an isolated restore. Public deployment and live verification with the chosen host, collector, and receiver remain pending.
