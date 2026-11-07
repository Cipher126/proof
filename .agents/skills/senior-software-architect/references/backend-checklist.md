# Backend Completion Checklist

Apply proportionally to the change.

## Contract and domain

- Inputs, outputs, errors, authorization, and idempotency semantics are explicit.
- State transitions and forbidden transitions are tested.
- Time, money, identifiers, nullability, and ordering have unambiguous representations.

## Data

- Transaction boundaries and isolation assumptions are documented.
- Database constraints protect critical invariants.
- Indexes match demonstrated query and locking patterns.
- Migrations are deterministic, reviewable, and safe for existing data.

## Distributed behavior

- Retry ownership, timeouts, deduplication, and backoff are defined.
- Consumers tolerate at-least-once execution where applicable.
- Partial failures do not leave hidden or irrecoverable state.
- Recovery and replay are bounded, authorized, observable, and idempotent.

## Security and tenancy

- Authentication and authorization are enforced server-side.
- Tenant scope cannot be selected or bypassed through untrusted identifiers.
- Secrets and sensitive data are excluded from logs, errors, traces, and fixtures.
- Abuse limits and payload limits exist at exposed boundaries.

## Operations

- Errors have stable codes and useful correlation context.
- Logs, metrics, traces, and audit events describe the same causal flow.
- Liveness, readiness, and dependency failures are distinguishable.
- A runbook or guided recovery path exists for material failures.

## Evidence

- Tests target invariants, concurrency, and failure—not only happy paths.
- Benchmarks state workload and limitations.
- Documentation matches observed behavior.
