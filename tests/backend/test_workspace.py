from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from conftest import BUYER_EMAIL, auth_headers, campaign_body, launch
from services.core import workspace
from services.core.admin import DEFAULT_LIMITS
from services.core.source_fetch import FetchedPage


def _source(api, tenant, key, body, user=None):
    return api.post(
        "/api/v1/workspace/sources", headers=auth_headers(user or tenant.owner, tenant.organization_id, key=key), json=body
    )


def _workspace(api, tenant):
    return api.get("/api/v1/workspace", headers=auth_headers(tenant.owner, tenant.organization_id)).json()["data"]


def _profile_body(evidence_id, *, expected, key="approve-1", fact_text="Acme books demos from Gmail threads."):
    return {
        "expected_profile_version": expected,
        "approval_key": key,
        "name": "Acme Scheduling",
        "website_url": "https://acme.example",
        "timezone": "Asia/Kolkata",
        "approved_facts": [
            {"id": "F1", "text": fact_text, "evidence_ids": [evidence_id], "authority": "operator_approved", "approved": True}
        ],
        "faq": [{"question": "Pricing?", "answer": "Ask the seller.", "fact_ids": ["F1"]}],
        "forbidden_promises": ["No discounts"],
    }


def _policy_body(expected, **overrides):
    body = {
        "expected_config_version": expected,
        "simulation": True,
        "consented_recipients": [
            {"email": BUYER_EMAIL, "role": "buyer_test", "consent_record": "signed form #12",
             "consented_at": "2026-11-05T17:00:00Z"}
        ],
        "selected_calendar_id": "primary",
        "working_hours": {"timezone": "Asia/Kolkata", "weekdays": [5, 1, 2, 3, 4], "start": "09:00", "end": "17:00"},
        "duration_minutes": 15,
        "limits": dict(DEFAULT_LIMITS),
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------- sources


def test_pasted_text_source_creates_untrusted_evidence_and_replays(api, make_tenant, conn):
    tenant = make_tenant()
    body = {"kind": "pasted_text", "title": "About us", "text": "Acme books demos from Gmail threads."}

    first = _source(api, tenant, "src-1", body)
    again = _source(api, tenant, "src-1", body)
    conflict = _source(api, tenant, "src-1", {**body, "text": "Something else"})

    assert first.status_code == 201 and again.status_code == 200
    evidence = first.json()["data"]
    assert again.json()["data"]["id"] == evidence["id"]
    assert evidence["source_kind"] == "operator" and evidence["fact_status"] == "observed"
    assert conflict.status_code == 409
    row = conn.execute("select metadata_json from evidence where id = %s", (evidence["id"],)).fetchone()
    assert row["metadata_json"]["untrusted"] is True


def test_website_source_uses_fetcher_and_records_final_url(api, make_tenant, monkeypatch):
    tenant = make_tenant()
    monkeypatch.setattr(
        workspace,
        "fetch_page",
        lambda url: FetchedPage(url, "https://acme.example/home", 200, "text/html", "Acme\nBook demos faster", False),
    )

    response = _source(api, tenant, "web-1", {"kind": "website", "url": "https://acme.example"})

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["source_kind"] == "seller_website" and data["source_url"] == "https://acme.example/home"
    assert data["excerpt"] == "Acme\nBook demos faster"


def test_blocked_website_is_422_with_pasted_text_fallback_and_no_evidence(api, make_tenant, conn):
    tenant = make_tenant()

    response = _source(api, tenant, "web-bad", {"kind": "website", "url": "http://169.254.169.254/latest/meta-data/"})

    assert response.status_code == 422
    assert response.json()["error"]["details"]["fallback"] == "pasted_text"
    count = conn.execute(
        "select count(*) as n from evidence where organization_id = %s and source_kind = 'seller_website'",
        (tenant.organization_id,),
    ).fetchone()["n"]
    assert count == 0


def test_member_cannot_change_seller_setup(api, make_tenant):
    tenant = make_tenant()
    member = make_tenant.add_member(tenant)

    response = _source(api, tenant, "m-1", {"kind": "pasted_text", "title": "t", "text": "x"}, user=member)

    assert response.status_code == 403
    assert api.get("/api/v1/workspace", headers=auth_headers(member, tenant.organization_id)).json()["data"]["role"] == "member"


# ---------------------------------------------------------------- profile


def _evidence_id(api, tenant, key="fact-src"):
    body = {"kind": "pasted_text", "title": "Facts", "text": "Acme books demos from Gmail threads."}
    return _source(api, tenant, key, body).json()["data"]["id"]


def test_profile_approval_cas_and_replay(api, make_tenant):
    tenant = make_tenant()
    evidence_id = _evidence_id(api, tenant)
    start = _workspace(api, tenant)["profile_version"]
    headers = auth_headers(tenant.owner, tenant.organization_id)

    approved = api.put("/api/v1/workspace/profile", headers=headers, json=_profile_body(evidence_id, expected=start))
    replay = api.put("/api/v1/workspace/profile", headers=headers, json=_profile_body(evidence_id, expected=start))
    stale = api.put("/api/v1/workspace/profile", headers=headers, json=_profile_body(evidence_id, expected=start, key="approve-2"))
    key_reuse = api.put(
        "/api/v1/workspace/profile", headers=headers,
        json=_profile_body(evidence_id, expected=start + 1, fact_text="Different claim"),
    )

    assert approved.status_code == 200
    data = approved.json()["data"]
    assert data["profile_version"] == start + 1 and data["profile"]["approved_facts"][0]["id"] == "F1"
    assert replay.status_code == 200 and replay.json()["data"]["profile_version"] == start + 1
    assert stale.status_code == 409 and stale.json()["error"]["details"]["current_profile_version"] == start + 1
    assert key_reuse.status_code == 409


def test_profile_rejects_unknown_or_foreign_evidence(api, make_tenant):
    tenant, other = make_tenant(), make_tenant()
    foreign_evidence = _evidence_id(api, other)
    version = _workspace(api, tenant)["profile_version"]
    headers = auth_headers(tenant.owner, tenant.organization_id)

    foreign = api.put("/api/v1/workspace/profile", headers=headers, json=_profile_body(foreign_evidence, expected=version))
    unknown = api.put("/api/v1/workspace/profile", headers=headers, json=_profile_body(str(uuid4()), expected=version, key="k2"))

    assert foreign.status_code == 422 and unknown.status_code == 422
    assert foreign.json()["error"]["details"]["unknown_evidence_ids"] == [foreign_evidence]


def test_profile_rejects_faq_with_unknown_fact_and_empty_facts(api, make_tenant):
    tenant = make_tenant()
    evidence_id = _evidence_id(api, tenant)
    headers = auth_headers(tenant.owner, tenant.organization_id)
    body = _profile_body(evidence_id, expected=1)
    body["faq"][0]["fact_ids"] = ["F9"]

    assert api.put("/api/v1/workspace/profile", headers=headers, json=body).status_code == 400
    assert api.put("/api/v1/workspace/profile", headers=headers, json={**_profile_body(evidence_id, expected=1), "approved_facts": []}).status_code == 400


# ---------------------------------------------------------------- policy


def test_policy_update_cas_replay_and_validation(api, make_tenant):
    tenant = make_tenant()
    version = _workspace(api, tenant)["config_version"]
    headers = auth_headers(tenant.owner, tenant.organization_id, key="policy-1")

    ok = api.put("/api/v1/workspace/policy", headers=headers, json=_policy_body(version))
    replay = api.put("/api/v1/workspace/policy", headers=headers, json=_policy_body(version))
    stale = api.put("/api/v1/workspace/policy", headers={**headers, "Idempotency-Key": "policy-2"}, json=_policy_body(version))

    assert ok.status_code == 200 and ok.json()["data"]["config_version"] == version + 1
    assert ok.json()["data"]["policy"]["working_hours"]["weekdays"] == [1, 2, 3, 4, 5]
    assert replay.json()["data"]["config_version"] == version + 1
    assert stale.status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [
        {"simulation": False},
        {"consented_recipients": []},
        {"consented_recipients": [{"email": BUYER_EMAIL, "role": "buyer_test", "consent_record": "", "consented_at": "2026-11-05T17:00:00Z"}]},
        {"consented_recipients": [{"email": BUYER_EMAIL, "role": "buyer_test", "consent_record": "ok form"}]},
        {"consented_recipients": [
            {"email": BUYER_EMAIL, "role": "buyer_test", "consent_record": "a1b", "consented_at": "2026-11-05T17:00:00Z"},
            {"email": "second@example.invalid", "role": "buyer_test", "consent_record": "a2b", "consented_at": "2026-11-05T17:00:00Z"},
        ]},
        {"duration_minutes": 30},
        {"working_hours": {"timezone": "Mars/Base", "weekdays": [1], "start": "09:00", "end": "17:00"}},
    ],
)
def test_policy_requires_simulation_and_complete_consent(api, make_tenant, overrides):
    tenant = make_tenant()
    headers = auth_headers(tenant.owner, tenant.organization_id, key=f"bad-{uuid4()}")

    assert api.put("/api/v1/workspace/policy", headers=headers, json=_policy_body(1, **overrides)).status_code == 400


