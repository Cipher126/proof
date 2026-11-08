# Operations Runbook

## First response

1. Record the request or correlation ID and UTC time.
2. Check `/health` for process liveness and `/ready` for database availability.
3. Preserve evidence before retrying or editing state.
4. Prefer bounded replay or a new compensating record; never edit posted financial history.

## Database unavailable

**Signal:** `/health` succeeds while `/ready` fails; financial commands return dependency errors.

- Stop automated retries that could amplify connection pressure.
- Confirm PostgreSQL availability, credentials, pool saturation, and migration head.
- Restore the dependency before accepting financial commands.
- Retry only commands with a client idempotency key.
- Verify the original idempotency record before assuming a timed-out command failed.

## Outbox backlog

**Signal:** unpublished events accumulate or `last_error` repeats.

- Inspect event type, attempt count, next attempt, and last error.
- Repair the destination or adapter before replay.
- Run `uv run proof-worker --once` for one bounded batch.
- Confirm `published_at` is set once and the business transaction remains unchanged.

## Dead-lettered outbox event

- Preserve the event payload and error.
- Determine whether the destination can safely accept a replay.
- Do not reset attempts blindly; a future administrative replay command must create an audit event.
- Reconcile downstream state after recovery.

## Provider webhook disagreement

- Verify signature classification, event identity, timestamp, and payload hash.
- Compare the internal transfer, provider event, and statement evidence.
- Treat out-of-order evidence as an observation, not authority to regress state.
- Open or rerun reconciliation using unchanged statement evidence.

## Reconciliation finding

- Read the finding's expected and actual evidence.
- For a timing difference, wait for the documented window and rerun unchanged evidence.
- For a real fee or correction, post a balanced adjustment through the resolution endpoint.
- Supply an operator identity and meaningful reason.
- Verify the original finding remains, the adjustment journal balances, and an audit event exists.

## Migration recovery

- Migrations are forward-only in normal operation.
- Test upgrades on a copy of production data before deployment.
- If an upgrade fails transactionally, fix forward and rerun.
- Do not downgrade across a migration that has accepted new financial writes unless a reviewed data migration exists.

## Local validation sequence

```powershell
docker compose up -d database
uv sync --dev
uv run alembic upgrade head
uv run pytest
uv run pytest -m integration
cd dashboard
npm ci
npm run build
```
