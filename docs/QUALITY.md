# Quality, Security, and Evidence Standard

## Test strategy

- Unit tests for pure money, state-machine, matching, and authorization rules.
- Property-based tests for ledger balance and idempotency invariants.
- Integration tests against real PostgreSQL for constraints, locking, migrations, and transaction behavior.
- Contract tests for OpenAPI, provider adapters, webhook signatures, and exported SDK behavior.
- End-to-end tests for the canonical demo and operator recovery paths.
- Fault tests for duplicate requests, out-of-order events, worker crashes, dependency interruption, and reconciliation reruns.

Coverage percentage is supporting evidence, not the goal. Tests must target invariants and failure boundaries.

## Security baseline

- Threat-model every external trust boundary.
- Store password and API-key verifiers using suitable one-way algorithms; never log credentials.
- Enforce authorization in application services and tenant filters, not only in UI routes.
- Authenticate webhooks with versioned signature schemes, constant-time comparison, timestamp windows, and replay records.
- Apply rate and body-size limits at appropriate boundaries.
- Redact secrets and sensitive payload fields recursively from structured logs.
- Use fictional data in public demos and fixtures.

## Observability

- Correlation and trace IDs span API, outbox, worker, provider event, and reconciliation activity.
- Structured logs describe events without becoming the source of truth.
- Metrics cover request outcomes, idempotency reuse/conflicts, outbox lag, worker failures, webhook validity, reconciliation findings, and database contention.
- Traces expose latency and causal flow without recording secrets or full financial payloads.
- Health endpoints distinguish liveness from dependency readiness.

## Performance evidence

- Define a workload, dataset, hardware/runtime context, and pass criteria before benchmarking.
- Measure latency distributions, throughput, error rate, lock waits, pool saturation, and outbox lag.
- Keep raw or machine-readable reports with the code.
- Publish limitations and failed targets honestly.
- Do not claim production scale from a local synthetic test.

## Review gates

Before marking a milestone complete, verify:

- financial invariants and forbidden paths;
- migration upgrade from a clean database;
- authorization and tenant isolation;
- retry, timeout, and partial-failure behavior;
- logs, metrics, traces, and operator explanation;
- documentation and deterministic demo steps;
- no committed secrets or real personal/financial data.
