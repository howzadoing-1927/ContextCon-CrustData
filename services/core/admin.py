"""Trusted server/admin paths for tenant setup and cleanup. Never exposed through the API.

    python -m services.core.admin seed-org --name "Demo seller" --owner-email owner@example.com \
        --buyer-test-email buyer@example.com --consent-record "operator-attested 2026-11-05" \
        --fact "An operator-approved statement about the seller"
    python -m services.core.admin purge-org --organization-id <uuid>
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from .contracts.base import normalize_email
from .contracts.requests import DEFAULT_PEOPLE, limits_for
from .db import reset_pool, transaction

REQUIRED_GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.freebusy",
)

DEFAULT_LIMITS = limits_for(DEFAULT_PEOPLE)

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
    approved_facts: list[str] | None = None,
) -> UUID:
    """Create an organization, its owner membership and a simulation policy with one consented buyer.
    `approved_facts` are operator-attested statements: each becomes operator evidence plus an approved fact
    (profile_version 1). Without them the profile stays unapproved and launch is refused."""
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
        "selected_calendar_id": "primary",
        "working_hours": {"timezone": timezone, "weekdays": [1, 2, 3, 4, 5], "start": "09:00", "end": "17:00"},
        "duration_minutes": 15,
        "limits": DEFAULT_LIMITS,
    }
    conn.execute(
        "insert into organizations (id, name, timezone, policy_json, config_version) values (%s, %s, %s, %s, 1)",
        (org_id, name, timezone, Jsonb(policy)),
    )
    add_membership(conn, organization_id=org_id, user_id=owner_user_id, role="owner")
    if approved_facts:
        approve_operator_facts(conn, organization_id=org_id, user_id=owner_user_id, facts=approved_facts)
    return org_id


def approve_operator_facts(conn: psycopg.Connection, *, organization_id: UUID, user_id: UUID, facts: list[str]) -> None:
    """Trusted admin path equivalent to POST /workspace/sources (pasted_text) + PUT /workspace/profile."""
    approved = []
    for index, text in enumerate(facts, start=1):
        evidence_id = conn.execute(
            """
            insert into evidence (organization_id, entity_kind, entity_id, source_kind, excerpt, retrieved_at,
                                  content_sha256, fact_status, metadata_json)
            values (%s, 'seller_source', %s, 'operator', %s, now(), %s, 'observed', %s)
            returning id
            """,
            (organization_id, organization_id, text, hashlib.sha256(text.encode()).hexdigest(),
             Jsonb({"title": f"operator-attested fact {index}", "added_by": str(user_id), "via": "admin"})),
        ).fetchone()["id"]
        approved.append({"id": f"F{index}", "text": text, "evidence_ids": [str(evidence_id)],
                         "authority": "operator_approved", "approved": True})
    conn.execute(
        """
        update organizations
        set approved_profile_json = %s, profile_version = profile_version + 1, approved_at = now(), approved_by = %s
        where id = %s
        """,
        (Jsonb({"approved_facts": approved, "faq": [], "forbidden_promises": []}), user_id, organization_id),
    )


def add_membership(conn: psycopg.Connection, *, organization_id: UUID, user_id: UUID, role: str) -> None:
    conn.execute(
        "insert into memberships (organization_id, user_id, role) values (%s, %s, %s)",
        (organization_id, user_id, role),
    )


def seed_seller_connection_without_oauth(
    conn: psycopg.Connection, *, organization_id: UUID, account_email: str, scopes: tuple[str, ...] = REQUIRED_GOOGLE_SCOPES
) -> UUID:
    """DEV/TEST ONLY: marks a seller Google connection as connected without tokens, so launch preconditions
    can be exercised before D2's OAuth exists. No Google call can succeed through this row."""
    row = conn.execute(
        """
        insert into connections (organization_id, provider, purpose, status, account_email, granted_scopes, calendar_id)
        values (%s, 'google', 'seller', 'connected', %s, %s, 'primary')
        returning id
        """,
        (organization_id, normalize_email(account_email), list(scopes)),
    ).fetchone()
    return row["id"]


def purge_organization(conn: psycopg.Connection, organization_id: UUID) -> None:
    conn.execute("select set_config('app.purge_tenant', %s, true)", (str(organization_id),))
    for table in _PURGE_ORDER:
        conn.execute(f"delete from {table} where organization_id = %s", (organization_id,))
    conn.execute("delete from organizations where id = %s", (organization_id,))


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
        "--fact",
        action="append",
        default=[],
        help="Operator-attested seller fact to approve (repeatable). Only state facts the seller has approved.",
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
                approved_facts=args.fact,
            )
            print(json.dumps({"organization_id": str(org_id)}))
        else:
            purge_organization(conn, args.organization_id)
            print(json.dumps({"purged": str(args.organization_id)}))


if __name__ == "__main__":
    main()
