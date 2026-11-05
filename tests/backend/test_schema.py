import hashlib
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from conftest import launch
from services.core.config import get_settings

APPLICATION_TABLES = {
    "organizations", "memberships", "connections", "campaigns", "prospects", "evidence",
    "decisions", "conversations", "messages", "tasks", "actions", "suppressions",
}


def test_exactly_twelve_application_tables(conn):
    rows = conn.execute(
        "select table_name from information_schema.tables where table_schema = %s and table_type = 'BASE TABLE'",
        (get_settings().db_schema,),
    ).fetchall()

    assert {r["table_name"] for r in rows} == APPLICATION_TABLES


def test_rls_enabled_on_every_application_table(conn):
    rows = conn.execute(
        "select relname from pg_class where relnamespace = %s::regnamespace and relkind = 'r' and relrowsecurity",
        (get_settings().db_schema,),
    ).fetchall()

    assert {r["relname"] for r in rows} == APPLICATION_TABLES


def test_composite_fk_rejects_cross_tenant_parent(conn, make_tenant, database_url):
    tenant_a, tenant_b = make_tenant(), make_tenant()
    campaign_a = launch(database_url, tenant_a)

    with pytest.raises(psycopg.errors.ForeignKeyViolation), conn.transaction():
        conn.execute(
            "insert into tasks (organization_id, campaign_id, kind, dedupe_key, payload_json, status) "
            "values (%s, %s, 'research', %s, '{}'::jsonb, 'ready')",
            (tenant_b.organization_id, campaign_a.id, f"cross:{uuid4()}"),
        )


def _decision(conn, tenant, campaign_id, status="blocked"):
    return conn.execute(
        "insert into decisions (organization_id, campaign_id, kind, status, reason, policy_result_json) "
        "values (%s, %s, 'test', %s, 'pytest', %s) returning id",
        (tenant.organization_id, campaign_id, status, Jsonb({"pass": False, "checks": []})),
    ).fetchone()["id"]


def test_decisions_are_append_only_except_one_resolution(conn, make_tenant, database_url):
    tenant = make_tenant()
    campaign = launch(database_url, tenant)
    decision_id = _decision(conn, tenant, campaign.id)

    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute("update decisions set reason = 'rewritten' where id = %s", (decision_id,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute("delete from decisions where id = %s", (decision_id,))

    conn.execute(
        "update decisions set status = 'resolved', resolution_json = %s where id = %s",
        (Jsonb({"resolution_type": "stop"}), decision_id),
    )
    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute(
            "update decisions set resolution_json = %s where id = %s", (Jsonb({"again": True}), decision_id)
        )


def test_evidence_is_immutable(conn, make_tenant, database_url):
    tenant = make_tenant()
    campaign = launch(database_url, tenant)
    evidence_id = conn.execute(
        "insert into evidence (organization_id, campaign_id, entity_kind, source_kind, excerpt, retrieved_at, "
        "content_sha256, fact_status) values (%s, %s, 'campaign', 'policy', 'x', now(), %s, 'observed') returning id",
        (tenant.organization_id, campaign.id, hashlib.sha256(b"x").hexdigest()),
    ).fetchone()["id"]

    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute("update evidence set excerpt = 'y' where id = %s", (evidence_id,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute("delete from evidence where id = %s", (evidence_id,))


def test_evidence_storage_path_must_start_with_org(conn, make_tenant, database_url):
    tenant = make_tenant()
    campaign = launch(database_url, tenant)

    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        conn.execute(
            "insert into evidence (organization_id, campaign_id, entity_kind, source_kind, excerpt, retrieved_at, "
            "content_sha256, fact_status, storage_path) values (%s, %s, 'campaign', 'policy', 'x', now(), %s, 'observed', %s)",
            (tenant.organization_id, campaign.id, "0" * 64, f"{uuid4()}/snapshot.json"),
        )


def test_message_connection_must_match_conversation(conn, make_tenant, database_url):
    tenant = make_tenant()
    campaign = launch(database_url, tenant)
    org = tenant.organization_id
    seller = conn.execute(
        "select id from connections where organization_id = %s and purpose = 'seller'", (org,)
    ).fetchone()["id"]
    other = conn.execute(
        "insert into connections (organization_id, provider, purpose, status) "
        "values (%s, 'google', 'buyer_test', 'pending') returning id",
        (org,),
    ).fetchone()["id"]
    prospect = conn.execute(
        "insert into prospects (organization_id, campaign_id, canonical_company_ref, status) "
        "values (%s, %s, 'co-1', 'researching') returning id",
        (org, campaign.id),
    ).fetchone()["id"]
    conversation = conn.execute(
        "insert into conversations (organization_id, campaign_id, prospect_id, connection_id, buyer_test_email, state) "
        "values (%s, %s, %s, %s, 'consenting-buyer@example.invalid', 'researching') returning id",
        (org, campaign.id, prospect, seller),
    ).fetchone()["id"]

    with pytest.raises(psycopg.errors.ForeignKeyViolation), conn.transaction():
        conn.execute(
            "insert into messages (organization_id, conversation_id, connection_id, direction, from_email, to_emails, "
            "body_text, body_sha256, status) values (%s, %s, %s, 'outbound', 'a@b.co', '{c@d.co}', 'x', %s, 'planned')",
            (org, conversation, other, "0" * 64),
        )
