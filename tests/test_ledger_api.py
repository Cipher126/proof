from __future__ import annotations

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st


def tenant(client: TestClient, name: str = "Northstar Demo") -> str:
    response = client.post("/v1/demo/tenants", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def account(client: TestClient, tenant_id: str, name: str, currency: str = "NGN") -> str:
    response = client.post(
        f"/v1/tenants/{tenant_id}/accounts",
        headers={"X-Tenant-ID": tenant_id},
        json={"name": name, "currency": currency},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_posts_balanced_journal_and_derives_balances(client: TestClient) -> None:
    tenant_id = tenant(client)
    cash = account(client, tenant_id, "Provider clearing")
    merchant = account(client, tenant_id, "Merchant payable")

    response = client.post(
        f"/v1/tenants/{tenant_id}/journals",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "reference": "demo/funding/001",
            "description": "Fictional opening movement",
            "entries": [
                {"account_id": cash, "amount_minor": -2_500_000},
                {"account_id": merchant, "amount_minor": 2_500_000},
            ],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "posted"
    assert sum(entry["amount_minor"] for entry in response.json()["entries"]) == 0

    balance = client.get(
        f"/v1/tenants/{tenant_id}/accounts/{merchant}/balance",
        headers={"X-Tenant-ID": tenant_id},
    )
    assert balance.json() == {
        "account_id": merchant,
        "currency": "NGN",
        "balance_minor": 2_500_000,
    }


def test_rejects_unbalanced_journal(client: TestClient) -> None:
    tenant_id = tenant(client)
    one = account(client, tenant_id, "One")
    two = account(client, tenant_id, "Two")
    response = client.post(
        f"/v1/tenants/{tenant_id}/journals",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "reference": "bad/001",
            "description": "Must fail",
            "entries": [
                {"account_id": one, "amount_minor": -100},
                {"account_id": two, "amount_minor": 99},
            ],
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unbalanced_journal"


def test_tenant_header_and_resource_boundaries(client: TestClient) -> None:
    tenant_a = tenant(client, "Tenant A")
    tenant_b = tenant(client, "Tenant B")
    account_a = account(client, tenant_a, "A cash")

    mismatch = client.get(
        f"/v1/tenants/{tenant_a}/accounts/{account_a}/balance",
        headers={"X-Tenant-ID": tenant_b},
    )
    assert mismatch.status_code == 403

    hidden = client.get(
        f"/v1/tenants/{tenant_b}/accounts/{account_a}/balance",
        headers={"X-Tenant-ID": tenant_b},
    )
    assert hidden.status_code == 404


def test_rejects_cross_currency_balancing(client: TestClient) -> None:
    tenant_id = tenant(client)
    ngn = account(client, tenant_id, "NGN cash", "NGN")
    usd = account(client, tenant_id, "USD cash", "USD")
    response = client.post(
        f"/v1/tenants/{tenant_id}/journals",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "reference": "bad/fx",
            "description": "Implicit FX is forbidden",
            "entries": [
                {"account_id": ngn, "amount_minor": -100},
                {"account_id": usd, "amount_minor": 100},
            ],
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unbalanced_journal"


# Each example creates its own tenant and uses no data from earlier examples.
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    credits=st.lists(st.integers(min_value=1, max_value=10**9), min_size=1, max_size=8),
    discrepancy=st.integers(min_value=1, max_value=10**6),
)
def test_journal_conserves_generated_amounts(client: TestClient, credits: list[int], discrepancy: int) -> None:
    tenant_id = tenant(client)
    source = account(client, tenant_id, "Clearing")
    destination = account(client, tenant_id, "Payable")
    headers = {"X-Tenant-ID": tenant_id}
    base = f"/v1/tenants/{tenant_id}"
    total = sum(credits)
    payload = {
        "reference": "property/funding",
        "description": "Generated fictional journal",
        "entries": [
            {"account_id": source, "amount_minor": -total - discrepancy},
            *({"account_id": destination, "amount_minor": credit} for credit in credits),
        ],
    }
    rejected = client.post(f"{base}/journals", headers=headers, json=payload)
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "unbalanced_journal"

    payload["entries"][0]["amount_minor"] = -total
    posted = client.post(f"{base}/journals", headers=headers, json=payload)
    assert posted.status_code == 201, posted.text
    assert sum(entry["amount_minor"] for entry in posted.json()["entries"]) == 0
    for account_id, expected in ((source, -total), (destination, total)):
        balance = client.get(f"{base}/accounts/{account_id}/balance", headers=headers)
        assert balance.status_code == 200
        assert balance.json()["balance_minor"] == expected
