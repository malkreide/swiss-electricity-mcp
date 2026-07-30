"""Centralised configuration (ARCH-004).

All runtime configuration is read once into a Pydantic-Settings object instead of
scattered ``os.environ`` lookups and module-level globals. Environment variables
use the ``SWISS_ELECTRICITY_`` prefix.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SWISS_ELECTRICITY_",
        extra="ignore",
    )

    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    # `NoDecode` is required, not cosmetic: pydantic-settings JSON-decodes any
    # complex-typed field straight from the environment *before* a
    # `mode="before"` validator runs. Without it,
    # `SWISS_ELECTRICITY_CORS_ORIGINS=https://a.test,https://b.test` raises
    # SettingsError instead of reaching `_split_csv` — so the comma-separated
    # form this module documents never worked and the validator was dead code.
    cors_origins: Annotated[list[str], NoDecode] = []
    # SEC-005: hostnames this server is reachable under. Needed for the
    # transport's Host/Origin check once the bind is not loopback — this process
    # cannot guess the service or public DNS name it is addressed by.
    allowed_hosts: Annotated[list[str], NoDecode] = []
    env: str = "unknown"  # deployment.environment resource attribute for traces

    @field_validator("cors_origins", "allowed_hosts", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        """Accept a comma-separated string (env var) or an already-parsed list."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton."""
    return Settings()
