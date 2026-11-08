# Threat Model

Proof is a fictional payment-operations platform. It does not process real funds or card data, and this document does not claim regulatory certification.

## Protected assets

- Integrity of posted journal transactions and derived balances.
- Tenant isolation across accounts, transfers, evidence, and reconciliation records.
- Idempotency outcomes and transactional outbox records.
- Provider statement and webhook evidence.
- Operator identity, resolution reasons, and audit history.
- Runtime provider signing secret and database credentials.

## Trust boundaries

1. API client to FastAPI command endpoints.
2. Provider simulator to signed webhook ingress.
3. FastAPI and worker processes to PostgreSQL.
4. Operations console to documented APIs.
5. Operator resolution action to ledger adjustment posting.

## Material threats and controls

| Threat | Consequence | Current control | Remaining work |
| --- | --- | --- | --- |
| Retried or duplicated financial command | Duplicate movement | Tenant- and operation-scoped idempotency key bound to canonical request hash; outcome commits with journal and outbox | Retention policy and response-version compatibility |
| Concurrent spending | Negative protected balance | Deterministic account row locking and balance derivation within the same transaction | Benchmark contention and introduce verified projection only if needed |
| Journal mutation | Hidden accounting rewrite | PostgreSQL triggers reject update/delete of posted journals and entries; reversals create new transactions | Restrict database roles in hosted deployment |
| Cross-tenant identifier use | Data disclosure or mutation | Tenant-qualified foreign keys, server-side tenant filters, route/header agreement, not-found masking | Replace demo header with scoped credentials |
| Forged webhook | False provider evidence | HMAC-SHA256 over timestamp and raw body; constant-time comparison; bounded timestamp window | Secret rotation and per-tenant provider keys |
| Replayed webhook | Reapplied evidence | Unique provider event identity plus payload hash; exact duplicate is stable, conflicting reuse is rejected | Provider-specific retention policy |
| Out-of-order provider status | Incorrect state regression | Provider events are append-only evidence and classified against internal state rather than trusted as direct authority | Formal provider-specific transition adapters |
| Altered provider statement | False reconciliation | Canonical content hash and preserved raw evidence | Object storage and external checksum for large files |
| Unauthorized discrepancy adjustment | Fraudulent ledger entry | Explicit operator identifier, balanced adjustment, append-only audit event, original finding retained | Authentication, RBAC, dual approval for high-value actions |
| Sensitive data in logs | Credential or payload exposure | Current application logs use request IDs and omit request bodies/secrets | Central redaction tests and structured logging policy |

## Abuse cases deliberately demonstrated

- Same idempotency key with changed content.
- Two simultaneous transfers competing for insufficient funds.
- Two simultaneous retries using the same idempotency key.
- Invalid HMAC, duplicate webhook, conflicting event reuse, and stale state.
- Direct SQL attempt to post an unbalanced journal.
- Direct SQL attempt to mutate a posted entry.
- Repeated outbox failure leading to a dead letter.

## Deployment assumptions

- TLS terminates before the API.
- PostgreSQL is not publicly reachable and uses a least-privilege application role.
- Secrets are injected at runtime and never committed.
- The demo tenant contains only fictional data.
- Public deployment must disable unrestricted tenant creation or clearly isolate it as disposable demo state.
