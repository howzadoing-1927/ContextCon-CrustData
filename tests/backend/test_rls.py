"""Direct-client access: SQL-level (any database with the migration) and, in gotrue mode, through the real
Supabase Data API (PostgREST) and Storage with the anon key + user JWT."""

import json
import os
from uuid import uuid4

import httpx2
import psycopg
import pytest
from psycopg import sql

from conftest import launch
from services.core.config import get_settings

SERVER_ONLY_TABLES = ("connections", "tasks", "actions")


def _as_role(conn, role, user_id=None):
    conn.execute(f"set local role {role}")
    claims = {"sub": str(user_id), "role": role} if user_id else {"role": role}
    conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))


@pytest.mark.parametrize("table", SERVER_ONLY_TABLES)
def test_authenticated_client_cannot_read_server_only_tables(conn, make_tenant, table):
    tenant = make_tenant()

    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        _as_role(conn, "authenticated", tenant.owner.id)
        conn.execute(f"select id from {table} limit 1")


def test_member_sees_only_own_campaigns_and_decisions(conn, make_tenant, database_url):
    tenant_a, tenant_b = make_tenant(), make_tenant()
    campaign_a, campaign_b = launch(database_url, tenant_a), launch(database_url, tenant_b)

    with conn.transaction():
        _as_role(conn, "authenticated", tenant_a.owner.id)
        campaigns = {r["id"] for r in conn.execute("select id from campaigns").fetchall()}
        decision_orgs = {r["organization_id"] for r in conn.execute("select organization_id from decisions").fetchall()}
        orgs = {r["id"] for r in conn.execute("select id from organizations").fetchall()}
        conn.execute("reset role")

    assert campaign_a.id in campaigns and campaign_b.id not in campaigns
    assert decision_orgs == {tenant_a.organization_id}
    assert orgs == {tenant_a.organization_id}


def test_member_cannot_read_org_policy_or_runtime_columns(conn, make_tenant):
    tenant = make_tenant()

    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        _as_role(conn, "authenticated", tenant.owner.id)
        conn.execute("select policy_json from organizations")


def test_authenticated_client_cannot_write(conn, make_tenant, database_url):
    tenant = make_tenant()
    campaign = launch(database_url, tenant)

    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        _as_role(conn, "authenticated", tenant.owner.id)
        conn.execute("update campaigns set status = 'completed' where id = %s", (campaign.id,))


@pytest.mark.parametrize("table", ["campaigns", "organizations", "tasks"])
def test_anon_role_has_no_access(conn, make_tenant, table):
    make_tenant()

    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        _as_role(conn, "anon")
        conn.execute(sql.SQL("select 1 from {}.{} limit 1").format(
            sql.Identifier(get_settings().db_schema), sql.Identifier(table)
        ))


def test_storage_objects_policy_is_org_prefixed(conn, make_tenant, auth_mode):
    if auth_mode != "local_jwt":
        pytest.skip("on Supabase, storage is exercised through the Storage API in test_storage_api_*")
    tenant_a, tenant_b = make_tenant(), make_tenant()
    names = [f"{tenant_a.organization_id}/a.json", f"{tenant_b.organization_id}/b.json", "not-a-uuid/c.json"]
    bucket_id = get_settings().storage_bucket
    for name in names:
        conn.execute("insert into storage.objects (bucket_id, name) values (%s, %s)", (bucket_id, name))
    try:
        with conn.transaction():
            _as_role(conn, "authenticated", tenant_a.owner.id)
            visible = {r["name"] for r in conn.execute("select name from storage.objects").fetchall()}
            conn.execute("reset role")
        assert visible == {names[0]}
        bucket = conn.execute("select public from storage.buckets where id = %s", (bucket_id,)).fetchone()
        assert bucket["public"] is False
    finally:
        conn.execute("delete from storage.objects where name = any(%s)", (names,))


# ---------------------------------------------------------------- real Supabase Data API / Storage

