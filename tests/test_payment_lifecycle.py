from fastapi.testclient import TestClient


def test_hold_capture_fee_and_partial_refunds(client: TestClient):
    tenant = client.post("/v1/demo/tenants", json={"name": "Lifecycle demo"}).json()["id"]
    root = f"/v1/tenants/{tenant}"
    headers = {"X-Tenant-ID": tenant}

    def account(name: str) -> str:
        response = client.post(f"{root}/accounts", headers=headers, json={"name": name, "currency": "NGN"})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    clearing, source, recipient, fee = map(account, ("Clearing", "Source", "Recipient", "Fee"))
    assert client.post(f"{root}/journals", headers=headers, json={
        "reference": "funding", "description": "Initial funding",
        "entries": [{"account_id": clearing, "amount_minor": -1000},
                    {"account_id": source, "amount_minor": 1000}],
    }).status_code == 201

    payment = {"client_reference": "payment-01", "source_account_id": source,
               "destination_account_id": recipient, "amount_minor": 800, "description": "Test payment"}
    created = client.post(f"{root}/payment-intents", headers={**headers, "Idempotency-Key": "intent-01"}, json=payment)
    assert created.status_code == 201, created.text
    transfer_id = created.json()["id"]
    assert created.json()["status"] == "created" and created.json()["journal_id"] is None
    route = f"{root}/transfers/{transfer_id}/transitions"

    def action(name: str, key: str, **detail):
        return client.post(route, headers={**headers, "Idempotency-Key": key},
                           json={"action": name, "reason": f"Test {name}", **detail})

    assert action("capture", "capture-01").status_code == 409
    assert action("authorize", "authorize-01").json()["to_status"] == "authorized"
    other = client.post(f"{root}/transfers", headers={**headers, "Idempotency-Key": "other-01"},
                        json={**payment, "amount_minor": 201, "client_reference": "other"})
    assert other.json()["error"]["code"] == "insufficient_funds"
    assert action("submit", "submit-01").json()["to_status"] == "submitted"
    capture = action("capture", "capture-01", fee_minor=100, fee_account_id=fee)
    assert capture.status_code == 201, capture.text
    assert capture.json()["to_status"] == "succeeded"
    assert action("capture", "capture-01", fee_minor=100, fee_account_id=fee).json() == capture.json()
    journal_id = capture.json()["journal_id"]
    reversal = client.post(f"{root}/journals/{journal_id}/reversals", headers=headers,
                           json={"reference": "duplicate-refund", "reason": "Test managed journal"})
    assert reversal.json()["error"]["code"] == "managed_journal"

    assert action("refund", "refund-01", amount_minor=900).json()["error"]["code"] == "refund_exceeds_capture"
    assert action("refund", "refund-01", amount_minor=200).json()["to_status"] == "succeeded"
    final = action("refund", "refund-02", amount_minor=600)
    assert final.status_code == 201, final.text
    assert final.json()["to_status"] == "reversed"
    assert action("refund", "refund-02", amount_minor=600).json() == final.json()

    for account_id, expected in [(source, 900), (recipient, 0), (fee, 100)]:
        balance = client.get(f"{root}/accounts/{account_id}/balance", headers=headers)
        assert balance.json()["balance_minor"] == expected
