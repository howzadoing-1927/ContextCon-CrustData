from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from conftest import auth_headers, campaign_body, launch
from services.core.contracts.envelopes import SuccessEnvelope
from services.core.contracts.views import CampaignLaunchView


def _post(api, tenant, key, body):
    return api.post("/api/v1/campaigns", headers=auth_headers(tenant.owner, tenant.organization_id, key=key), json=body)


def _counts(conn, org):
    return conn.execute(
        """
        select (select count(*) from campaigns where organization_id = %(o)s) as campaigns,
               (select count(*) from tasks where organization_id = %(o)s) as tasks,
               (select count(*) from decisions where organization_id = %(o)s) as decisions
        """,
        {"o": org},
    ).fetchone()


def test_launch_persists_campaign_task_and_decision_atomically(api, make_tenant, conn):
    tenant = make_tenant()

    response = _post(api, tenant, "launch-1", campaign_body(tenant))

    assert response.status_code == 202
    view = SuccessEnvelope[CampaignLaunchView].model_validate(response.json()).data
    assert view.status == "running" and view.stage == "normalize_mission" and view.version == 1
    assert view.usage.estimated_cost is None
    task = conn.execute(
        "select kind, status, dedupe_key, payload_json, attempt, lease_generation from tasks "
        "where organization_id = %s and id = %s",
        (tenant.organization_id, view.task_id),
    ).fetchone()
    assert task["kind"] == "normalize_mission" and task["status"] == "ready"
    assert task["dedupe_key"] == f"campaign:{view.id}:normalize_mission"
    assert task["payload_json"]["campaign_id"] == str(view.id)
    assert (task["attempt"], task["lease_generation"]) == (0, 0)
    decision = conn.execute(
        "select id, kind, status, task_id, policy_result_json from decisions where organization_id = %s",
        (tenant.organization_id,),
    ).fetchone()
    assert decision["kind"] == "campaign_launch" and decision["status"] == "accepted"
    assert decision["task_id"] == view.task_id and view.last_decision_id == decision["id"]
    assert decision["policy_result_json"]["pass"] is True


def test_duplicate_launch_same_key_and_body_is_idempotent(api, make_tenant, conn):
    tenant = make_tenant()
    body = campaign_body(tenant)

    first = _post(api, tenant, "dup-key", body)
    second = _post(api, tenant, "dup-key", body)

    assert first.status_code == second.status_code == 202
    assert first.json()["data"] == second.json()["data"]
    assert dict(_counts(conn, tenant.organization_id)) == {"campaigns": 1, "tasks": 1, "decisions": 1}


def test_same_key_different_body_is_409(api, make_tenant, conn):
    tenant = make_tenant()
    _post(api, tenant, "conflict-key", campaign_body(tenant))

    response = _post(api, tenant, "conflict-key", campaign_body(tenant, request_text="A different mission."))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"
    assert dict(_counts(conn, tenant.organization_id)) == {"campaigns": 1, "tasks": 1, "decisions": 1}


def test_concurrent_duplicate_launch_creates_one_campaign(make_tenant, database_url, conn):
    tenant = make_tenant()
    key = f"race-{uuid4()}"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: launch(database_url, tenant, key), range(4)))

    assert len({r.id for r in results}) == 1 and len({r.task_id for r in results}) == 1
    assert dict(_counts(conn, tenant.organization_id)) == {"campaigns": 1, "tasks": 1, "decisions": 1}


def test_stale_profile_version_is_409(api, make_tenant, conn):
    tenant = make_tenant()

    response = _post(api, tenant, "stale", campaign_body(tenant, profile_version=2))

    assert response.status_code == 409
    assert _counts(conn, tenant.organization_id)["campaigns"] == 0


def test_unconsented_recipient_is_422(api, make_tenant, conn):
    tenant = make_tenant()

    response = _post(api, tenant, "recipient", campaign_body(tenant, buyer_test_email="researched.person@example.com"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RECIPIENT_NOT_ALLOWED"
    assert _counts(conn, tenant.organization_id)["tasks"] == 0


def test_limits_above_policy_or_contract_rejected(api, make_tenant):
    tenant = make_tenant()
    body = campaign_body(tenant)
    body["limits"] = {**body["limits"], "max_conversations": 2}

    assert _post(api, tenant, "limits", body).status_code == 400


def test_missing_seller_connection_is_422(api, make_tenant, conn):
    tenant = make_tenant(seller_connected=False)

    response = _post(api, tenant, "no-google", campaign_body(tenant))

    assert response.status_code == 422
    assert "missing_scopes" in response.json()["error"]["details"]
    assert _counts(conn, tenant.organization_id)["tasks"] == 0


def test_missing_idempotency_key_is_400(api, make_tenant):
    tenant = make_tenant()

    response = api.post(
        "/api/v1/campaigns", headers=auth_headers(tenant.owner, tenant.organization_id), json=campaign_body(tenant)
    )

    assert response.status_code == 400
    assert response.json()["error"]["details"]["field"] == "Idempotency-Key"


def test_body_tenant_field_is_rejected(api, make_tenant):
    tenant = make_tenant()
    body = {**campaign_body(tenant), "organization_id": str(UUID(int=1))}

    assert _post(api, tenant, "tenant-in-body", body).status_code == 400
