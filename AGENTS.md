# Proof Agent Contract

This repository builds **Proof**, a fault-tolerant payment ledger and reconciliation platform. Preserve that identity unless the user explicitly changes it.

## Required reading order

Before planning or changing implementation, read:

1. `memory.md`
2. `docs/PRODUCT.md`
3. `docs/DOMAIN.md`
4. `docs/ARCHITECTURE.md`
5. `docs/DECISIONS.md`
6. `docs/QUALITY.md`
7. `docs/ROADMAP.md`
8. `.agents/skills/senior-software-architect/SKILL.md`

Read the skill references only when their routing instructions apply.

## Authority

- The user's latest explicit instruction has highest authority.
- `memory.md` records durable product intent and approved constraints.
- `docs/DOMAIN.md` owns financial invariants.
- Accepted entries in `docs/DECISIONS.md` own architectural choices.
- `docs/ROADMAP.md` controls current scope and milestone order.
- Implementation must conform to these documents; update the relevant document in the same change when an approved decision changes.

## Non-negotiable working rules

- Do not silently rename, reposition, or broaden Proof.
- Do not turn Proof into a generic wallet, payment gateway clone, neobank UI, or CRUD demo.
- Do not represent simulated providers, money, benchmarks, or deployments as real.
- Prefer correctness, auditability, recoverability, and explainability over feature count.
- Keep the architecture deployable by one developer. Add a distributed component only when a measured requirement or failure boundary justifies it.
- Record a consequential or difficult-to-reverse decision in `docs/DECISIONS.md` before implementing it.
- Preserve double-entry and idempotency invariants in every write path.
- Complete and verify one milestone before expanding the next.

## Completion standard

A feature is complete only when its domain behavior, failure behavior, authorization, observability, tests, documentation, and demo path are coherent. Passing a happy-path request alone is insufficient.
