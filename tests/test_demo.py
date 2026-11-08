from __future__ import annotations

from fastapi.testclient import TestClient


def test_canonical_demo_runs_end_to_end(client: TestClient) -> None:
    response = client.post("/v1/demo/scenarios/canonical")
    assert response.status_code == 200, response.text
    scenario = response.json()
    assert scenario["fictional"] is True
    assert scenario["transfer"]["amount_minor"] == 2_500_000
    assert scenario["provider_event"]["amount_minor"] == 2_475_000
    assert scenario["provider_event"]["classification"] == "conflict"
    assert len(scenario["findings"]) == 1
    assert scenario["findings"][0]["kind"] == "amount_mismatch"

    timeline = client.get(
        f"/v1/tenants/{scenario['tenant_id']}/operations/transfers/"
        f"{scenario['transfer']['id']}/timeline",
        headers={"X-Tenant-ID": scenario["tenant_id"]},
    )
    assert timeline.status_code == 200
    assert {item["kind"] for item in timeline.json()["items"]} == {
        "transfer",
        "journal",
        "outbox",
        "provider_evidence",
    }
