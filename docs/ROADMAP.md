# Delivery Roadmap

Work in order. Do not expand later milestones while an earlier milestone lacks its acceptance evidence.

## Milestone 0 — Foundation and executable architecture ✅

- Repository structure, tooling, configuration, containers, CI, and migration harness.
- FastAPI application shell with health/readiness and structured error contracts.
- PostgreSQL integration and module boundary checks.
- Seeded fictional tenant and deterministic clock/ID strategy for tests.

**Exit evidence:** project tooling, PostgreSQL Compose service, initial Alembic migration, API shell, CI workflow, tests, and OpenAPI export are implemented. A clean CI run remains required after repository publication.

## Milestone 1 — Verifiable ledger 🚧

- Tenants, currencies, accounts, journals, entries, and balance queries.
- Atomic posting service with database constraints.
- Reversals and traceable references.
- Property and concurrency tests.

**Exit evidence:** atomic posting, derived balances, PostgreSQL balance/immutability triggers, reversals, and API tests are implemented. PostgreSQL integration and concurrency verification remain before this milestone is complete.

## Milestone 2 — Idempotent payment commands

- Transfers, holds, fees, refunds, explicit state transitions, and idempotency records.
- Safe concurrent spending rules.
- Transactional outbox written with financial state.

**Exit evidence:** duplicate, conflicting, racing, and interrupted requests have documented deterministic outcomes.

## Milestone 3 — Provider evidence and failures

- Simulated provider adapter, signed webhooks, replay defense, retries, and out-of-order handling.
- Worker processing, dead letters, causal timelines, and failure injection.

**Exit evidence:** the same deterministic scenario survives duplicates, delays, invalid signatures, and worker restarts.

## Milestone 4 — Settlement and reconciliation

- Statement import, evidence hashing, deterministic matching, discrepancy taxonomy, reruns, and resolution workflows.
- Adjustment and reversal accounting.

**Exit evidence:** canonical mismatches are detected, explained, resolved, and safely reproduced on rerun.

## Milestone 5 — Operations console and guided demo

- Money-flow view, ledger explorer, causal timeline, settlement view, discrepancy queue, and scenario controls.
- Recruiter-oriented guided walkthrough with explicit fictional-data labeling.

**Exit evidence:** a reviewer can complete the canonical story without terminal access or undocumented setup.

## Milestone 6 — Production evidence and portfolio packaging

- Threat model, runbooks, telemetry dashboards, load and fault reports, architecture diagrams, public case study, and hosted demo.
- Honest limitations and architectural tradeoffs.

**Exit evidence:** reproducible deployment, working live demo, clear source documentation, and a two-minute portfolio narrative.
