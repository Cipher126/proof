from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections.abc import Callable
import uuid

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from proof.messaging.models import OutboxEvent
from proof.errors import NotFoundError, ProofError
from proof.operations.models import AuditEvent


class DeliveryFailure(Exception):
    """A retryable, safe-to-persist delivery error."""


def dispatch_batch(
    session: Session,
    *,
    now: datetime | None = None,
    batch_size: int = 100,
    fail_event_types: set[str] | None = None,
    max_attempts: int = 3,
    deliver: Callable[[OutboxEvent], None] | None = None,
) -> dict[str, int]:
    """Dispatch due events, using the local sink when no external adapter is configured."""
    if deliver is not None and batch_size != 1:
        raise ValueError("external delivery holds one event lock per transaction")
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
        try:
            if event.event_type in fail_event_types:
                raise DeliveryFailure("injected demo delivery failure")
            if deliver is not None:
                traceparent = event.payload.get("traceparent")
                carrier = {"traceparent": traceparent} if isinstance(traceparent, str) else {}
                context = TraceContextTextMapPropagator().extract(carrier)
                with trace.get_tracer(__name__).start_as_current_span(
                    "proof.outbox.deliver", context=context, kind=trace.SpanKind.PRODUCER,
                ) as span:
                    span.set_attribute("messaging.message.id", str(event.id))
                    deliver(event)
        except DeliveryFailure as exc:
            result["failed"] += 1
            event.last_error = str(exc)
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


def requeue_dead_letter(
    session: Session, tenant_id: uuid.UUID, event_id: uuid.UUID, *, actor: str, reason: str,
) -> None:
    event = session.scalar(select(OutboxEvent).where(
        OutboxEvent.tenant_id == tenant_id, OutboxEvent.id == event_id,
    ).with_for_update())
    if event is None:
        raise NotFoundError("outbox event")
    if event.dead_lettered_at is None or event.published_at is not None:
        raise ProofError("outbox_not_dead_lettered", "only dead-lettered events can be requeued", 409)
    session.add(AuditEvent(
        tenant_id=tenant_id, actor=actor, action="outbox.requeued", resource_type="outbox_event",
        resource_id=event.id, reason=reason, details={"previous_attempts": event.attempts},
    ))
    event.attempts = 0
    event.dead_lettered_at = None
    event.next_attempt_at = None
    event.last_error = None
    session.commit()
