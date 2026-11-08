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

## ADR-005: Serialize protected spending on the source account

- **Status:** Accepted
- **Context:** Two concurrent transfers must not both observe and spend the same available funds.
- **Decision:** Lock involved account rows in deterministic identifier order, derive the source balance from posted entries inside that transaction, enforce the account's negative-balance policy, and commit the transfer, journal, idempotency outcome, and outbox event atomically.
- **Alternatives:** Application-only balance checks; serializable isolation for every financial command; a mutable balance as the sole authority.
- **Consequences:** Correctness is straightforward and measurable. A highly contended source account can become a serialization point, while derived-balance queries will eventually need a verified projection optimization.
- **Evidence:** PostgreSQL concurrency tests must prove that competing transfers cannot overspend.
- **Revisit when:** Measured lock waits or balance-query costs exceed the target workload.

## ADR-006: Persist business idempotency with command effects

- **Status:** Accepted
- **Context:** Clients retry timed-out requests and may reuse a key with different content.
- **Decision:** Bind each idempotency key to tenant, operation, and a canonical request hash. Persist its resource outcome in the same database transaction as the financial effect and outbox event.
- **Alternatives:** Cache-only keys; HTTP response caching; provider-generated deduplication.
- **Consequences:** Retries remain deterministic across process restarts. Records require retention policy and careful response evolution.
- **Revisit when:** Retention volume or multi-region command routing requires a different coordination model.

## ADR-007: Issue a short-lived credential for each guided demo tenant

- **Status:** Accepted
- **Context:** An anonymous visitor needs to inspect and resolve their fictional incident without accessing another visitor's records.
- **Decision:** Return one random bearer credential when a scenario is created. Store only its SHA-256 verifier, public ID, tenant and expiry. Require it for tenant routes in Compose and derive the audit actor from its public ID. Keep header-based fixtures confined to the explicit local development mode.
- **Alternatives:** Public tenant IDs as credentials, or an account and login flow for the guided demo.
- **Consequences:** Each visitor can operate their own fictional tenant without signing up. Refreshing the browser loses the in-memory credential. A hosted deployment still needs resource limits and a demo-data retention policy.
- **Evidence:** Reject missing, invalid, expired and cross-tenant credentials. Resolve the incident with a valid credential and verify that spoofed operator headers do not affect audit attribution.
- **Revisit when:** Real users need long-lived identities, separately delegated roles, or account recovery.

## ADR template

### ADR-NNN: Decision title

- **Status:** Proposed | Accepted | Superseded
- **Context:**
- **Decision:**
- **Alternatives:**
- **Consequences:**
- **Evidence:**
- **Revisit when:**
