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
| Cross-tenant identifier use | Data disclosure or mutation | Tenant-scoped expiring bearer credential in sandbox mode, tenant-qualified foreign keys, and server-side tenant filters | Review remaining database associations before broader use |
| Forged webhook | False provider evidence | HMAC-SHA256 over timestamp and raw body; constant-time comparison; bounded timestamp window | Secret rotation and per-tenant provider keys |
| Replayed webhook | Reapplied evidence | Unique provider event identity plus payload hash; exact duplicate is stable, conflicting reuse is rejected | Provider-specific retention policy |
| Out-of-order provider status | Incorrect state regression | Provider events are append-only evidence and classified against internal state rather than trusted as direct authority | Formal provider-specific transition adapters |
| Altered provider statement | False reconciliation | Canonical content hash and preserved raw evidence | Object storage and external checksum for large files |
| Unauthorized discrepancy adjustment | Fraudulent ledger entry | Sandbox audit actor derived from the authenticated credential, with a balanced adjustment and append-only audit event | Named user accounts, RBAC and dual approval for real operators |
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
- The packaged sandbox disables generic tenant creation, arbitrary journal writes, and arbitrary adjustments. Its guided adjustment derives the amount and accounts from the stored scenario.
- PostgreSQL limits anonymous creation to one concurrent setup, 60 scenarios per hour, and 2,000 retained scenarios per dedicated demo database. Public operation still needs per-client fairness and a retention plan.
