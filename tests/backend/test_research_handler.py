import json

import pytest
from psycopg.types.json import Jsonb

from conftest import launch
from services.adapters.crustdata.adapter import (
    CompanyCandidate,
    CompanySearchResult,
    EnrichResult,
    Observation,
    PeopleResult,
    PersonMatch,
    company_ref,
    person_ref,
)
from services.adapters.crustdata.client import CrustdataOutOfCredits, CrustdataUnavailable, ProviderReceipt
from services.core import db
from services.core.campaigns import get_mission_detail
from services.worker import queue
from services.worker.research import handle_research

PLAN = {
    "objective": "book_demo", "geography": ["Bengaluru"], "industries": ["fintech"],
    "company_rules": [], "buyer_roles": ["VP of Sales"], "exclusions": ["banks"], "missing_required_fields": [],
    "assumptions": [], "research_queries": [{"intent": "find fintech companies", "limit": 10}], "stop_conditions": [],
}


def receipt(endpoint, billable=True):
    return ProviderReceipt(endpoint, "2025-11-01", 200, f"req-{endpoint}", 0.23 if billable else 0.0, 1, "a" * 64, "b" * 64, billable, 1, 5)


class FakeResearch:
    """FIXTURE provider. `matches` maps company id -> 'supported' | 'conflicted' | 'unknown'."""

    def __init__(self, n_companies=4, matches=None, fail_on=None):
        self.receipts = []
        self.n = n_companies
        self.matches = matches or {}
        self.fail_on = fail_on
        self.people_calls = []
        self.enrich_calls = []

    def _call(self, endpoint, billable=True):
        if self.fail_on and self.fail_on[0] == endpoint:
            raise self.fail_on[1]
        r = receipt(endpoint, billable)
        self.receipts.append(r)
        return r

    def autocomplete(self, field, query, limit=10):
        self._call("/company/search/autocomplete", billable=False)
        return {"city": ["Bengaluru"], "taxonomy.professional_network_specialities": ["Fintech"]}.get(field, [])

    def search_companies(self, query, limit):
        r = self._call("/company/search")
        companies = [
            CompanyCandidate(company_ref(100 + i), f"Company {i}", f"c{i}.example",
                             [Observation("crustdata:/company/search#basic_info.name", f"Company {i}", "c" * 64, r)])
            for i in range(self.n)
        ][:limit]
        return CompanySearchResult(companies, 42, True, r)

    def find_people(self, ref, roles, limit=3):
        self.people_calls.append(ref)
        r = self._call("/person/search")
        status = self.matches.get(ref, "unknown")
        if status == "supported":
            pid = person_ref(int(ref.rsplit(":", 1)[1]) + 1000)
            obs = [
                Observation(f"crustdata:/person/search#experience.employment_details.current[crustdata_company_id={ref}].title", "VP Sales", "d" * 64, r),
                Observation("crustdata:/person/search#basic_profile.name", "Asha Rao", "d" * 64, r),
                Observation("crustdata:/person/search#basic_profile.email", "leak@example.com", "d" * 64, r),
            ]
            return PeopleResult(ref, "supported", PersonMatch(pid, "Asha Rao", "VP Sales", obs), "matched", [], r)
        return PeopleResult(ref, status, None, f"{status} relationship", [{"code": "condition_eliminates_all"}], r)

    def enrich_identity(self, ref):
        self.enrich_calls.append(ref)
        r = self._call("/company/enrich")
        return EnrichResult(ref, [Observation("crustdata:/company/enrich#funding.last_round_type", "series_b", "e" * 64, r)],
                            ["funding.total_investment_usd"], r)


