"""Configuration via environment variables (pydantic-settings).

Single source of truth for all runtime configuration. Tests use this with
overrides via env vars; production loads from `.env` on the Vultr VM.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Environment variables override defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    # ---------------------------------------------------------------- app ---
    atrio_env: Literal["local", "test", "staging", "demo", "prod"] = "local"
    atrio_build_sha: str = "dev"
    atrio_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"
    log_level: str = "INFO"

    # ----------------------------------------------------------- database ---
    database_url: str = "postgresql+asyncpg://atrio:atrio_local_dev_password@postgres:5432/atrio"

    # ----------------------------------------------------------------- jwt ---
    jwt_private_key_path: str = "/run/secrets/jwt_private.pem"
    jwt_public_key_path: str = "/run/secrets/jwt_public.pem"
    jwt_algorithm: str = "RS256"
    jwt_access_expires_seconds: int = 3600
    jwt_refresh_expires_seconds: int = 2_592_000

    # In test mode we use HS256 with an inline secret so we don't need files.
    jwt_test_secret: str = "test-secret-for-unit-tests-only-not-prod-32chars"

    # ----------------------------------------------------------------- ai ---
    gemini_api_key: str = ""
    featherless_api_key: str = ""
    speechmatics_api_key: str = ""
    atrio_mock_inference: bool = True

    # ------------------------------------------------------------ livekit ---
    livekit_url: str = "ws://livekit:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "devsecret_at_least_32_chars_long_xxxx"

    # ------------------------------------------------------------- kraken ---
    kraken_api_key: str = ""
    kraken_api_secret: str = ""
    kraken_paper_mode: bool = True

    # -------------------------------------------------------- object store ---
    s3_endpoint: str = "http://minio:9000"
    s3_region: str = "eu-central-1"
    s3_access_key: str = "atrio_minio_user"
    s3_secret_key: str = "atrio_minio_password"
    s3_bucket: str = "atrio-storage"
    s3_force_path_style: bool = True

    # ---------------------------------------------------------------- smtp ---
    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = "noreply@atrio.app"
    smtp_tls: bool = False
    frontend_base_url: str = "http://localhost:8080"

    # -------------------------------------------------------------- cors ---
    cors_origins: str = "http://localhost:5173,http://localhost:8000"
    rate_limit_enabled: bool = True

    # ----------------------------------------------------- observability ---
    prometheus_enabled: bool = True

    # ----------------------------------------------------------- paths ---
    model_registry_path: str = Field(default="config/models/atrio.yaml")
    prompts_dir: str = Field(default="prompts")
    mandates_dir: str = Field(default="config/mandates")
    dictionaries_dir: str = Field(default="config/dictionaries")

    # ---------------------------------------------------------- limits ---
    max_document_bytes: int = 25 * 1024 * 1024
    max_documents_per_session: int = 5
    proposal_expiry_seconds: int = 15 * 60
    dissent_rounds_cap: int = 2

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return ",".join(o.strip() for o in v.split(",") if o.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o for o in self.cors_origins.split(",") if o]

    @property
    def is_test(self) -> bool:
        return self.atrio_env == "test"

    @property
    def is_prod_like(self) -> bool:
        return self.atrio_env in ("staging", "demo", "prod")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()


def reset_settings_cache() -> None:
    """Test helper: reset the settings cache so env changes take effect."""
    get_settings.cache_clear()


def project_root() -> Path:
    """Return the repository root (directory containing this file's grandparent)."""
    return Path(__file__).resolve().parents[3]
