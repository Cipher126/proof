from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "PROOF_DATABASE_URL",
        "postgresql+psycopg://proof:proof@127.0.0.1:5432/proof",
    )
    environment: str = os.getenv("PROOF_ENVIRONMENT", "development")
    log_level: str = os.getenv("PROOF_LOG_LEVEL", "INFO")


settings = Settings()
