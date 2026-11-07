# Proof

**Every cent accounted for.**

Proof is a backend-first, fictional payment operations platform. Its first executable milestone is an immutable, tenant-scoped double-entry ledger whose balances can be reproduced from posted entries.

Proof does not move real money and is not a payment processor.

## Run locally

```powershell
Copy-Item .env.example .env
docker compose up -d database
uv sync --dev
uv run alembic upgrade head
uv run proof-api
```

Open `http://127.0.0.1:8000/docs`.

## Verify

```powershell
uv run pytest
uv run python scripts/export_openapi.py
```

## Implemented

- Health and dependency readiness endpoints with request correlation.
- Tenant-scoped accounts with fixed currencies and integer minor-unit balances.
- Atomic double-entry journal posting with deterministic entry ordering.
- Immutable posted journals and entries enforced by PostgreSQL triggers.
- Database checks for non-zero entries, unique positions, tenant consistency, and balanced posting.
- Reversals that create new linked journal transactions instead of rewriting history.
- API tests for valid posting, tenant isolation, invalid currency combinations, and unbalanced journals.

The product contract and roadmap live in `memory.md` and `docs/`.
