import json
from datetime import UTC, datetime

import httpx2
import openai
import pytest

from conftest import BUYER_EMAIL, launch
from services.core import db
from services.core.campaigns import get_mission_detail
from services.core.config import get_settings
from services.core.contracts.model_io import NormalizedPlan
from services.models.client import AzureModelClient, ModelCall, ModelUnavailable
from services.models.normalize import apply_founder_icp, build_envelope, normalize_mission, repair_plan
from services.worker import queue
from services.worker.handlers import handle_normalize_mission

VALID_PLAN = {
    "objective": "book_demo",
    "geography": ["India"],
    "industries": ["Logistics"],
    "company_rules": [
        {"field": "industry", "operator": "contains", "value": "logistics", "must_have": True},
        {"field": "employee_count", "operator": "range", "value": [50, 500], "must_have": False},
    ],
    "buyer_roles": ["Head of Sales"],
    "exclusions": ["Existing customers"],
    "missing_required_fields": [],
    "assumptions": [{"text": "Mid-market means 50-500 employees", "status": "hypothesis"}],
    "research_queries": [{"intent": "find logistics companies in India with a sales team", "limit": 5}],
    "stop_conditions": ["No qualified prospect after 3 enrichments"],
}

SNAPSHOT = {
    "profile_version": 1,
    "config_version": 1,
    "seller": {"name": "Acme", "website_url": "https://acme.example", "timezone": "Asia/Kolkata"},
    "approved_profile": {
        "approved_facts": [{"id": "F1", "text": "Acme books demos.", "evidence_ids": ["e"], "authority": "operator_approved", "approved": True}],
        "faq": [],
        "forbidden_promises": [],
    },
    "policy": {"simulation": True, "buyer_test": {"email": BUYER_EMAIL}, "limits": {"max_discovered": 10, "max_research_calls": 10, "max_model_calls": 20}},
}


class FakeClient:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.requests = []

    def complete_json(self, **kwargs):
        self.requests.append(kwargs)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return ModelCall(
            role="fast", deployment="fixture-fast", prompt_version=kwargs["prompt_version"], attempt=kwargs["attempt"],
            output_mode="json_schema_strict", latency_ms=5, model_version="fixture-model",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
            content=output if isinstance(output, str) else json.dumps(output),
        )


# ---------------------------------------------------------------- model step (no DB)


def test_valid_plan_validates_and_passes_policy():
    outcome = normalize_mission(FakeClient(VALID_PLAN), campaign_id="c", request_text="Find logistics", snapshot=SNAPSHOT)

    assert outcome.plan == repair_plan(NormalizedPlan.model_validate(VALID_PLAN))
    assert outcome.policy_violations == [] and len(outcome.calls) == 1


def test_founder_icp_overwrites_market_from_request_text():
    snapshot = {
        **SNAPSHOT,
        "ideal_customer": {
            "customer_type": "K-12 schools",
            "regions": ["India"],
            "buyer_roles": ["Principal", "School administrator"],
            "timeline": None,
            "criteria": ["Has an academic coordinator"],
            "exclusions": ["universities"],
        },
    }

    outcome = normalize_mission(
        FakeClient(VALID_PLAN),
        campaign_id="c",
        request_text="Book a demo with a mid-market logistics company's head of sales.",
        snapshot=snapshot,
    )

    assert outcome.plan.industries == ["K-12 schools"]
    assert outcome.plan.buyer_roles == ["Principal", "School administrator"]
    assert outcome.plan.geography == ["India"]
    assert outcome.plan.exclusions == ["universities"]


def test_repair_drops_filled_missing_and_demotes_unmapped_must_haves():
    raw = {
        **VALID_PLAN,
        "missing_required_fields": [
            "geography",
            "confirmation of company size fitting mid-market definition",
            "budget",
        ],
        "company_rules": [
            {"field": "company_size", "operator": "range", "value": [50, 1000], "must_have": True},
            {"field": "company_market_segment", "operator": "equals", "value": "mid-market", "must_have": True},
        ],
    }

    plan = repair_plan(NormalizedPlan.model_validate(raw))

    assert plan.missing_required_fields == ["budget"]
    assert plan.company_rules[0].must_have is True
    assert plan.company_rules[1].must_have is False


def test_invalid_output_gets_one_repair_with_errors():
    client = FakeClient({**VALID_PLAN, "objective": "sell_anything"}, VALID_PLAN)

    outcome = normalize_mission(client, campaign_id="c", request_text="x", snapshot=SNAPSHOT)

    assert outcome.plan is not None and len(outcome.calls) == 2
    assert "failed validation" in client.requests[1]["user"]


