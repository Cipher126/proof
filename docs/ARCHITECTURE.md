# Architecture

## Architectural style

Proof begins as a **modular monolith with separately runnable process roles**. One repository and one versioned domain model keep financial transactions coherent; API, worker, scheduler, and reconciliation processes may scale independently while sharing the same PostgreSQL source of truth.

Microservices are not a target. A module may become a service only when measured scaling, isolation, ownership, or deployment requirements outweigh the cost of distributed consistency.

## System context

```text
API clients ───────> FastAPI application ───────> PostgreSQL
                           │                           │
Simulated providers ─> webhook ingress               │
                           │                           │
                           └─ transactional outbox ───┘
                                         │
                                         v
                                  background workers
                                         │
                            reconciliation + notifications
                                         │
                                         v
                               operations console / telemetry
```

## Modules

- **identity:** tenants, named API credentials, roles, and authorization.
- **ledger:** accounts, journal transactions, entries, and derived balances.
- **payments:** transfers, holds, fees, refunds, and state machines.
- **providers:** provider configuration, signed event ingestion, simulations, normalized evidence.
- **settlement:** settlement batches and provider-statement imports.
- **reconciliation:** deterministic matching, findings, resolutions, reruns.
- **operations:** audit events, timelines, health, metrics, and administrative queries.
- **messaging:** transactional outbox, delivery attempts, retries, and dead letters.

Modules communicate through explicit application interfaces and domain events. They must not reach into another module's persistence internals.

## Data and consistency

- PostgreSQL is authoritative for ledger, payment state, idempotency, outbox, provider evidence, and reconciliation findings.
- Financial writes use database transactions, constraints, appropriate row locking, and deterministic lock ordering.
- Redis is optional infrastructure for bounded caching, rate limiting, or ephemeral coordination. It is never the financial source of truth.
- Consumers are at-least-once; handlers must be idempotent.
- Schema changes use Alembic and expand/contract practices when compatibility matters.

## API approach

- Versioned REST API with OpenAPI as an exported, tested contract.
- Opaque public identifiers; internal keys remain private.
- Stable machine-readable error codes and request correlation IDs.
- `Idempotency-Key` is required for financial command endpoints.
- Webhook signatures include timestamp tolerance and replay defense.

## Operations console

The console is a thin client over documented APIs. It visualizes ledger entries, money flow, provider evidence, reconciliation findings, and causal timelines. It must not contain business rules required for correctness.

## Deployment baseline

- Containerized API and worker processes.
- Managed PostgreSQL-compatible database for hosted demonstrations.
- Least-privilege runtime identities and environment-provided secrets.
- Structured logs, metrics, traces, readiness, and dependency health.
- Seeded fictional demo tenant and deterministic scenario runner.

## Evolution triggers

Revisit the architecture only with evidence such as lock contention, query plans, queue lag, failure-domain requirements, security isolation, or independent release ownership. Document the trigger and alternatives in `docs/DECISIONS.md`.
