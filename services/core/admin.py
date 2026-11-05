"""Trusted server/admin paths for tenant setup and cleanup. Never exposed through the API.

    python -m services.core.admin seed-org --name "Demo seller" --owner-email owner@example.com \
        --buyer-test-email buyer@example.com --consent-record "operator-attested 2026-11-05"
    python -m services.core.admin purge-org --organization-id <uuid>
"""

import argparse
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from .contracts.base import normalize_email
from .db import reset_pool, transaction

REQUIRED_GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.freebusy",
)

DEFAULT_LIMITS = {
    "max_discovered": 10,
    "max_enriched": 3,
    "max_conversations": 1,
    "max_outbound_messages": 6,
    "max_model_calls": 20,
    "max_research_calls": 10,
    "max_runtime_seconds": 600,
    "max_reply_turns": 4,
    "no_reply_followups": 0,
}

# Deletion order respects composite foreign keys; decisions/evidence deletes are allowed only while
# app.purge_tenant equals this organization for the current transaction.
_PURGE_ORDER = (
    "suppressions", "messages", "actions", "decisions", "tasks", "conversations",
    "evidence", "prospects", "campaigns", "connections", "memberships",
)


def seed_organization(
    conn: psycopg.Connection,
    *,
    name: str,
    owner_user_id: UUID,
    buyer_test_email: str,
    consent_record: str,
    timezone: str = "Asia/Kolkata",
    approve_placeholder_profile: bool = False,
) -> UUID:
    """Create an organization, its owner membership and a simulation policy with one consented buyer."""
    org_id = uuid4()
    now = datetime.now(UTC)
    policy = {
        "simulation": True,
        "consented_recipients": [
            {
                "email": normalize_email(buyer_test_email),
                "role": "buyer_test",
                "consent_record": consent_record,
                "consented_at": now.isoformat(),
            }
        ],
        "limits": DEFAULT_LIMITS,
    }
    profile = {"approved_facts": [], "placeholder": True} if approve_placeholder_profile else {}
    conn.execute(
        """
        insert into public.organizations
          (id, name, timezone, approved_profile_json, profile_version, approved_at, approved_by,
           policy_json, config_version)
        values (%s, %s, %s, %s, %s, %s, %s, %s, 1)
        """,
        (
            org_id, name, timezone, Jsonb(profile),
            1 if approve_placeholder_profile else 0,
            now if approve_placeholder_profile else None,
            owner_user_id if approve_placeholder_profile else None,
            Jsonb(policy),
        ),
    )
    add_membership(conn, organization_id=org_id, user_id=owner_user_id, role="owner")
    return org_id


def add_membership(conn: psycopg.Connection, *, organization_id: UUID, user_id: UUID, role: str) -> None:
    conn.execute(
        "insert into public.memberships (organization_id, user_id, role) values (%s, %s, %s)",
        (organization_id, user_id, role),
    )


def seed_seller_connection_without_oauth(
    conn: psycopg.Connection, *, organization_id: UUID, account_email: str, scopes: tuple[str, ...] = REQUIRED_GOOGLE_SCOPES
) -> UUID:
    """DEV/TEST ONLY: marks a seller Google connection as connected without tokens, so launch preconditions
    can be exercised before D2's OAuth exists. No Google call can succeed through this row."""
    row = conn.execute(
        """
        insert into public.connections (organization_id, provider, purpose, status, account_email, granted_scopes, calendar_id)
        values (%s, 'google', 'seller', 'connected', %s, %s, 'primary')
        returning id
        """,
        (organization_id, normalize_email(account_email), list(scopes)),
    ).fetchone()
    return row["id"]


def purge_organization(conn: psycopg.Connection, organization_id: UUID) -> None:
    conn.execute("select set_config('app.purge_tenant', %s, true)", (str(organization_id),))
    for table in _PURGE_ORDER:
        conn.execute(f"delete from public.{table} where organization_id = %s", (organization_id,))
    conn.execute("delete from public.organizations where id = %s", (organization_id,))


def _user_id_for_email(conn: psycopg.Connection, email: str) -> UUID:
    row = conn.execute("select id from auth.users where lower(email) = lower(%s)", (email,)).fetchone()
    if row is None:
        raise SystemExit(f"no auth.users row for {email!r}; create the user in Supabase Auth first")
    return row["id"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m services.core.admin")
    sub = parser.add_subparsers(dest="command", required=True)

    seed = sub.add_parser("seed-org")
    seed.add_argument("--name", required=True)
    seed.add_argument("--owner-email", required=True)
    seed.add_argument("--buyer-test-email", required=True)
    seed.add_argument("--consent-record", required=True)
    seed.add_argument("--timezone", default="Asia/Kolkata")
    seed.add_argument(
        "--approve-placeholder-profile",
        action="store_true",
        help="Mark an empty placeholder profile approved so launch can be exercised before B3 profile approval.",
    )

    purge = sub.add_parser("purge-org")
    purge.add_argument("--organization-id", required=True, type=UUID)

    args = parser.parse_args(argv)
    try:
        _run(args)
    finally:
        reset_pool()


def _run(args: argparse.Namespace) -> None:
    with transaction() as conn:
        if args.command == "seed-org":
            org_id = seed_organization(
                conn,
                name=args.name,
                owner_user_id=_user_id_for_email(conn, args.owner_email),
                buyer_test_email=args.buyer_test_email,
                consent_record=args.consent_record,
                timezone=args.timezone,
                approve_placeholder_profile=args.approve_placeholder_profile,
            )
            print(json.dumps({"organization_id": str(org_id)}))
        else:
            purge_organization(conn, args.organization_id)
            print(json.dumps({"purged": str(args.organization_id)}))


if __name__ == "__main__":
    main()
