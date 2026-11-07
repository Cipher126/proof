# Architecture Decision Log

Record consequential and difficult-to-reverse choices here before implementation. Each entry must state context, decision, alternatives, consequences, and evidence that would trigger reconsideration.

## ADR-001: Build Proof as a modular monolith

- **Status:** Accepted
- **Context:** Financial commands need coherent transactions and the project is owned by one developer. Distributed services would add failure modes without an established scaling or team boundary.
- **Decision:** Use one repository and domain model with explicit modules and separately runnable API/worker roles.
- **Alternatives:** Microservices per domain; a single unstructured application package.
- **Consequences:** Strong transactional boundaries and simpler deployment; module boundaries require deliberate enforcement.
- **Revisit when:** Measured scaling, security isolation, ownership, or release independence cannot be handled by process separation and database design.

## ADR-002: PostgreSQL is the financial source of truth

- **Status:** Accepted
- **Context:** Ledger and payment state require transactions, constraints, durable evidence, and reproducible history.
- **Decision:** Store authoritative state, idempotency, outbox records, and reconciliation evidence in PostgreSQL. Redis must not determine balances or final state.
- **Alternatives:** Redis-led state; event broker as primary ledger; separate event store from the first release.
- **Consequences:** Clear consistency model; careful indexing, locking, and archival are required.
- **Revisit when:** Verified workloads or retention constraints exceed the chosen design and a migration preserves the same invariants.

## ADR-003: Use immutable double-entry journals

- **Status:** Accepted
- **Context:** Mutable balances cannot explain or independently verify historical movement.
- **Decision:** Post balanced, immutable journal transactions and derive balances from entries. Corrections use new reversing or adjustment entries.
- **Alternatives:** Mutable account balance rows with transaction history; single-sided transaction records.
- **Consequences:** Strong auditability and reproducibility; domain operations must model accounting explicitly.

## ADR-004: Simulate providers in the core portfolio release

- **Status:** Accepted
- **Context:** The project must be safe, deterministic, inexpensive to run, and publicly demonstrable without claiming real-money processing.
- **Decision:** Build realistic provider adapters and a deterministic failure simulator. Clearly label all funds and providers as fictional.
- **Alternatives:** Production payment integration; static mocked screenshots.
- **Consequences:** Repeatable demonstrations and failure testing; adapters must remain plausible and contract-driven.
- **Revisit when:** A sandbox integration adds hiring value without weakening reliability or requiring sensitive production access.

## ADR template

### ADR-NNN: Decision title

- **Status:** Proposed | Accepted | Superseded
- **Context:**
- **Decision:**
- **Alternatives:**
- **Consequences:**
- **Evidence:**
- **Revisit when:**
