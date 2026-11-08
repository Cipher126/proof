from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _setup(client: TestClient) -> dict[str, str | dict]:
    tenant = client.post("/v1/demo/tenants", json={"name": "Reconciliation demo"}).json()
    tenant_id = tenant["id"]

    def account(name: str, allow_negative: bool = False) -> str:
        response = client.post(
            f"/v1/tenants/{tenant_id}/accounts",
            headers={"X-Tenant-ID": tenant_id},
            json={"name": name, "currency": "NGN", "allow_negative": allow_negative},
        )
        assert response.status_code == 201
        return response.json()["id"]

    system = account("System clearing", True)
    source = account("Merchant available")
    destination = account("Customer payable")
    fee = account("Provider fee expense")
    funding = client.post(
        f"/v1/tenants/{tenant_id}/journals",
        headers={"X-Tenant-ID": tenant_id},
        json={
            "reference": "reconciliation/funding",
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
        headers={"X-Tenant-ID": tenant_id, "Idempotency-Key": "reconcile-transfer-key"},
        json={
            "client_reference": "reconcile-order-001",
            "source_account_id": source,
            "destination_account_id": destination,
            "amount_minor": 2_000,
            "description": "Fictional settlement",
        },
    )
    assert transfer.status_code == 201
    return {
        "tenant_id": tenant_id,
        "destination": destination,
        "fee": fee,
        "transfer": transfer.json(),
    }


def _statement_payload(transfer: dict, amount: int) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "provider": "proof-simulated-payments",
        "filename": "fictional-settlement-001.json",
        "period_start": (now - timedelta(hours=1)).isoformat(),
        "period_end": (now + timedelta(hours=1)).isoformat(),
        "lines": [
            {
                "provider_reference": f"provider-{transfer['id']}",
                "client_reference": transfer["client_reference"],
                "amount_minor": amount,
                "currency": transfer["currency"],
                "status": "succeeded",
                "occurred_at": now.isoformat(),
            }
        ],
    }


def test_reconciliation_is_idempotent_and_resolves_with_adjustment(client: TestClient) -> None:
    context = _setup(client)
    tenant_id = str(context["tenant_id"])
    transfer = context["transfer"]
    headers = {"X-Tenant-ID": tenant_id}
    payload = _statement_payload(transfer, amount=1_750)

    first_import = client.post(
        f"/v1/tenants/{tenant_id}/settlements/statements", headers=headers, json=payload
    )
    assert first_import.status_code == 201, first_import.text
    assert first_import.json()["duplicate"] is False
    statement_id = first_import.json()["statement"]["id"]

    duplicate_import = client.post(
        f"/v1/tenants/{tenant_id}/settlements/statements", headers=headers, json=payload
    )
    assert duplicate_import.json()["duplicate"] is True
    assert duplicate_import.json()["statement"]["id"] == statement_id

    first_run = client.post(
        f"/v1/tenants/{tenant_id}/settlements/statements/{statement_id}/reconcile",
        headers=headers,
    )
    assert first_run.status_code == 200, first_run.text
    assert len(first_run.json()["findings"]) == 1
    finding = first_run.json()["findings"][0]
    assert finding["kind"] == "amount_mismatch"
    assert finding["expected"] == {"amount_minor": 2_000}
    assert finding["actual"] == {"amount_minor": 1_750}

    repeated_run = client.post(
        f"/v1/tenants/{tenant_id}/settlements/statements/{statement_id}/reconcile",
        headers=headers,
    )
    assert repeated_run.json()["id"] == first_run.json()["id"]
    assert repeated_run.json()["findings"][0]["id"] == finding["id"]

    resolved = client.post(
        f"/v1/tenants/{tenant_id}/reconciliation/findings/{finding['id']}/resolve",
        headers={**headers, "X-Operator-ID": "operator@proof.demo"},
        json={
            "resolution": "adjusted",
            "reason": "Provider retained a fictional NGN 2.50 fee.",
            "adjustment_description": "Recognize provider settlement fee",
            "adjustment_entries": [
                {"account_id": context["destination"], "amount_minor": -250},
                {"account_id": context["fee"], "amount_minor": 250},
            ],
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["adjustment_journal_id"] is not None

    balance = client.get(
        f"/v1/tenants/{tenant_id}/accounts/{context['destination']}/balance",
        headers=headers,
    )
    assert balance.json()["balance_minor"] == 1_750


def test_reconciliation_explains_missing_records_on_both_sides(client: TestClient) -> None:
    context = _setup(client)
    tenant_id = str(context["tenant_id"])
    transfer = context["transfer"]
    payload = _statement_payload(transfer, amount=2_000)
    payload["lines"][0]["client_reference"] = "unknown-provider-only-transfer"
    headers = {"X-Tenant-ID": tenant_id}
    statement = client.post(
        f"/v1/tenants/{tenant_id}/settlements/statements", headers=headers, json=payload
    ).json()["statement"]
    run = client.post(
        f"/v1/tenants/{tenant_id}/settlements/statements/{statement['id']}/reconcile",
        headers=headers,
    )
    assert run.status_code == 200
    assert {finding["kind"] for finding in run.json()["findings"]} == {
        "missing_internal",
        "missing_provider",
    }