# ---------------------------------------------------------------- launch gate and snapshot


def test_launch_refused_when_founder_icp_missing(api, make_tenant, conn):
    tenant = make_tenant()
    conn.execute(
        "update organizations set approved_profile_json = approved_profile_json - 'ideal_customer' where id = %s",
        (tenant.organization_id,),
    )

    response = api.post(
        "/api/v1/campaigns",
        headers=auth_headers(tenant.owner, tenant.organization_id, key="no-icp"),
        json=campaign_body(tenant),
    )

    assert response.status_code == 422 and response.json()["error"]["details"]["field"] == "ideal_customer"


def test_launch_refused_when_facts_not_approved(api, make_tenant, conn):
    tenant = make_tenant()
    conn.execute(
        "update organizations set approved_profile_json = %s where id = %s",
        (Jsonb({"approved_facts": [], "placeholder": True}), tenant.organization_id),
    )

    response = api.post(
        "/api/v1/campaigns", headers=auth_headers(tenant.owner, tenant.organization_id, key="no-facts"), json=campaign_body(tenant)
    )

    assert response.status_code == 422 and response.json()["error"]["details"]["field"] == "profile"


def test_launch_refused_when_consent_incomplete(api, make_tenant, conn):
    tenant = make_tenant()
    conn.execute(
        "update organizations set policy_json = jsonb_set(policy_json, '{consented_recipients,0}', "
        "(policy_json -> 'consented_recipients' -> 0) - 'consented_at') where id = %s",
        (tenant.organization_id,),
    )

    response = api.post(
        "/api/v1/campaigns", headers=auth_headers(tenant.owner, tenant.organization_id, key="no-consent"), json=campaign_body(tenant)
    )

    assert response.status_code == 422 and response.json()["error"]["code"] == "RECIPIENT_NOT_ALLOWED"


def test_launch_snapshot_is_immutable_and_survives_profile_change(api, make_tenant, conn, database_url):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    evidence_id = _evidence_id(api, tenant)
    api.put("/api/v1/workspace/profile", headers=auth_headers(tenant.owner, tenant.organization_id),
            json=_profile_body(evidence_id, expected=1, fact_text="A newer approved claim"))

    snapshot = conn.execute("select launch_snapshot_json from campaigns where id = %s", (launched.id,)).fetchone()["launch_snapshot_json"]

    assert snapshot["profile_version"] == 1 and snapshot["config_version"] == 1
    assert [f["text"] for f in snapshot["approved_profile"]["approved_facts"]] == [
        "Pytest Seller offers a scheduling assistant for B2B sales teams."
    ]
    assert snapshot["policy"]["buyer_test"]["email"] == BUYER_EMAIL
    with pytest.raises(psycopg.errors.InsufficientPrivilege), conn.transaction():
        conn.execute("update campaigns set launch_snapshot_json = '{}'::jsonb where id = %s", (launched.id,))
    stale_launch = api.post(
        "/api/v1/campaigns", headers=auth_headers(tenant.owner, tenant.organization_id, key="after-change"), json=campaign_body(tenant)
    )
    assert stale_launch.status_code == 409
