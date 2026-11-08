from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from proof.config import settings
from proof.errors import NotFoundError, ProofError
from proof.ledger import service as ledger_service
from proof.payments.models import Transfer
from proof.providers.models import ProviderEvent
from proof.providers.schemas import ProviderWebhook

PROVIDER = "proof-simulated-payments"
SIGNATURE_TOLERANCE = timedelta(minutes=5)


def sign_payload(timestamp: str, body: bytes) -> str:
    message = timestamp.encode("ascii") + b"." + body
    return hmac.new(
        settings.simulated_provider_secret.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()


def _classify(transfer: Transfer | None, payload: ProviderWebhook) -> str:
    if transfer is None:
        return "unmatched"
    if transfer.amount_minor != payload.amount_minor or transfer.currency != payload.currency:
        return "conflict"
    if payload.status == transfer.status:
        return "matched"
    if transfer.status == "succeeded" and payload.status in {"submitted", "failed"}:
        return "ignored_out_of_order"
    return "observed"


def ingest_webhook(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    event_id: str,
    timestamp: str,
    signature: str,
    body: bytes,
    now: datetime | None = None,
) -> tuple[ProviderEvent, bool]:
    ledger_service.require_tenant(session, tenant_id)
    now = now or datetime.now(timezone.utc)
    try:
        provider_time = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ProofError("invalid_provider_timestamp", "provider timestamp is invalid", 401) from exc
    if abs(now - provider_time) > SIGNATURE_TOLERANCE:
        raise ProofError("stale_provider_event", "provider timestamp is outside the replay window", 401)
    expected = sign_payload(timestamp, body)
    if not hmac.compare_digest(expected, signature.lower()):
        raise ProofError("invalid_provider_signature", "provider signature is invalid", 401)
    payload_hash = hashlib.sha256(body).hexdigest()
    existing = session.scalar(
        select(ProviderEvent).where(
            ProviderEvent.tenant_id == tenant_id,
            ProviderEvent.provider == PROVIDER,
            ProviderEvent.event_id == event_id,
        )
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise ProofError(
                "provider_event_conflict",
                "the provider event ID was already used with different content",
                409,
            )
        return existing, True
    try:
        decoded = json.loads(body)
        payload = ProviderWebhook.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ProofError("invalid_provider_payload", "provider payload is invalid") from exc
    transfer = session.scalar(
        select(Transfer).where(
            Transfer.tenant_id == tenant_id,
            Transfer.client_reference == payload.client_reference,
        )
    )
    event = ProviderEvent(
        tenant_id=tenant_id,
        provider=PROVIDER,
        event_id=event_id,
        event_type=payload.event_type,
        provider_transfer_id=payload.provider_transfer_id,
        client_reference=payload.client_reference,
        amount_minor=payload.amount_minor,
        currency=payload.currency,
        provider_status=payload.status,
        payload_hash=payload_hash,
        raw_payload=decoded,
        classification=_classify(transfer, payload),
        transfer_id=transfer.id if transfer else None,
        provider_timestamp=provider_time,
        received_at=now,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event, False


def build_demo_event(
    session: Session,
    tenant_id: uuid.UUID,
    client_reference: str,
    scenario: str,
    now: datetime | None = None,
) -> tuple[ProviderEvent, bool]:
    now = now or datetime.now(timezone.utc)
    transfer = session.scalar(
        select(Transfer).where(
            Transfer.tenant_id == tenant_id,
            Transfer.client_reference == client_reference,
        )
    )
    if transfer is None:
        raise NotFoundError("transfer")
    status = "succeeded"
    amount = transfer.amount_minor
    if scenario == "out_of_order":
        status = "submitted"
    elif scenario == "amount_mismatch":
        amount = 2 if amount == 1 else amount - max(1, min(25_000, amount // 100))
    event_id = f"demo-{scenario}-{transfer.id}"
    payload = {
        "event_type": "transfer.status_changed",
        "provider_transfer_id": f"provider-{transfer.id}",
        "client_reference": transfer.client_reference,
        "amount_minor": amount,
        "currency": transfer.currency,
        "status": status,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(now.timestamp()))
    return ingest_webhook(
        session,
        tenant_id,
        event_id=event_id,
        timestamp=timestamp,
        signature=sign_payload(timestamp, body),
        body=body,
        now=now,
    )
