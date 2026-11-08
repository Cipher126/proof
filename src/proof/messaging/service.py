from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from proof.messaging.models import OutboxEvent


def dispatch_batch(
    session: Session,
    *,
    now: datetime | None = None,
    batch_size: int = 100,
    fail_event_types: set[str] | None = None,
    max_attempts: int = 3,
) -> dict[str, int]:
    """Dispatch one durable batch to the local demo event sink.

    The current portfolio milestone models publication by atomically marking the event.
    A broker adapter can replace this sink without changing outbox ownership semantics.
    """
    now = now or datetime.now(timezone.utc)
    fail_event_types = fail_event_types or set()
    events = session.scalars(
        select(OutboxEvent)
        .where(
            OutboxEvent.published_at.is_(None),
            OutboxEvent.dead_lettered_at.is_(None),
            or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
        )
        .order_by(OutboxEvent.occurred_at, OutboxEvent.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    ).all()
    result = {"processed": 0, "published": 0, "failed": 0, "dead_lettered": 0}
    for event in events:
        result["processed"] += 1
        event.attempts += 1
        if event.event_type in fail_event_types:
            result["failed"] += 1
            event.last_error = "injected demo delivery failure"
            if event.attempts >= max_attempts:
                event.dead_lettered_at = now
                event.next_attempt_at = None
                result["dead_lettered"] += 1
            else:
                event.next_attempt_at = now + timedelta(seconds=2**event.attempts)
            continue
        event.published_at = now
        event.next_attempt_at = None
        event.last_error = None
        result["published"] += 1
    session.commit()
    return result
