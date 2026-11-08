from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from proof.config import settings


def _setup_transfer(client: TestClient) -> tuple[str, dict]:
    tenant_response = client.post("/v1/demo/tenants", json={"name": "Provider evidence demo"})
    tenant_id = tenant_response.json()["id"]

    def account(name: str, allow_negative: bool = False) -> str:
        response = client.post(
            f"/v1/tenants/{tenant_id}/accounts",
            headers={"X-Tenant-ID": tenant_id},
            json={"name": name, "currency": "NGN", "allow_negative": allow_negative},
        )
        assert response.status_code == 201
        return response.json()["id"]

    system = account("System", True)
    source = account("Merchant")
    destination = account("Customer")
    funding = client.post(
        f"/v1/tenants/{tenant_id}/journals",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "reference": "provider/funding",
            "description": "Fictional funds",
            "entries": [
                {"account_id": system, "amount_minor": -2_500},
                {"account_id": source, "amount_minor": 2_500},
            ],
        },
    )
    assert funding.status_code == 201
    transfer = client.post(
        f"/v1/tenants/{tenant_id}/transfers",
        headers={"X-Tenant-ID": tenant_id, "Idempotency-Key": "provider-transfer-key"},
        json={
            "client_reference": "provider-order-001",
            "source_account_id": source,
            "destination_account_id": destination,
            "amount_minor": 2_000,
            "description": "Fictional provider-observed transfer",
        },
    )
    assert transfer.status_code == 201, transfer.text
    return tenant_id, transfer.json()


def _signed_headers(tenant_id: str, event_id: str, body: bytes) -> dict[str, str]:
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    message = timestamp.encode("ascii") + b"." + body
    signature = hmac.new(
        settings.simulated_provider_secret.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()
    return {
        "X-Tenant-ID": tenant_id,
        "X-Proof-Event-ID": event_id,
        "X-Proof-Timestamp": timestamp,
        "X-Proof-Signature": signature,
        "Content-Type": "application/json",
    }


def _body(transfer: dict, *, status: str = "succeeded", amount: int | None = None) -> bytes:
    return json.dumps(
        {
            "event_type": "transfer.status_changed",
            "provider_transfer_id": f"provider-{transfer['id']}",
            "client_reference": transfer["client_reference"],
            "amount_minor": amount if amount is not None else transfer["amount_minor"],
            "currency": transfer["currency"],
            "status": status,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_signed_provider_events_are_deduplicated_and_classified(client: TestClient) -> None:
    tenant_id, transfer = _setup_transfer(client)
    url = f"/v1/tenants/{tenant_id}/providers/simulated/webhooks"
    body = _body(transfer)
    headers = _signed_headers(tenant_id, "provider-event-001", body)

    first = client.post(url, headers=headers, content=body)
    assert first.status_code == 200, first.text
    assert first.json()["duplicate"] is False
    assert first.json()["event"]["classification"] == "matched"

    duplicate = client.post(url, headers=headers, content=body)
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["event"]["id"] == first.json()["event"]["id"]

    changed = _body(transfer, amount=transfer["amount_minor"] - 250)
    changed_response = client.post(
        url,
        headers=_signed_headers(tenant_id, "provider-event-001", changed),
        content=changed,
    )
    assert changed_response.status_code == 409
    assert changed_response.json()["error"]["code"] == "provider_event_conflict"

    older_state = _body(transfer, status="submitted")
    older_response = client.post(
        url,
        headers=_signed_headers(tenant_id, "provider-event-002", older_state),
        content=older_state,
    )
    assert older_response.status_code == 200
    assert older_response.json()["event"]["classification"] == "ignored_out_of_order"

    invalid = client.post(
        url,
        headers={**_signed_headers(tenant_id, "provider-event-003", body), "X-Proof-Signature": "0" * 64},
        content=body,
    )
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "invalid_provider_signature"

    timeline = client.get(
        f"/v1/tenants/{tenant_id}/operations/transfers/{transfer['id']}/timeline",
        headers={"X-Tenant-ID": tenant_id},
    )
    assert timeline.status_code == 200, timeline.text
    kinds = {item["kind"] for item in timeline.json()["items"]}
    assert kinds == {"transfer", "journal", "outbox", "provider_evidence"}


def test_demo_provider_scenario_exposes_amount_conflict(client: TestClient) -> None:
    tenant_id, transfer = _setup_transfer(client)
    response = client.post(
        f"/v1/tenants/{tenant_id}/demo/provider-events",
        headers={"X-Tenant-ID": tenant_id},
        json={"client_reference": transfer["client_reference"], "scenario": "amount_mismatch"},
    )
    assert response.status_code == 200
    assert response.json()["event"]["classification"] == "conflict"
