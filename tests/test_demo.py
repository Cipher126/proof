from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from proof import identity
from proof.db import get_session
from proof.main import app
from proof.operations.models import AuditEvent


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


def test_sandbox_credential_is_tenant_bound_and_supplies_audit_actor(client, monkeypatch):
    monkeypatch.setattr(identity, "settings", SimpleNamespace(environment="sandbox"))
    assert client.post("/v1/demo/tenants", json={"name": "Unrestricted"}).status_code == 404
    response = client.post("/v1/demo/scenarios/canonical")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    scenario = response.json()
    other = client.post("/v1/demo/scenarios/canonical").json()
    tenant = scenario["tenant_id"]
    token = scenario["access_token"]
    base = f"/v1/tenants/{tenant}"
    timeline = f"{base}/operations/transfers/{scenario['transfer']['id']}/timeline"
    auth = {"Authorization": f"Bearer {token}"}

    assert client.get(timeline, headers={"X-Tenant-ID": tenant}).status_code == 401
    assert client.get(timeline, headers={"Authorization": "Bearer " + "x" * 43}).status_code == 401
    assert client.get(timeline, headers={
        "Authorization": f"Bearer {other['access_token']}", "X-Tenant-ID": tenant,
    }).status_code == 401
    assert client.get(timeline, headers=auth).status_code == 200
    assert client.post(
        f"{base}/accounts", headers=auth, json={"name": "Extra account", "currency": "NGN"},
    ).status_code == 404

    finding = scenario["findings"][0]
    response = client.post(
        f"{base}/reconciliation/findings/{finding['id']}/resolve",
        headers={**auth, "X-Operator-ID": "spoofed-operator"},
        json={"resolution": "acknowledged", "reason": "Reviewed the fictional discrepancy"},
    )
    assert response.status_code == 200, response.text

    test_session = contextmanager(app.dependency_overrides[get_session])
    with test_session() as session:
        credential = session.scalar(select(identity.DemoCredential).where(
            identity.DemoCredential.verifier == hashlib.sha256(token.encode()).hexdigest()
        ))
        assert credential is not None
        audit = session.scalar(select(AuditEvent))
        assert audit.actor == response.json()["resolved_by"] == f"demo:{credential.id}"
        credential.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.commit()

    assert client.get(timeline, headers=auth).status_code == 401
