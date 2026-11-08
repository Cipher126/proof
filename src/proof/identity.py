from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from proof.config import settings
from proof.db import Base, get_session
from proof.errors import ProofError
from proof.ledger.models import Tenant

ROLE_PERMISSIONS = {
    "integrator": {"read", "payment"},
    "operator": {"read", "ledger", "settlement"},
    "auditor": {"read"},
    "provider": {"provider"},
}


class OperatorCredential(Base):
    __tablename__ = "operator_credentials"
    __table_args__ = (CheckConstraint(
        "role IN ('integrator', 'operator', 'auditor', 'provider')", name="ck_operator_credential_role",
    ),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(20))
    verifier: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DemoCredential(Base):
    __tablename__ = "demo_credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), unique=True
    )
    verifier: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DemoAdmissionBucket(Base):
    __tablename__ = "demo_admission_buckets"
    bucket: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    client_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    starts: Mapped[int] = mapped_column(Integer)


@dataclass(frozen=True)
class TenantAccess:
    tenant_id: uuid.UUID
    credential_id: uuid.UUID | None = None
    role: str = "development"
    name: str | None = None

    @property
    def audit_actor(self) -> str | None:
        if self.name is not None:
            return f"key:{self.name}:{self.credential_id}"
        return f"demo:{self.credential_id}" if self.credential_id else None


def _verifier(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_demo_credential(session: Session, tenant_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    session.add(DemoCredential(
        tenant_id=tenant_id,
        verifier=_verifier(token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    ))
    session.commit()
    return token


def require_development() -> None:
    if settings.environment != "development":
        raise ProofError("not_found", "endpoint was not found", 404)


def issue_operator_credential(
    session: Session, tenant_id: uuid.UUID, name: str, role: str, hours: int,
) -> tuple[OperatorCredential, str]:
    if session.get(Tenant, tenant_id) is None:
        raise ProofError("not_found", "tenant was not found", 404)
    if role not in ROLE_PERMISSIONS or not 1 <= hours <= 2160 or not 1 <= len(name.strip()) <= 80:
        raise ProofError("invalid_credential", "invalid name, role, or expiry")
    token = "proofk_" + secrets.token_urlsafe(32)
    credential = OperatorCredential(
        tenant_id=tenant_id, name=name.strip(), role=role, verifier=_verifier(token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=hours),
    )
    session.add(credential)
    session.commit()
    return credential, token


def require_demo() -> None:
    if settings.environment not in {"sandbox", "development"}:
        raise ProofError("not_found", "endpoint was not found", 404)


def active_tenant(
    tenant_id: uuid.UUID,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))],
    x_tenant_id: Annotated[uuid.UUID | None, Header(alias="X-Tenant-ID")] = None,
) -> TenantAccess:
    if "authorization" not in request.headers and settings.environment == "development":
        if x_tenant_id != tenant_id:
            raise ProofError("tenant_header_mismatch", "X-Tenant-ID must match the route tenant", 403)
        return TenantAccess(tenant_id)

    token = credentials.credentials if credentials is not None else ""
    if settings.environment == "operations" and token.startswith("proofk_") and len(token) == 50:
        key = session.scalar(select(OperatorCredential).where(
            OperatorCredential.tenant_id == tenant_id,
            OperatorCredential.verifier == _verifier(token),
            OperatorCredential.expires_at > func.now(),
            OperatorCredential.revoked_at.is_(None),
        ))
        if key is not None:
            return TenantAccess(tenant_id, key.id, key.role, key.name)
    if settings.environment in {"sandbox", "development"} and len(token) == 43:
        credential_id = session.scalar(
            select(DemoCredential.id).where(
                DemoCredential.tenant_id == tenant_id,
                DemoCredential.verifier == _verifier(token),
                DemoCredential.expires_at > func.now(),
            )
        )
        if credential_id is not None:
            return TenantAccess(tenant_id, credential_id, "demo")
    code = "invalid_credential" if settings.environment == "operations" else "invalid_demo_credential"
    raise ProofError(code, "a valid tenant bearer credential is required", 401)


def require_permission(permission: str):
    def authorize(access: Annotated[TenantAccess, Depends(active_tenant)]) -> None:
        if permission == "read" and access.role == "demo":
            return
        if settings.environment == "sandbox":
            raise ProofError("not_found", "endpoint was not found", 404)
        if access.role == "development":
            return
        if permission not in ROLE_PERMISSIONS.get(access.role, set()):
            raise ProofError("permission_denied", "credential lacks permission for this operation", 403)

    return authorize