@pytest.fixture
def research_campaign(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    conn.execute(
        "update campaigns set stage = 'research', normalized_plan_json = %s where id = %s", (Jsonb(PLAN), launched.id)
    )
    conn.execute(
        "insert into tasks (organization_id, campaign_id, kind, dedupe_key, payload_json, status) "
        "values (%s, %s, 'research', %s, '{}'::jsonb, 'ready')",
        (tenant.organization_id, launched.id, f"campaign:{launched.id}:research"),
    )
    with db.connect(database_url) as c:
        lease = queue.claim(c, owner="research-test", kinds=["research"], lease_seconds=60, organization_id=tenant.organization_id)
    return tenant, launched, lease


def _campaign(conn, cid):
    return conn.execute("select status, stage, version, budget_json from campaigns where id = %s", (cid,)).fetchone()


def _decision(conn, cid):
    return conn.execute(
        "select status, reason, evidence_ids, input_refs_json, policy_result_json from decisions "
        "where campaign_id = %s and kind = 'research'", (cid,)
    ).fetchall()


def test_happy_path_persists_prospects_evidence_decision_and_queues_qualify(research_campaign, conn):
    tenant, launched, lease = research_campaign
    fake = FakeResearch(matches={company_ref(100): "unknown", company_ref(101): "supported", company_ref(102): "conflicted"})

    handle_research(conn, lease, research_factory=lambda: fake)

    campaign = _campaign(conn, launched.id)
    assert (campaign["status"], campaign["stage"]) == ("running", "qualify")
    assert campaign["budget_json"]["usage"]["research_calls"] == 1 + 4 + 1  # search + 4 people + 1 enrich
    prospects = conn.execute(
        "select canonical_company_ref, canonical_person_ref, status, identity_json from prospects where campaign_id = %s order by canonical_company_ref",
        (launched.id,),
    ).fetchall()
    assert [(p["canonical_company_ref"], p["canonical_person_ref"], p["status"]) for p in prospects] == [
        ("crustdata:company:100", None, "needs_evidence"),
        ("crustdata:company:101", "crustdata:person:1101", "researching"),
        ("crustdata:company:102", None, "needs_evidence"),
        ("crustdata:company:103", None, "needs_evidence"),
    ]
    supported = prospects[1]["identity_json"]
    assert supported["relationship"]["status"] == "supported" and supported["relationship"]["evidence_ids"]
    assert prospects[2]["identity_json"]["relationship"]["status"] == "conflicted"

    evidence = conn.execute(
        "select source_kind, provider_ref, field_path, excerpt, content_sha256, fact_status, metadata_json from evidence "
        "where campaign_id = %s", (launched.id,)
    ).fetchall()
    assert evidence and all(e["source_kind"] == "crustdata" and e["fact_status"] == "observed" for e in evidence)
    assert all(len(e["content_sha256"]) == 64 and e["provider_ref"].startswith("crustdata:") for e in evidence)
    assert all(e["metadata_json"]["api_version"] == "2025-11-01" and e["metadata_json"]["request_id"] for e in evidence)
    assert not any("@" in e["excerpt"] for e in evidence), "email-like values must never be persisted"
    assert {"crustdata:/company/enrich#funding.last_round_type"} <= {e["field_path"] for e in evidence}

    [decision] = _decision(conn, launched.id)
    assert decision["status"] == "accepted" and decision["evidence_ids"]
    refs = decision["input_refs_json"]
    assert refs["billable_calls"] == 6 and refs["credits_used"] == pytest.approx(6 * 0.23)
    assert refs["mapping"]["weak_matches"][0]["plan"] == "industry:fintech"
    assert conn.execute(
        "select status from tasks where organization_id = %s and kind = 'qualify_and_draft'", (tenant.organization_id,)
    ).fetchone()["status"] == "ready"
    assert conn.execute("select status from tasks where id = %s", (lease.task_id,)).fetchone()["status"] == "succeeded"

    with db.connect() as c:
        detail = get_mission_detail(c, organization_id=tenant.organization_id, campaign_id=launched.id)
    case = next(p for p in detail.prospects if p.canonical_person_ref)
    assert case.relationship.status == "supported" and case.person.title == "VP Sales"
    assert case.delivery.buyer_test_email == tenant.buyer_test_email and case.delivery.identity_is_simulated is True
    assert case.fit == "needs_evidence" and case.facts
    assert len(detail.evidence) == len(evidence)


def test_no_supported_person_gives_no_match_without_invented_identity(research_campaign, conn):
    _, launched, lease = research_campaign

    handle_research(conn, lease, research_factory=lambda: FakeResearch(n_companies=3))

    campaign = _campaign(conn, launched.id)
    assert campaign["status"] == "no_match"
    assert conn.execute(
        "select count(*) as n from prospects where campaign_id = %s and canonical_person_ref is not null", (launched.id,)
    ).fetchone()["n"] == 0
    assert _decision(conn, launched.id)[0]["status"] == "blocked"


def test_caps_stop_after_three_matches_and_ten_discovered(research_campaign, conn):
    _, launched, lease = research_campaign
    conn.execute("update campaigns set limits_json = limits_json || %s where id = %s",
                 (Jsonb({"max_discovered": 10, "max_enriched": 3}), launched.id))
    fake = FakeResearch(n_companies=15, matches={company_ref(100 + i): "supported" for i in range(15)})

    handle_research(conn, lease, research_factory=lambda: fake)

    assert len(fake.enrich_calls) == 3 and len(fake.people_calls) == 3
    discovered = _decision(conn, launched.id)[0]["input_refs_json"]["discovered"]
    assert len(discovered) == 10


def test_research_budget_enforced_before_calls(research_campaign, conn):
    _, launched, lease = research_campaign
    conn.execute("update campaigns set limits_json = limits_json || %s where id = %s", (Jsonb({"max_research_calls": 10}), launched.id))
    conn.execute("update campaigns set budget_json = jsonb_set(budget_json, '{usage,research_calls}', '5') where id = %s", (launched.id,))
    fake = FakeResearch(n_companies=10, matches={})

    handle_research(conn, lease, research_factory=lambda: fake)

    billable = sum(1 for r in fake.receipts if r.billable)
    assert billable <= 5  # max_research_calls 10 minus 5 already used
    assert _campaign(conn, launched.id)["budget_json"]["usage"]["research_calls"] <= 10


def test_out_of_credits_needs_human_and_no_retry(research_campaign, conn):
    _, launched, lease = research_campaign
    fake = FakeResearch(fail_on=("/company/search", CrustdataOutOfCredits("insufficient_credits: none left", endpoint="/company/search", status=402)))

    handle_research(conn, lease, research_factory=lambda: fake)

    assert _campaign(conn, launched.id)["status"] == "needs_human"
    assert _decision(conn, launched.id)[0]["status"] == "blocked"
    assert conn.execute("select status from tasks where id = %s", (lease.task_id,)).fetchone()["status"] == "succeeded"
    assert conn.execute("select count(*) as n from prospects where campaign_id = %s", (launched.id,)).fetchone()["n"] == 0


def test_unavailable_schedules_retry(research_campaign, conn):
    _, launched, lease = research_campaign
    fake = FakeResearch(fail_on=("/person/search", CrustdataUnavailable("gave up", endpoint="/person/search", status=503)))

    handle_research(conn, lease, research_factory=lambda: fake)

    assert _campaign(conn, launched.id)["status"] == "running"
    assert conn.execute("select status from tasks where id = %s", (lease.task_id,)).fetchone()["status"] == "ready"
    assert _decision(conn, launched.id)[0]["status"] == "rejected"


def test_unmappable_plan_needs_human(research_campaign, conn):
    _, launched, lease = research_campaign
    conn.execute(
        "update campaigns set normalized_plan_json = %s where id = %s", (Jsonb({**PLAN, "geography": ["Atlantis"]}), launched.id)
    )

    handle_research(conn, lease, research_factory=lambda: FakeResearch())

    assert _campaign(conn, launched.id)["status"] == "needs_human"
    assert "mapped" in _decision(conn, launched.id)[0]["reason"]


def test_stale_lease_writes_nothing(research_campaign, conn):
    _, launched, lease = research_campaign

    class ExpiringResearch(FakeResearch):
        def enrich_identity(self, ref):
            conn.execute("update tasks set lease_until = now() - interval '1 second' where id = %s", (lease.task_id,))
            return super().enrich_identity(ref)

    with pytest.raises(queue.LeaseLost):
        handle_research(conn, lease, research_factory=lambda: ExpiringResearch(matches={company_ref(100): "supported"}))

    assert conn.execute("select count(*) as n from prospects where campaign_id = %s", (launched.id,)).fetchone()["n"] == 0
    assert conn.execute("select count(*) as n from evidence where campaign_id = %s", (launched.id,)).fetchone()["n"] == 0
    assert _decision(conn, launched.id) == []


def test_campaign_stopped_during_research_discards_results(research_campaign, conn):
    _, launched, lease = research_campaign

    class StopDuring(FakeResearch):
        def search_companies(self, query, limit):
            conn.execute("update campaigns set status = 'stopped' where id = %s", (launched.id,))
            return super().search_companies(query, limit)

    handle_research(conn, lease, research_factory=lambda: StopDuring(matches={company_ref(100): "supported"}))

    assert _campaign(conn, launched.id)["status"] == "stopped"
    assert conn.execute("select count(*) as n from prospects where campaign_id = %s", (launched.id,)).fetchone()["n"] == 0
    assert _decision(conn, launched.id)[0]["status"] == "rejected"
