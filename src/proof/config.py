from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "PROOF_DATABASE_URL",
        "postgresql+psycopg://proof:proof@127.0.0.1:55432/proof",
    )
    environment: str = os.getenv("PROOF_ENVIRONMENT", "development")
    log_level: str = os.getenv("PROOF_LOG_LEVEL", "INFO")
    simulated_provider_secret: str = os.getenv(
        "PROOF_SIMULATED_PROVIDER_SECRET", "development-only-change-me"
    )


settings = Settings()