def test_two_invalid_outputs_give_no_plan():
    outcome = normalize_mission(FakeClient("not json", {**VALID_PLAN, "extra": 1}), campaign_id="c", request_text="x", snapshot=SNAPSHOT)

    assert outcome.plan is None and len(outcome.validation_errors) == 2


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"research_queries": [{"intent": "find", "limit": 5}] * 3}, "max_research_calls"),
        ({"research_queries": [{"intent": "https://evil.example/?q=1", "limit": 5}]}, "URL/SQL"),
        ({"research_queries": [{"intent": "x; drop table tasks", "limit": 5}]}, "URL/SQL"),
        ({"research_queries": []}, "no research queries"),
    ],
)
def test_plan_policy_violations(change, expected):
    snapshot = {**SNAPSHOT, "policy": {**SNAPSHOT["policy"], "limits": {"max_discovered": 10, "max_research_calls": 2}}}

    outcome = normalize_mission(FakeClient({**VALID_PLAN, **change}), campaign_id="c", request_text="x", snapshot=snapshot)

    assert outcome.plan is not None
    assert any(expected in v for v in outcome.policy_violations), outcome.policy_violations


def test_query_limit_above_max_discovered_is_violation():
    snapshot = {**SNAPSHOT, "policy": {**SNAPSHOT["policy"], "limits": {"max_discovered": 3, "max_research_calls": 10}}}

    outcome = normalize_mission(FakeClient(VALID_PLAN), campaign_id="c", request_text="x", snapshot=snapshot)

    assert any("max_discovered" in v for v in outcome.policy_violations)


def test_envelope_never_contains_recipients_or_tenant_secrets():
    envelope = build_envelope(campaign_id="c", request_text="Find logistics", snapshot=SNAPSHOT, now=datetime(2026, 11, 6, tzinfo=UTC))
    text = json.dumps(envelope)

    assert BUYER_EMAIL not in text and "evidence_ids" not in text
    assert envelope["approved_seller_profile"]["approved_facts"] == [{"id": "F1", "text": "Acme books demos."}]


def test_azure_client_falls_back_to_json_object_when_strict_schema_rejected(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://fixture.invalid")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fixture")
    monkeypatch.setenv("AZURE_OPENAI_FAST_DEPLOYMENT", "fast-dep")
    # Empty (not deleted): the settings loader would otherwise re-add these from a local .env.
    monkeypatch.setenv("AZURE_OPENAI_DECISION_DEPLOYMENT", "")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "")
    get_settings.cache_clear()
    client = AzureModelClient(get_settings())
    get_settings.cache_clear()
    seen = []

    class Choice:
        message = type("M", (), {"content": json.dumps(VALID_PLAN)})()

    def create(deployment, system, user, response_format):
        seen.append(response_format["type"])
        if response_format["type"] == "json_schema":
            response = httpx2.Response(400, request=httpx2.Request("POST", "https://fixture.invalid"))
            raise openai.BadRequestError("response_format json_schema not supported", response=response, body=None)
        return type("R", (), {"model": "m-1", "usage": type("U", (), {"prompt_tokens": 7, "completion_tokens": 3})(), "choices": [Choice]})()

    monkeypatch.setattr(client, "_create", create)
    call = client.complete_json(role="decision", system="s", user="u", schema_name="N", schema={}, prompt_version="p", attempt=1)

    assert seen == ["json_schema", "json_object"]
    assert call.output_mode == "json_object_fallback" and call.deployment == "fast-dep" and call.degraded_from == "decision"
    assert client.api_path == "azure v1"


# ---------------------------------------------------------------- worker handler (DB)


@pytest.fixture
def leased(make_tenant, database_url):
    tenant = make_tenant()
    launched = launch(database_url, tenant, request_text="Find mid-market logistics companies in India and their head of sales.")
    with db.connect(database_url) as c:
        lease = queue.claim(c, owner="pytest-worker", kinds=["normalize_mission"], lease_seconds=60, organization_id=tenant.organization_id)
    return tenant, launched, lease


def _campaign(conn, launched):
    return conn.execute(
        "select status, stage, version, normalized_plan_json, budget_json from campaigns where id = %s", (launched.id,)
    ).fetchone()


def _decisions(conn, launched):
    return conn.execute(
        "select kind, status, reason, model_metadata_json, policy_result_json from decisions "
        "where campaign_id = %s and kind = 'normalize_mission' order by created_at", (launched.id,)
    ).fetchall()


def _task_status(conn, lease):
    return conn.execute("select status from tasks where id = %s", (lease.task_id,)).fetchone()["status"]


