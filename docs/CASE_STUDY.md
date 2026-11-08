# Proof — Engineering Case Study

## The problem

Payment systems fail in inconvenient ways: clients retry, callbacks arrive twice or out of order, workers crash, and provider settlement records disagree with internal expectations. A successful request is not enough; the system must explain what happened and remain correct under failure.

Proof is a fictional payment ledger and reconciliation platform built to make that correctness visible.

## The portfolio thesis

> I build reliable Python systems that remain correct when requests are duplicated, services fail, and money is involved.

## The guided incident

1. A fictional merchant submits an NGN 25,000 transfer.
2. Proof atomically commits the transfer, two balanced ledger entries, the idempotency outcome, and an outbox event.
3. A simulated provider reports NGN 24,750.
4. The signed provider evidence is preserved and classified as a conflict.
5. A content-addressed statement produces one explainable NGN 250 amount mismatch.
6. An operator posts a controlled balanced adjustment.
7. Proof retains the original records, links the new adjustment, and appends an audit event.

The operations console runs this story against the real backend; it is not a static mockup.

## Important design decisions

- **Modular monolith:** financial transactions stay coherent while API and worker roles can scale independently.
- **PostgreSQL authority:** durable records, constraints, locks, and migrations define correctness; Redis is not required for financial truth.
- **Immutable double entry:** balances are derived from signed entries; corrections create new journals.
- **Business idempotency:** a key is bound to tenant, operation, and canonical request content—not merely an HTTP response cache.
- **Source-account serialization:** deterministic row locks prevent competing transfers from overspending.
- **Evidence, not authority:** provider events and statements are preserved observations that reconciliation compares with internal state.
- **Transactional outbox:** event intent commits with the business effect, with bounded retries and dead letters.

## Verification evidence

- API tests cover tenant isolation, balanced posting, idempotent replay, key conflicts, signatures, evidence classification, reconciliation reruns, and controlled resolution.
- PostgreSQL tests directly attack invariants and exercise real concurrent transactions.
- The migration suite includes a forward repair for a trigger defect found by integration testing; history was preserved rather than rewritten.
- Browser QA verifies the canonical incident and resolution at a desktop viewport.

## Honest limitations

- All providers, tenants, funds, and incidents are fictional.
- Guided scenario creation is anonymous and subject to database-wide admission caps. Tenant access is scoped to the one-hour credential issued for that scenario. A public instance needs per-client fairness and managed retention.
- Provider signing uses one development secret; production requires per-tenant secret rotation.
- The outbox currently publishes to a local demonstration sink rather than an external broker.
- Authentication, RBAC, durable file storage, and dual approval are future production-hardening work.
- Performance results describe one local synthetic environment and are not production-scale claims.
