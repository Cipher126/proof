from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone

from proof.db import SessionLocal
from proof.errors import ProofError
from proof.identity import OperatorCredential, ROLE_PERMISSIONS, issue_operator_credential
from proof.ledger.service import create_tenant
from proof.operations.models import AuditEvent


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Proof tenants and credentials from a trusted shell")
    commands = parser.add_subparsers(dest="command", required=True)
    tenant = commands.add_parser("tenant")
    tenant.add_argument("name")
    issue = commands.add_parser("issue")
    issue.add_argument("tenant", type=uuid.UUID)
    issue.add_argument("name")
    issue.add_argument("role", choices=sorted(ROLE_PERMISSIONS))
    issue.add_argument("--hours", type=int, default=24)
    revoke = commands.add_parser("revoke")
    revoke.add_argument("credential", type=uuid.UUID)
    args = parser.parse_args()
    try:
        with SessionLocal() as session:
            if args.command == "tenant":
                if not 1 <= len(args.name.strip()) <= 120:
                    parser.error("invalid tenant name")
                record = create_tenant(session, args.name)
                print(json.dumps({"tenant_id": str(record.id)}))
            elif args.command == "issue":
                key, token = issue_operator_credential(session, args.tenant, args.name, args.role, args.hours)
                print(json.dumps({"credential_id": str(key.id), "token": token, "expires_at": key.expires_at.isoformat()}))
            else:
                key = session.get(OperatorCredential, args.credential, with_for_update=True)
                if key is None:
                    parser.error("credential not found")
                if key.revoked_at is None:
                    key.revoked_at = datetime.now(timezone.utc)
                    session.add(AuditEvent(
                        tenant_id=key.tenant_id, actor="local-admin", action="credential.revoked",
                        resource_type="operator_credential", resource_id=key.id,
                        reason="Revoked from the administration CLI", details={},
                    ))
                    session.commit()
    except ProofError as exc:
        parser.exit(1, f"{exc.code}: {exc.message}\n")


if __name__ == "__main__":
    main()