def test_handler_accepts_valid_plan_and_queues_research(leased, conn):
    tenant, launched, lease = leased

    handle_normalize_mission(conn, lease, client=FakeClient(VALID_PLAN))

    campaign = _campaign(conn, launched)
    assert (campaign["status"], campaign["stage"], campaign["version"]) == ("running", "research", 2)
    snapshot = conn.execute(
        "select launch_snapshot_json from campaigns where id = %s", (launched.id,)
    ).fetchone()["launch_snapshot_json"]
    expected = repair_plan(apply_founder_icp(NormalizedPlan.model_validate(VALID_PLAN), snapshot)).model_dump(mode="json")
    assert campaign["normalized_plan_json"] == expected
    assert campaign["budget_json"]["usage"]["model_calls"] == 1 and campaign["budget_json"]["usage"]["tokens_in"] == 100
    [decision] = _decisions(conn, launched)
    assert decision["status"] == "accepted" and decision["policy_result_json"]["pass"] is True
    assert decision["model_metadata_json"]["deployment"] == "fixture-fast"
    assert decision["model_metadata_json"]["prompt_version"] == "normalize_mission.v3"
    research = conn.execute(
        "select status from tasks where organization_id = %s and kind = 'research'", (tenant.organization_id,)
    ).fetchall()
    assert [r["status"] for r in research] == ["ready"]
    assert _task_status(conn, lease) == "succeeded"


def test_handler_missing_required_fields_needs_human_without_research(leased, conn):
    tenant, launched, lease = leased
    plan = {**VALID_PLAN, "missing_required_fields": ["budget"]}

    handle_normalize_mission(conn, lease, client=FakeClient(plan))

    campaign = _campaign(conn, launched)
    assert (campaign["status"], campaign["stage"]) == ("needs_human", "clarification")
    [decision] = _decisions(conn, launched)
    assert decision["status"] == "blocked"
    assert conn.execute(
        "select count(*) as n from tasks where organization_id = %s and kind = 'research'", (tenant.organization_id,)
    ).fetchone()["n"] == 0
    with db.connect() as c:
        detail = get_mission_detail(c, organization_id=tenant.organization_id, campaign_id=launched.id)
    assert detail.open_exceptions[0].model.deployment == "fixture-fast"


def test_handler_invalid_output_twice_blocks_and_counts_usage(leased, conn):
    _, launched, lease = leased

    handle_normalize_mission(conn, lease, client=FakeClient("{}", "{}"))

    campaign = _campaign(conn, launched)
    assert campaign["status"] == "needs_human" and campaign["budget_json"]["usage"]["model_calls"] == 2
    assert _decisions(conn, launched)[0]["status"] == "blocked"


def test_handler_unavailable_model_schedules_retry_without_state_change(leased, conn):
    _, launched, lease = leased

    handle_normalize_mission(conn, lease, client=FakeClient(ModelUnavailable("down", [])))

    assert _campaign(conn, launched)["status"] == "running"
    assert _decisions(conn, launched)[0]["status"] == "rejected"
    assert _task_status(conn, lease) == "ready"


def test_handler_discards_plan_if_campaign_stopped_meanwhile(leased, conn):
    _, launched, lease = leased

    class StopDuringCall(FakeClient):
        def complete_json(self, **kwargs):
            conn.execute("update campaigns set status = 'stopped' where id = %s", (launched.id,))
            return super().complete_json(**kwargs)

    handle_normalize_mission(conn, lease, client=StopDuringCall(VALID_PLAN))

    campaign = _campaign(conn, launched)
    assert campaign["status"] == "stopped" and campaign["normalized_plan_json"] is None
    assert _decisions(conn, launched)[0]["status"] == "rejected"


def test_handler_refuses_when_model_budget_exhausted(leased, conn):
    _, launched, lease = leased
    conn.execute(
        "update campaigns set budget_json = jsonb_set(budget_json, '{usage,model_calls}', '19') where id = %s", (launched.id,)
    )
    client = FakeClient(VALID_PLAN)

    handle_normalize_mission(conn, lease, client=client)

    assert client.requests == []
    assert _campaign(conn, launched)["status"] == "needs_human"


def test_stale_lease_cannot_apply_plan(leased, conn):
    _, launched, lease = leased

    class ExpireDuringCall(FakeClient):
        def complete_json(self, **kwargs):
            conn.execute("update tasks set lease_until = now() - interval '1 second' where id = %s", (lease.task_id,))
            return super().complete_json(**kwargs)

    with pytest.raises(queue.LeaseLost):
        handle_normalize_mission(conn, lease, client=ExpireDuringCall(VALID_PLAN))

    assert _campaign(conn, launched)["normalized_plan_json"] is None
    assert _decisions(conn, launched) == []
