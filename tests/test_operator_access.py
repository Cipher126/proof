from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from proof import identity
from proof.db import get_session
from proof.main import app


def test_named_credentials_scope_roles_and_revoke(client, monkeypatch):
    tenant = client.post("/v1/demo/tenants", json={"name": "Operations test"}).json()["id"]
    test_session = contextmanager(app.dependency_overrides[get_session])
    with test_session() as session:
        auditor, read_key = identity.issue_operator_credential(session, UUID(tenant), "Reviewer", "auditor", 1)
        _, operator_key = identity.issue_operator_credential(session, UUID(tenant), "Operations", "operator", 1)
        _, provider_key = identity.issue_operator_credential(session, UUID(tenant), "Provider", "provider", 1)
        auditor_id = auditor.id
    monkeypatch.setattr(identity, "settings", SimpleNamespace(environment="operations"))
    root = f"/v1/tenants/{tenant}"

    def auth(token):
        return {"Authorization": f"Bearer {token}"}

    assert client.post("/v1/demo/scenarios/canonical").status_code == 404
    account = {"name": "Managed account", "currency": "NGN"}
    assert client.post(root + "/accounts", headers={"X-Tenant-ID": tenant}, json=account).status_code == 401
    assert client.post(root + "/accounts", headers=auth(read_key), json=account).status_code == 403
    created = client.post(root + "/accounts", headers=auth(operator_key), json=account)
    assert created.status_code == 201, created.text
    balance = f"{root}/accounts/{created.json()['id']}/balance"
    assert client.get(balance, headers=auth(read_key)).status_code == 200
    assert client.get(balance, headers=auth(provider_key)).status_code == 403
    with test_session() as session:
        session.get(identity.OperatorCredential, auditor_id).revoked_at = datetime.now(timezone.utc)
        session.commit()
    assert client.get(balance, headers=auth(read_key)).status_code == 401
