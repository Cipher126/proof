from __future__ import annotations

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st


def _tenant(client: TestClient) -> str:
    response = client.post("/v1/demo/tenants", json={"name": "Transfer demo"})
    assert response.status_code == 201
    return response.json()["id"]


def _account(
    client: TestClient,
    tenant_id: str,
    name: str,
    *,
    allow_negative: bool = False,
) -> str:
    response = client.post(
        f"/v1/tenants/{tenant_id}/accounts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": name, "currency": "NGN", "allow_negative": allow_negative},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _balance(client: TestClient, tenant_id: str, account_id: str) -> int:
    response = client.get(
        f"/v1/tenants/{tenant_id}/accounts/{account_id}/balance",
        headers={"X-Tenant-ID": tenant_id},
    )
    assert response.status_code == 200
    return response.json()["balance_minor"]


def test_transfer_is_idempotent_and_enforces_available_funds(client: TestClient) -> None:
    tenant_id = _tenant(client)
    system = _account(client, tenant_id, "System clearing", allow_negative=True)
    source = _account(client, tenant_id, "Merchant available")
    destination = _account(client, tenant_id, "Customer payable")

    funding = client.post(
        f"/v1/tenants/{tenant_id}/journals",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "reference": "demo/funding",
            "description": "Fictional demo funding",
            "entries": [
                {"account_id": system, "amount_minor": -1_000},
                {"account_id": source, "amount_minor": 1_000},
            ],
        },
    )
    assert funding.status_code == 201

    payload = {
        "client_reference": "merchant-order-001",
        "source_account_id": source,
        "destination_account_id": destination,
        "amount_minor": 600,
        "description": "Fictional order settlement",
    }
    headers = {"X-Tenant-ID": tenant_id, "Idempotency-Key": "order-001-attempt"}
    first = client.post(f"/v1/tenants/{tenant_id}/transfers", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    assert first.headers["Idempotent-Replayed"] == "false"

    replay = client.post(f"/v1/tenants/{tenant_id}/transfers", headers=headers, json=payload)
    assert replay.status_code == 201
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json()["id"] == first.json()["id"]

    conflict_payload = {**payload, "amount_minor": 500}
    conflict = client.post(
        f"/v1/tenants/{tenant_id}/transfers", headers=headers, json=conflict_payload
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_conflict"

    insufficient = client.post(
        f"/v1/tenants/{tenant_id}/transfers",
        headers={"X-Tenant-ID": tenant_id, "Idempotency-Key": "order-002-attempt"},
        json={**payload, "client_reference": "merchant-order-002", "amount_minor": 500},
    )
    assert insufficient.status_code == 409
    assert insufficient.json()["error"]["code"] == "insufficient_funds"

    assert _balance(client, tenant_id, source) == 400
    assert _balance(client, tenant_id, destination) == 600


# Each example creates its own tenant and uses no data from earlier examples.
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    amount=st.integers(min_value=1, max_value=10**9),
    remaining=st.integers(min_value=0, max_value=10**9),
    retries=st.integers(min_value=1, max_value=5),
)
def test_transfer_replay_moves_generated_amount_once(
    client: TestClient, amount: int, remaining: int, retries: int,
) -> None:
    tenant_id = _tenant(client)
    clearing = _account(client, tenant_id, "Clearing", allow_negative=True)
    source = _account(client, tenant_id, "Source")
    destination = _account(client, tenant_id, "Destination")
    headers = {"X-Tenant-ID": tenant_id}
    base = f"/v1/tenants/{tenant_id}"
    funding = client.post(f"{base}/journals", headers=headers, json={
        "reference": "property/funding",
        "description": "Generated fictional funds",
        "entries": [
            {"account_id": clearing, "amount_minor": -(amount + remaining)},
            {"account_id": source, "amount_minor": amount + remaining},
        ],
    })
    assert funding.status_code == 201, funding.text

    headers["Idempotency-Key"] = "property-transfer-key"
    payload = {
        "client_reference": "property/transfer",
        "source_account_id": source,
        "destination_account_id": destination,
        "amount_minor": amount,
        "description": "Generated fictional transfer",
    }
    first = client.post(f"{base}/transfers", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    assert first.headers["Idempotent-Replayed"] == "false"

    conflict = client.post(f"{base}/transfers", headers=headers, json={**payload, "amount_minor": amount + 1})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_conflict"
    for _ in range(retries):
        replay = client.post(f"{base}/transfers", headers=headers, json=payload)
        assert replay.status_code == 201
        assert replay.headers["Idempotent-Replayed"] == "true"
        assert replay.json() == first.json()
    assert _balance(client, tenant_id, source) == remaining
    assert _balance(client, tenant_id, destination) == amount
