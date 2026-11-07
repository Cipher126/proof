from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProofError(Exception):
    code: str
    message: str
    status_code: int = 400


class NotFoundError(ProofError):
    def __init__(self, resource: str) -> None:
        super().__init__("not_found", f"{resource} was not found", 404)


class TenantBoundaryError(ProofError):
    def __init__(self) -> None:
        super().__init__("tenant_boundary_violation", "resource is outside the active tenant", 404)