@pytest.fixture
def rest(auth_mode):
    if auth_mode != "gotrue":
        pytest.skip("PostgREST/Storage checks need a real Supabase project (gotrue mode)")
    return os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_ANON_KEY"]


def _client_headers(anon_key, token=None):
    # Profile headers make PostgREST target our schema, never a same-named table in another app's schema.
    schema = get_settings().db_schema
    return {
        "apikey": anon_key,
        "Authorization": f"Bearer {token or anon_key}",
        "Accept-Profile": schema,
        "Content-Profile": schema,
    }


def _schema_not_exposed(response) -> bool:
    return response.status_code == 406 and "PGRST106" in response.text


@pytest.mark.parametrize("table", SERVER_ONLY_TABLES)
def test_data_api_denies_server_only_tables(rest, make_tenant, table):
    base, anon = rest
    tenant = make_tenant()

    response = httpx2.get(f"{base}/rest/v1/{table}?select=id", headers=_client_headers(anon, tenant.owner.token), timeout=15)

    assert response.status_code in (401, 403) or _schema_not_exposed(response), response.text


def test_data_api_scopes_campaigns_to_member_and_denies_anon_and_writes(rest, make_tenant, database_url):
    base, anon = rest
    tenant_a, tenant_b = make_tenant(), make_tenant()
    campaign_a, campaign_b = launch(database_url, tenant_a), launch(database_url, tenant_b)

    own = httpx2.get(f"{base}/rest/v1/campaigns?select=id", headers=_client_headers(anon, tenant_a.owner.token), timeout=15)
    if _schema_not_exposed(own):
        pytest.skip(f"schema {get_settings().db_schema!r} is not exposed via the Data API: no direct-client path exists")
    anonymous = httpx2.get(f"{base}/rest/v1/campaigns?select=id", headers=_client_headers(anon), timeout=15)
    write = httpx2.patch(
        f"{base}/rest/v1/campaigns?id=eq.{campaign_a.id}",
        headers=_client_headers(anon, tenant_a.owner.token),
        json={"status": "completed"},
        timeout=15,
    )

    ids = {row["id"] for row in own.json()}
    assert own.status_code == 200 and str(campaign_a.id) in ids and str(campaign_b.id) not in ids
    assert anonymous.status_code in (401, 403)
    assert write.status_code in (401, 403)


def test_storage_api_private_bucket_org_prefix(rest, make_tenant):
    base, anon = rest
    bucket = get_settings().storage_bucket
    tenant_a, tenant_b = make_tenant(), make_tenant()
    service = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    path = f"{tenant_a.organization_id}/pytest-{uuid4().hex}.txt"
    upload = httpx2.post(
        f"{base}/storage/v1/object/{bucket}/{path}",
        headers={"apikey": service, "Authorization": f"Bearer {service}", "Content-Type": "text/plain"},
        content=b"outcome evidence",
        timeout=15,
    )
    assert upload.status_code in (200, 201), upload.text
    try:
        user_headers = {"apikey": anon}
        own = httpx2.get(
            f"{base}/storage/v1/object/authenticated/{bucket}/{path}",
            headers={**user_headers, "Authorization": f"Bearer {tenant_a.owner.token}"},
            timeout=15,
        )
        foreign = httpx2.get(
            f"{base}/storage/v1/object/authenticated/{bucket}/{path}",
            headers={**user_headers, "Authorization": f"Bearer {tenant_b.owner.token}"},
            timeout=15,
        )
        public = httpx2.get(f"{base}/storage/v1/object/public/{bucket}/{path}", timeout=15)
        assert own.status_code == 200 and own.content == b"outcome evidence"
        assert foreign.status_code != 200
        assert public.status_code != 200
    finally:
        httpx2.request(
            "DELETE",
            f"{base}/storage/v1/object/{bucket}",
            headers={"apikey": service, "Authorization": f"Bearer {service}"},
            json={"prefixes": [path]},
            timeout=15,
        )
