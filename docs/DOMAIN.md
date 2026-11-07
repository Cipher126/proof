# Domain Model and Financial Invariants

This document owns Proof's financial rules. Code and database constraints must enforce them together.

## Money representation

- Store amounts as integers in the currency's minor unit.
- Never use binary floating point for money.
- Every account has exactly one currency; cross-currency movement requires an explicit conversion transaction and rate evidence.
- Currency metadata defines the valid minor-unit scale.

## Ledger model

- Journal transactions are immutable after posting.
- Each journal transaction contains at least two entries.
- The signed sum of entries for each currency in one journal transaction is zero.
- Balances are derived from posted entries. Any cached balance is an optimization and must be reproducible.
- Corrections create reversing or adjusting transactions; they never edit or delete posted entries.
- Domain records reference their resulting journal transaction IDs.

## Command invariants

- A tenant-scoped idempotency key identifies one command and normalized request payload.
- Reusing a key with an equivalent payload returns the original outcome.
- Reusing a key with a materially different payload is rejected.
- Idempotency, domain mutation, journal posting, and outbox creation commit atomically.
- Concurrent commands cannot overspend a balance when the account policy forbids it.

## State machines

Transfers use explicit transitions. Initial target model:

`created -> authorized -> submitted -> succeeded`

Failure branches may include `failed`, `cancelled`, `expired`, and `reversed`. A transition must define:

- valid source states;
- initiating actor or evidence;
- ledger effect, if any;
- retry semantics;
- emitted event;
- audit record.

Provider events are evidence, not direct authority. Signature validity, tenant/provider binding, event identity, causal rules, and current state determine whether an event may cause a transition.

## Reconciliation

- Preserve the imported statement and its content hash as evidence.
- Match records deterministically where possible and score or queue ambiguous cases rather than guessing.
- Distinguish missing internal record, missing provider record, amount mismatch, currency mismatch, duplicate, timing difference, and unexpected state.
- Reconciliation findings are append-only observations with a lifecycle; resolving one records who acted, why, and what compensating entries or mappings were created.
- Rerunning reconciliation over unchanged evidence is idempotent.

## Multi-tenancy and audit

- Every tenant-owned record carries an enforced tenant boundary.
- Credentials are stored only as non-reversible verifiers plus public identifiers.
- Audit events are append-only and exclude secrets and unnecessary payload data.
- Operator actions record actor, tenant, action, resource, reason, request correlation, and timestamp.

## Required invariant tests

- Property tests that generated journal transactions always balance.
- Concurrent debit tests that prove the configured overdraft rule.
- Idempotency tests for identical, conflicting, racing, and failed requests.
- State-machine tests for every permitted and forbidden transition.
- Reconciliation replay tests that prove stable findings.
- Database-level tests that bypass service code and confirm constraints reject invalid records.
