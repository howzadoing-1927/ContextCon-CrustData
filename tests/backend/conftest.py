"""Database test harness.

Reads the repo-root .env (never overriding variables already set). Two auth modes:
- gotrue (default when SUPABASE_URL, SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY exist): real users via
  the Supabase Auth admin API and real access tokens via password sign-in.
- local_jwt (OUTCOME_TEST_AUTH_MODE=local_jwt + SUPABASE_JWT_SECRET): throwaway plain Postgres with
  tests/backend/sql/supabase_local_shim.sql; users inserted into auth.users and HS256 tokens minted.
Without DATABASE_URL every database test is skipped with that reason; skipped is never passed.
"""

import os
import secrets
import time
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx2
import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.core import admin, db
from services.core.campaigns import launch_campaign
from services.core.config import get_settings, load_dotenv
from services.core.contracts.requests import CampaignCreate
from services.core.contracts.views import CampaignLaunchView

load_dotenv()

BUYER_EMAIL = "consenting-buyer@example.invalid"


@dataclass(frozen=True)
class TestUser:
    id: UUID
    email: str
    token: str


@dataclass(frozen=True)
class Tenant:
    organization_id: UUID
    owner: TestUser
    buyer_test_email: str


def _connect(url: str) -> psycopg.Connection:
    return db.connect(url)


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set: database tests need the Supabase .env")
    return url


@pytest.fixture(scope="session")
def auth_mode(database_url: str) -> str:
    mode = os.environ.get("OUTCOME_TEST_AUTH_MODE", "gotrue")
    if mode == "local_jwt":
        if not (os.environ.get("SUPABASE_JWT_SECRET") and os.environ.get("SUPABASE_URL")):
            pytest.skip("local_jwt mode needs SUPABASE_URL (issuer) and SUPABASE_JWT_SECRET")
        return mode
    if not all(os.environ.get(k) for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY")):
        pytest.skip("gotrue mode needs SUPABASE_URL, SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY")
    return mode


@pytest.fixture
def conn(database_url: str) -> Iterator[psycopg.Connection]:
    connection = _connect(database_url)
    yield connection
    connection.close()


class UserFactory:
    def __init__(self, mode: str, database_url: str) -> None:
        self.mode = mode
        self.database_url = database_url
        self.created: list[UUID] = []
        self.base = os.environ["SUPABASE_URL"].rstrip("/")

    def _service_headers(self) -> dict[str, str]:
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        return {"apikey": key, "Authorization": f"Bearer {key}"}

    def create(self) -> TestUser:
        email = f"outcome-test-{uuid4().hex[:12]}@example.com"
        if self.mode == "local_jwt":
            user_id = uuid4()
            with _connect(self.database_url) as c:
                c.execute("insert into auth.users (id, email) values (%s, %s)", (user_id, email))
            self.created.append(user_id)
            return TestUser(user_id, email, mint_token(user_id))
        password = secrets.token_urlsafe(24)
        created = httpx2.post(
            f"{self.base}/auth/v1/admin/users",
            headers=self._service_headers(),
            json={"email": email, "password": password, "email_confirm": True},
            timeout=15,
        )
        created.raise_for_status()
        user_id = UUID(created.json()["id"])
        self.created.append(user_id)
        session = httpx2.post(
            f"{self.base}/auth/v1/token?grant_type=password",
            headers={"apikey": os.environ["SUPABASE_ANON_KEY"]},
            json={"email": email, "password": password},
            timeout=15,
        )
        session.raise_for_status()
        return TestUser(user_id, email, session.json()["access_token"])

    def cleanup(self) -> None:
        for user_id in self.created:
            if self.mode == "local_jwt":
                with _connect(self.database_url) as c:
                    c.execute("delete from auth.users where id = %s", (user_id,))
            else:
                httpx2.delete(f"{self.base}/auth/v1/admin/users/{user_id}", headers=self._service_headers(), timeout=15)


def mint_token(user_id: UUID, *, expires_in: int = 600, secret: str | None = None) -> str:
    now = int(time.time())
    claims = {
        "sub": str(user_id),
        "aud": "authenticated",
        "role": "authenticated",
        "iss": f"{os.environ['SUPABASE_URL'].rstrip('/')}/auth/v1",
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, secret or os.environ["SUPABASE_JWT_SECRET"], algorithm="HS256")


@pytest.fixture
def make_tenant(auth_mode: str, database_url: str) -> Iterator:
    users = UserFactory(auth_mode, database_url)
    orgs: list[UUID] = []

    def factory(*, seller_connected: bool = True, approved: bool = True) -> Tenant:
        owner = users.create()
        with _connect(database_url) as c, c.transaction():
            org_id = admin.seed_organization(
                c,
                name=f"Outcome test {uuid4().hex[:6]}",
                owner_user_id=owner.id,
                buyer_test_email=BUYER_EMAIL,
                consent_record="pytest operator-attested consent",
                approve_placeholder_profile=approved,
            )
            if seller_connected:
                admin.seed_seller_connection_without_oauth(c, organization_id=org_id, account_email="seller@example.invalid")
        orgs.append(org_id)
        return Tenant(org_id, owner, BUYER_EMAIL)

    yield factory

    with _connect(database_url) as c:
        for org_id in orgs:
            with c.transaction():
                admin.purge_organization(c, org_id)
    users.cleanup()


@pytest.fixture
def api(auth_mode: str) -> Iterator[TestClient]:
    get_settings.cache_clear()
    db.reset_pool()
    yield TestClient(create_app())
    db.reset_pool()
    get_settings.cache_clear()


def launch(database_url: str, tenant: Tenant, key: str | None = None, **overrides) -> CampaignLaunchView:
    """Launch through the real core transaction (not the HTTP layer) to set up queue/action tests."""
    with _connect(database_url) as c, c.transaction():
        return launch_campaign(
            c,
            organization_id=tenant.organization_id,
            user_id=tenant.owner.id,
            idempotency_key=key or f"pytest-{uuid4()}",
            body=CampaignCreate.model_validate(campaign_body(tenant, **overrides)),
        )


def auth_headers(user: TestUser, organization_id: UUID, *, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {user.token}", "X-Organization-ID": str(organization_id)}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def campaign_body(tenant: Tenant, **overrides) -> dict:
    body = {
        "request_text": "Find a relevant B2B company and its sales leader and book a 15-minute demo.",
        "mode": "simulation",
        "buyer_test_email": tenant.buyer_test_email,
        "profile_version": 1,
        "config_version": 1,
        "limits": dict(admin.DEFAULT_LIMITS),
    }
    body.update(overrides)
    return body
