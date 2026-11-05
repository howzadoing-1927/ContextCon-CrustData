from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from conftest import auth_headers, campaign_body, launch
from services.api.main import create_app
from services.core import db
from services.core.config import get_settings
from services.core.contracts.envelopes import SuccessEnvelope
from services.core.contracts.views import CampaignView, DecisionView, DemoSessionView, MembershipsView, OrganizationView


def _client(monkeypatch, **env) -> TestClient:
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    db.reset_pool()
    return TestClient(create_app())


def test_cors_allows_exact_configured_origin_only(monkeypatch):
    client = _client(monkeypatch, ALLOWED_CORS_ORIGINS="http://localhost:3100")
    allowed = client.options(
        "/api/v1/health/live",
        headers={
            "Origin": "http://localhost:3100",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-organization-id,idempotency-key",
        },
    )
    denied = client.options(
        "/api/v1/health/live",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3100"
    headers = allowed.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in headers and "x-organization-id" in headers and "idempotency-key" in headers
    assert denied.headers.get("access-control-allow-origin") != "https://evil.example"
    get_settings.cache_clear()
    db.reset_pool()


def test_memberships_lists_orgs_without_organization_header(api, make_tenant):
    tenant = make_tenant()
    headers = {"Authorization": f"Bearer {tenant.owner.token}"}

    response = api.get("/api/v1/me/memberships", headers=headers)

    assert response.status_code == 200
    data = SuccessEnvelope[MembershipsView].model_validate(response.json()).data
    assert [item.organization_id for item in data.items] == [tenant.organization_id]
    assert data.items[0].role == "owner" and data.items[0].organization_name


def test_campaign_list_includes_conversation_state_and_cursor(api, make_tenant, database_url):
    tenant = make_tenant()
    first = launch(database_url, tenant, key="list-a")
    second = launch(database_url, tenant, key="list-b", request_text="Book a second demo with a logistics sales lead.")
    headers = auth_headers(tenant.owner, tenant.organization_id)

    page = api.get("/api/v1/campaigns", headers=headers, params={"limit": 1})
    body = page.json()["data"]
    items = [CampaignView.model_validate(item) for item in body["items"]]

    assert page.status_code == 200
    assert len(items) == 1 and items[0].id == second.id
    assert items[0].conversation_state is None
    assert body["next_cursor"]
    rest = api.get("/api/v1/campaigns", headers=headers, params={"cursor": body["next_cursor"], "limit": 10})
    rest_items = rest.json()["data"]["items"]
    assert [row["id"] for row in rest_items] == [str(first.id)]
    assert rest.json()["data"]["next_cursor"] is None


def test_ledger_is_oldest_first_with_stable_cursor(api, make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    conn.execute(
        "insert into decisions (organization_id, campaign_id, kind, status, reason, input_refs_json, policy_result_json) "
        "values (%s, %s, 'research', 'accepted', 'later', '{}'::jsonb, %s)",
        (tenant.organization_id, launched.id, Jsonb({"pass": True, "checks": []})),
    )
    headers = auth_headers(tenant.owner, tenant.organization_id)

    page = api.get(f"/api/v1/campaigns/{launched.id}/ledger", headers=headers, params={"limit": 1})
    items = [DecisionView.model_validate(item) for item in page.json()["data"]["items"]]
    rest = api.get(
        f"/api/v1/campaigns/{launched.id}/ledger",
        headers=headers,
        params={"cursor": page.json()["data"]["next_cursor"], "limit": 10},
    )

    assert items[0].kind == "campaign_launch"
    assert [row["kind"] for row in rest.json()["data"]["items"]] == ["research"]
    missing = api.get(f"/api/v1/campaigns/{uuid4()}/ledger", headers=headers)
    assert missing.status_code == 404


def test_brief_maps_onto_profile_cas_and_policy(api, make_tenant):
    tenant = make_tenant()
    source = api.post(
        "/api/v1/workspace/sources",
        headers=auth_headers(tenant.owner, tenant.organization_id, key="brief-src"),
        json={"kind": "pasted_text", "title": "About", "text": "Brief Seller schedules field visits for fleet operators."},
    ).json()["data"]
    workspace = api.get("/api/v1/workspace", headers=auth_headers(tenant.owner, tenant.organization_id)).json()["data"]
    body = {
        "expected_profile_version": workspace["profile_version"],
        "name": "Brief Seller",
        "website_url": "https://brief.example/",
        "timezone": "Asia/Kolkata",
        "seller_brief": {
            "founder_name": "Ada",
            "founder_email": "ada@brief.example",
            "service": "Field-service scheduling",
            "pricing": None,
            "capacity": "12 operators",
        },
        "ideal_customer": {
            "customer_type": "Fleet operators",
            "regions": ["India"],
            "buyer_roles": ["Head of Operations"],
            "timeline": None,
            "criteria": ["Runs 50 or more field vehicles"],
            "exclusions": [],
        },
        "description": "Brief Seller schedules field visits for fleet operators.",
        "approved_fact_ids": [],
        "proposed_facts": [
            {"id": "brief-onboarding", "text": "Onboarding takes two weeks.", "evidence_ids": [source["id"]]}
        ],
        "evidence": [source],
        "escalation_topics": ["Discounts or custom pricing"],
        "working_hours": {"timezone": "Asia/Kolkata", "weekdays": [1, 2, 3, 4, 5], "start": "10:00", "end": "16:00"},
        "duration_minutes": 15,
    }
    headers = auth_headers(tenant.owner, tenant.organization_id, key="brief-1")

    saved = api.put("/api/v1/workspace/brief", headers=headers, json=body)
    replay = api.put("/api/v1/workspace/brief", headers=headers, json=body)
    stale = api.put("/api/v1/workspace/brief", headers={**headers, "Idempotency-Key": "brief-2"}, json=body)
    data = OrganizationView.model_validate(saved.json()["data"])

    assert saved.status_code == 200
    assert data.name == "Brief Seller" and data.profile_version == workspace["profile_version"] + 1
    assert data.config_version == workspace["config_version"] + 1
    assert data.seller_brief.founder_name == "Ada"
    assert data.ideal_customer.customer_type == "Fleet operators"
    assert data.profile.forbidden_promises == ["Discounts or custom pricing"]
    assert data.policy.working_hours["start"] == "10:00"
    assert any(fact["id"] == "brief-description" for fact in data.profile.approved_facts)
    assert source["id"] not in data.profile.approved_facts[0]["evidence_ids"]
    assert data.viewer_role == "owner" and data.approved_facts
    assert replay.status_code == 200 and replay.json()["data"]["profile_version"] == data.profile_version
    assert stale.status_code == 409


def test_demo_session_flag_off_is_404(api):
    assert api.post("/api/v1/demo/session").status_code == 404


def test_demo_session_mints_token_for_seeded_workspace(monkeypatch, make_tenant, api):
    if not get_settings().supabase_jwt_secret:
        pytest.skip("demo session minting needs SUPABASE_JWT_SECRET")
    tenant = make_tenant()
    client = _client(
        monkeypatch,
        DEMO_SESSION_ENABLED="true",
        DEMO_ORGANIZATION_ID=str(tenant.organization_id),
    )

    response = client.post("/api/v1/demo/session")
    data = SuccessEnvelope[DemoSessionView].model_validate(response.json()).data
    me = client.get("/api/v1/me/memberships", headers={"Authorization": f"Bearer {data.access_token}"})
    workspace = client.get(
        "/api/v1/workspace",
        headers={"Authorization": f"Bearer {data.access_token}", "X-Organization-ID": str(data.organization_id)},
    )

    assert response.status_code == 200
    assert data.session_kind == "demo" and data.organization_id == tenant.organization_id
    assert me.status_code == 200 and workspace.status_code == 200
    get_settings.cache_clear()
    db.reset_pool()


def test_demo_launch_without_google_is_waived_not_passed(api, make_tenant, conn):
    tenant = make_tenant(seller_connected=False)
    conn.execute(
        "update organizations set policy_json = policy_json || %s where id = %s",
        (Jsonb({"demo_allow_launch_without_google": True}), tenant.organization_id),
    )

    response = api.post(
        "/api/v1/campaigns",
        headers=auth_headers(tenant.owner, tenant.organization_id, key="demo-launch"),
        json=campaign_body(tenant),
    )
    decision = conn.execute(
        "select policy_result_json from decisions where organization_id = %s and kind = 'campaign_launch'",
        (tenant.organization_id,),
    ).fetchone()["policy_result_json"]
    google = next(c for c in decision["checks"] if c["name"] == "seller_google_ready")

    assert response.status_code == 202
    assert google["pass"] is False and google["status"] == "waived (demo)"
    assert decision["pass"] is True
    ledger = api.get(
        f"/api/v1/campaigns/{response.json()['data']['id']}/ledger",
        headers=auth_headers(tenant.owner, tenant.organization_id),
    )
    check = next(c for c in ledger.json()["data"]["items"][0]["policy"]["checks"] if "seller_google_ready" in c["name"])
    assert check["pass"] is False and check["reason"].startswith("[waived (demo)]")
