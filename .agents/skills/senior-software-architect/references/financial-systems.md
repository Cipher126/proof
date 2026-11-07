# Financial Systems Guidance

Use for ledger, payment, settlement, or reconciliation changes.

## Preserve evidence

Financial state must be explainable from immutable business records. Do not repair history by updating posted entries, deleting provider evidence, or rewriting imported statements. Corrections are new, linked records.

## Separate concepts

- A payment intent or transfer is a business workflow.
- A journal transaction is an accounting effect.
- A provider event is external evidence.
- A settlement is an aggregation and obligation lifecycle.
- A reconciliation finding is an observation about disagreement.

Do not collapse these into one status-heavy table.

## Concurrency and idempotency

Choose and test the balance protection mechanism explicitly. Common valid approaches include locked balance rows, serializable transactions with retry, or invariant-preserving database updates. The correct choice depends on workload and schema; application checks without database coordination are insufficient.

Bind idempotency to tenant, operation, key, and normalized semantic payload. Persist enough outcome data to make retries deterministic, including known failures where retrying the same command must not create a new effect.

## Reconciliation

Matching rules must be deterministic and explainable. Use exact identifiers and amounts before heuristic signals. Keep ambiguous cases unresolved for operator review. A rerun over unchanged evidence must not multiply findings or adjustments.

## Claims and demonstrations

Label simulated funds, providers, and incidents clearly. Do not describe a sandbox as a regulated payment processor or imply compliance certifications. Describe implemented controls and threat assumptions precisely rather than claiming broad compliance.
