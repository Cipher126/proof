# Proof

**Every cent accounted for.**

Proof is a backend-first, fictional payment operations platform. Its first executable milestone is an immutable, tenant-scoped double-entry ledger whose balances can be reproduced from posted entries.

Proof does not move real money and is not a payment processor.

## Run the local demo

With Docker Desktop running, open PowerShell in the project folder and run:

```powershell
docker compose up --build -d
```

Open [Proof](http://127.0.0.1:18080/) and click **Run guided incident**. Compare the
₦25,000 transfer with the ₦24,750 provider statement, then post the ₦250 adjustment.
The [API contract](http://127.0.0.1:18080/docs) is available in the same process.
Compose applies migrations before starting the API. Run `docker compose stop` to
stop the services and retain the demo database.

This configuration binds to loopback. Each guided incident issues a tenant-scoped
bearer credential that expires after one hour. The browser keeps it in memory,
so refreshing the page starts a new session. See [the threat model](docs/THREAT_MODEL.md)
for the public-hosting gates.

## Run from source

The source workflow defaults to development mode, which enables fixture and
integration endpoints. Use it on localhost with fictional data.

```powershell
docker compose up -d database
uv sync --frozen
uv run alembic upgrade head
uv run proof-api
```

Open `http://127.0.0.1:8000/docs`.

Build the desktop-first operations console with:

```powershell
cd dashboard
npm ci
npm run build
cd ..
uv run proof-api
```

Then open `http://127.0.0.1:8000/` and run the guided fictional incident.

## Verify

```powershell
uv run pytest
uv run pytest -m integration
uv run python scripts/export_openapi.py
```

The PostgreSQL suite creates and migrates an isolated schema and removes it after
the tests. The configured database role needs permission to create a schema.

For portfolio review, start with the [engineering case study](docs/CASE_STUDY.md).
The [decision log](docs/DECISIONS.md), [runbook](docs/RUNBOOK.md), and
[benchmark notes](docs/benchmarks/README.md) cover the tradeoffs and operating limits.

## Implemented

- Health and dependency readiness endpoints with request correlation.
- Tenant-scoped accounts with fixed currencies and integer minor-unit balances.
- Atomic double-entry journal posting with deterministic entry ordering.
- Immutable posted journals and entries enforced by PostgreSQL triggers.
- Database checks for non-zero entries, unique positions, tenant consistency, and balanced posting.
- Reversals that create new linked journal transactions instead of rewriting history.
- API tests for valid posting, tenant isolation, invalid currency combinations, and unbalanced journals.
- Idempotent transfers with canonical request hashing and conflict detection.
- Source-account locking and available-funds enforcement under concurrent PostgreSQL transactions.
- Transactional outbox events committed atomically with transfer and ledger effects.
- Timestamped HMAC provider webhooks with payload-bound replay protection.
- Append-only provider evidence classified as matched, conflicting, unmatched, or out of order.
- Recoverable outbox dispatch with exponential backoff, injected failures, and dead letters.
- A causal transfer timeline joining business state, journal proof, outbox delivery, and provider evidence.
- Content-addressed provider statement evidence with idempotent imports and reruns.
- Explainable reconciliation findings for missing, duplicated, mismatched, and unexpected records.
- Audited operator resolution that posts new balanced adjustments rather than rewriting history.

The product contract and roadmap live in `memory.md` and `docs/`.
