from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import DateTime, ForeignKey, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from proof.config import settings
from proof.db import Base, get_session
from proof.errors import ProofError


class DemoCredential(Base):
    __tablename__ = "demo_credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), unique=True
    )
    verifier: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True)
class TenantAccess:
    tenant_id: uuid.UUID
    credential_id: uuid.UUID | None = None

    @property
    def audit_actor(self) -> str | None:
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

    if credentials is not None and len(credentials.credentials) == 43:
        credential_id = session.scalar(
            select(DemoCredential.id).where(
                DemoCredential.tenant_id == tenant_id,
                DemoCredential.verifier == _verifier(credentials.credentials),
                DemoCredential.expires_at > func.now(),
            )
        )
        if credential_id is not None:
            return TenantAccess(tenant_id, credential_id)
    raise ProofError("invalid_demo_credential", "a valid demo bearer credential is required", 401)
