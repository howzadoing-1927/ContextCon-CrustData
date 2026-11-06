"""Seed the live demo workspace: a real Supabase Auth login, one org, and the consented test inboxes.

    .venv/bin/python scripts/seed_demo.py --login-email you@example.com \
        --buyer a@example.com --buyer b@example.com --consent-record "operator-attested 2026-11-06"

Idempotent: reuses the login and the org it already owns. Writes DEMO_LOGIN_EMAIL, DEMO_LOGIN_PASSWORD and
RUNTIME_ORGANIZATION_ID into the root .env and NEXT_PUBLIC_OUTCOME_ORG_ID into apps/web/.env.local.
Every buyer is a consented buyer_test recipient; researched people are never recipients.
"""

import argparse
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx2
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.core.admin import seed_organization  # noqa: E402
from services.core.config import REPO_ROOT, get_settings  # noqa: E402
from services.core.contracts.base import normalize_email  # noqa: E402
from services.core.db import reset_pool, transaction  # noqa: E402


def _set_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.is_file() else []
    keys = set(values)
    kept = [line for line in lines if line.split("=", 1)[0].strip() not in keys]
    kept += [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(kept) + "\n")


def _env_value(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip() or None
    return None


def ensure_login(email: str, password: str) -> UUID:
    settings = get_settings()
    base = f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users"
    headers = {"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}"}
    with transaction() as conn:
        row = conn.execute("select id from auth.users where lower(email) = lower(%s)", (email,)).fetchone()
    with httpx2.Client(timeout=20) as http:
        if row:
            res = http.put(f"{base}/{row['id']}", headers=headers, json={"password": password, "email_confirm": True})
            res.raise_for_status()
            return row["id"]
        res = http.post(base, headers=headers, json={"email": email, "password": password, "email_confirm": True})
        res.raise_for_status()
        return UUID(res.json()["id"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--login-email", required=True)
    parser.add_argument("--buyer", action="append", required=True)
    parser.add_argument("--consent-record", required=True)
    parser.add_argument("--name", default="Vedora")
    parser.add_argument("--timezone", default="Asia/Kolkata")
    args = parser.parse_args()

    root_env, web_env = REPO_ROOT / ".env", REPO_ROOT / "apps/web/.env.local"
    password = _env_value(root_env, "DEMO_LOGIN_PASSWORD") or secrets.token_urlsafe(18)
    user_id = ensure_login(args.login_email, password)

    now = datetime.now(UTC).isoformat()
    buyers = [
        {"email": normalize_email(b), "role": "buyer_test", "consent_record": args.consent_record, "consented_at": now}
        for b in dict.fromkeys(args.buyer)
    ]
    try:
        with transaction() as conn:
            owned = conn.execute(
                "select organization_id from memberships where user_id = %s and role = 'owner' order by created_at limit 1",
                (user_id,),
            ).fetchone()
            org_id = owned["organization_id"] if owned else seed_organization(
                conn, name=args.name, owner_user_id=user_id, buyer_test_email=buyers[0]["email"],
                consent_record=args.consent_record, timezone=args.timezone,
            )
            conn.execute(
                "update organizations set policy_json = jsonb_set(policy_json, '{consented_recipients}', %s), "
                "config_version = greatest(config_version, 1) where id = %s",
                (Jsonb(buyers), org_id),
            )
    finally:
        reset_pool()

    _set_env(root_env, {"DEMO_LOGIN_EMAIL": args.login_email, "DEMO_LOGIN_PASSWORD": password,
                        "RUNTIME_ORGANIZATION_ID": str(org_id)})
    _set_env(web_env, {"NEXT_PUBLIC_OUTCOME_ORG_ID": str(org_id)})
    print(f"organization_id={org_id} login={args.login_email} buyers={len(buyers)}")


if __name__ == "__main__":
    main()
