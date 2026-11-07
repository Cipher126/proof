# Product Brief

## Problem

Payment systems receive imperfect information. Clients retry timed-out requests, providers deliver duplicate or delayed webhooks, concurrent operations compete for the same funds, and settlement files can disagree with internal records. A successful HTTP response is not proof that the accounting is correct.

Proof is a sandbox payment-operations platform that records money movement in an immutable ledger and continuously proves whether internal and provider records agree.

## Primary users

- **Backend integrator:** submits idempotent payment commands and consumes stable API contracts.
- **Payment operator:** monitors transfers, settlements, and discrepancies and performs controlled recovery actions.
- **Auditor or engineering reviewer:** traces a balance to its journal entries, actor, request, provider evidence, and resolution history.

## Core jobs

1. Create tenant-owned ledger accounts with explicit currencies and purposes.
2. Move simulated funds through balanced journal transactions.
3. Accept retried commands without duplicating financial effects.
4. Receive and authenticate provider events without trusting delivery order or uniqueness.
5. Compare internal expectations with provider statements.
6. Explain discrepancies and resolve them without rewriting history.

## Canonical demo story

1. A merchant initiates a NGN 25,000 transfer with an idempotency key.
2. Proof atomically writes the transfer, balanced journal entries, and an outbox event.
3. The client retries the same request and receives the original result.
4. A simulated provider sends duplicate and out-of-order callbacks; Proof records them but applies the valid transition once.
5. A statement import intentionally reports NGN 24,750.
6. Reconciliation flags a NGN 250 fee mismatch with evidence from both sides.
7. An operator resolves the discrepancy through a controlled adjustment that creates new entries and an audit event.
8. The final screen proves the account balance, settlement state, and complete causal timeline.

## Product principles

- Make correctness visible.
- Explain every state transition.
- Never mutate financial history to make records appear correct.
- Use realistic failure modes without pretending demo data is real.
- Keep operator actions deliberate, authorized, and auditable.

## Portfolio presentation

The public experience should lead with the interactive guided incident, then reveal architecture, invariants, tests, benchmarks, and tradeoffs. Avoid unsupported scale claims, invented customers, or generic feature marketing.
