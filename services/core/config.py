import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Load KEY=VALUE lines into os.environ without overriding variables already set."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def _int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value else default


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value in {"1", "true", "yes", "on"}


def _optional(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,40}$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")


def _identifier(name: str, default: str, pattern: re.Pattern[str]) -> str:
    value = os.environ.get(name, "").strip() or default
    if not pattern.match(value):
        raise ValueError(f"{name}={value!r} is not a safe identifier")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    db_schema: str
    storage_bucket: str
    supabase_url: str | None
    supabase_anon_key: str | None
    supabase_service_role_key: str | None
    supabase_jwt_secret: str | None
    supabase_jwks_url: str | None
    runtime_organization_id: UUID | None
    worker_id: str | None
    release_sha: str | None
    task_lease_seconds: int
    worker_heartbeat_seconds: int
    worker_stale_seconds: int
    action_executing_timeout_seconds: int
    simulation_only: bool
    live_effects_enabled: bool
    provider_timeout_seconds: int
    azure_openai_endpoint: str | None
    azure_openai_api_key: str | None
    azure_openai_api_version: str | None
    azure_openai_decision_deployment: str | None
    azure_openai_fast_deployment: str | None

    @property
    def azure_configured(self) -> bool:
        return bool(
            self.azure_openai_endpoint
            and self.azure_openai_api_key
            and (self.azure_openai_fast_deployment or self.azure_openai_decision_deployment)
        )

    @property
    def private_schema(self) -> str:
        return "app_private" if self.db_schema == "public" else f"{self.db_schema}_private"

    @property
    def jwt_issuer(self) -> str | None:
        return f"{self.supabase_url.rstrip('/')}/auth/v1" if self.supabase_url else None

    @property
    def jwks_url(self) -> str | None:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        return f"{self.jwt_issuer}/.well-known/jwks.json" if self.jwt_issuer else None


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    runtime_org = _optional("RUNTIME_ORGANIZATION_ID")
    return Settings(
        database_url=_optional("DATABASE_URL"),
        db_schema=_identifier("OUTCOME_DB_SCHEMA", "public", _IDENTIFIER),
        storage_bucket=_identifier("STORAGE_BUCKET", "evidence", _BUCKET),
        supabase_url=_optional("SUPABASE_URL"),
        supabase_anon_key=_optional("SUPABASE_ANON_KEY"),
        supabase_service_role_key=_optional("SUPABASE_SERVICE_ROLE_KEY"),
        supabase_jwt_secret=_optional("SUPABASE_JWT_SECRET"),
        supabase_jwks_url=_optional("SUPABASE_JWKS_URL"),
        runtime_organization_id=UUID(runtime_org) if runtime_org else None,
        worker_id=_optional("WORKER_ID"),
        release_sha=_optional("RELEASE_SHA"),
        task_lease_seconds=_int("TASK_LEASE_SECONDS", 60),
        worker_heartbeat_seconds=_int("WORKER_HEARTBEAT_SECONDS", 15),
        worker_stale_seconds=_int("WORKER_STALE_SECONDS", 60),
        action_executing_timeout_seconds=_int("ACTION_EXECUTING_TIMEOUT_SECONDS", 120),
        simulation_only=_bool("SIMULATION_ONLY", True),
        live_effects_enabled=_bool("LIVE_EFFECTS_ENABLED", False),
        provider_timeout_seconds=_int("PROVIDER_TIMEOUT_SECONDS", 20),
        azure_openai_endpoint=_optional("AZURE_OPENAI_ENDPOINT"),
        azure_openai_api_key=_optional("AZURE_OPENAI_API_KEY"),
        azure_openai_api_version=_optional("AZURE_OPENAI_API_VERSION"),
        azure_openai_decision_deployment=_optional("AZURE_OPENAI_DECISION_DEPLOYMENT"),
        azure_openai_fast_deployment=_optional("AZURE_OPENAI_FAST_DEPLOYMENT"),
    )
