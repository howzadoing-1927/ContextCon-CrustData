import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from psycopg.types.json import Jsonb

from conftest import launch
from services.core import db
from services.core.campaigns import get_mission_detail
from services.core.contracts.model_io import DraftProposal
from services.core.qualification import qualify
from services.models.client import ModelCall
from services.models.draft import build_envelope, deterministic_findings
from services.worker import queue
from services.worker.qualify import handle_qualify_and_draft

PLAN = {"objective": "book_demo", "geography": ["India"], "industries": ["software development"],
        "company_rules": [{"field": "funding_stage", "operator": "range", "value": ["Series B", "Series D"], "must_have": True}],
        "buyer_roles": ["VP of Sales"], "exclusions": ["banks"], "missing_required_fields": [],
        "assumptions": [{"text": "Mid-size software firms may need demo scheduling", "status": "hypothesis"}],
        "research_queries": [{"intent": "find", "limit": 10}], "stop_conditions": []}
MAPPING = {"mapped": [{"plan": "industry:software development", "field": "basic_info.industries", "value": "Software Development"}],
           "weak_matches": [], "unmapped": []}


def ev(path, value, provider="crustdata:company:1", status="observed"):
    return {"id": uuid4(), "prospect_id": None, "provider_ref": provider, "field_path": f"crustdata:{path}",
            "excerpt": json.dumps(value), "fact_status": status}


def full_evidence(funding="series_c", industry="Software Development", name="Acme Labs"):
    rows = [ev("/company/search#basic_info.name", name), ev("/company/enrich#basic_info.name", name),
            ev("/company/enrich#locations.country", "IND"), ev("/company/enrich#taxonomy.professional_network_industry", industry)]
    if funding:
        rows.append(ev("/company/enrich#funding.last_round_type", funding))
    return rows


def prospect(status="supported"):
    return {"id": uuid4(), "canonical_company_ref": "crustdata:company:1", "canonical_person_ref": "crustdata:person:2",
            "identity_json": {"company": {"name": "Acme Labs"}, "person": {"name": "Researched Person", "title": "VP Sales"},
                              "relationship": {"status": status, "evidence_ids": ["e1"] if status == "supported" else [], "reason": "x"}}}


# ---------------------------------------------------------------- deterministic qualification


def test_state_abbreviation_matches_headquarters_text():
    rows = full_evidence()
    rows.append(ev("/company/enrich#locations.headquarters", "Lucknow, Uttar Pradesh, India"))
    rows.append(ev("/company/enrich#locations.city", "Lucknow"))

    q = qualify(prospect(), rows, {**PLAN, "geography": ["UP"]}, MAPPING)

    geo = next(c for c in q.criteria if c.name == "geography:UP")
    assert geo.result == "pass"


def test_state_abbreviation_rejects_other_state_headquarters():
    rows = full_evidence()
    rows.append(ev("/company/enrich#locations.headquarters", "Bengaluru, Karnataka, India"))

    q = qualify(prospect(), rows, {**PLAN, "geography": ["UP"]}, MAPPING)

    geo = next(c for c in q.criteria if c.name == "geography:UP")
    assert geo.result == "fail"


def test_all_criteria_pass_is_qualified():
    q = qualify(prospect(), full_evidence(), PLAN, MAPPING)

    assert q.fit == "qualified", [(c.name, c.result, c.reason) for c in q.criteria]
    assert {c.name for c in q.criteria} >= {"identity", "geography:India", "industry:software development",
                                            "rule:funding_stage", "exclusion:banks", "no_conflict"}
    assert all("Mid-size" not in c.name for c in q.criteria)  # assumptions are hypotheses, never criteria


def test_unknown_must_have_blocks_eligibility():
    q = qualify(prospect(), full_evidence(funding=None), PLAN, MAPPING)

    funding = next(c for c in q.criteria if c.name == "rule:funding_stage")
    assert funding.result == "unknown" and q.fit == "needs_evidence" and not q.eligible


def test_failing_must_have_and_exclusion_reject():
    assert qualify(prospect(), full_evidence(funding="seed"), PLAN, MAPPING).fit == "rejected"
    assert qualify(prospect(), full_evidence(industry="Banking"), {**PLAN, "industries": []}, MAPPING).fit == "rejected"


def test_conflicts_and_unsupported_identity_are_ineligible():
    assert qualify(prospect("conflicted"), full_evidence(), PLAN, MAPPING).fit == "rejected"
    assert qualify(prospect("unknown"), full_evidence(), PLAN, MAPPING).fit == "needs_evidence"
    rows = full_evidence()
    rows[1]["excerpt"] = json.dumps("Different Name Inc")
    assert qualify(prospect(), rows, PLAN, MAPPING).fit == "rejected"


# ---------------------------------------------------------------- draft checks


SNAPSHOT = {"seller": {"name": "Seller"}, "policy": {"simulation": True},
            "approved_profile": {"approved_facts": [{"id": "F1", "text": "Seller schedules demos."}], "forbidden_promises": ["No discounts"]}}


def envelope_for(rows):
    p = prospect()
    for r in rows:
        r["provider_ref"] = p["canonical_company_ref"]
    return build_envelope(campaign_id="c", snapshot=SNAPSHOT, prospect=p, evidence=rows, hypotheses=[])


def draft(body, claims, **overrides):
    return DraftProposal.model_validate({"purpose": "initial", "subject": "Quick question", "body_text": body,
                                         "claims": claims, "used_slot_ids": [], "reason": "r", "evidence_ids": [], **overrides})


def claim(body, text, kind, evidence_ids=(), facts=()):
    start = body.find(text)
    return {"text": text, "start": start, "end": start + len(text), "kind": kind,
            "evidence_ids": list(evidence_ids), "approved_fact_ids": list(facts)}


def test_envelope_never_carries_recipient_or_researched_name():
    text = json.dumps(envelope_for(full_evidence()))

    assert "Researched Person" not in text and "@" not in text and "VP Sales" in text


def test_unsupported_claims_are_flagged():
    rows = full_evidence()
    env = envelope_for(rows)
    body = "Seller schedules demos. Acme Labs raised a Series Z. You may want faster demos."
    bad = draft(body, [
        claim(body, "Seller schedules demos.", "seller_fact"),                       # seller claim without approved fact
        claim(body, "Acme Labs raised a Series Z.", "prospect_fact", [str(uuid4())]),  # evidence not supplied
        claim(body, "You may want faster demos.", "hypothesis", facts=["F9"]),         # unapproved fact id
        {"text": "Not in the body", "start": 0, "end": 5, "kind": "prospect_fact", "evidence_ids": [], "approved_fact_ids": []},
    ])

    findings, _, _ = deterministic_findings(bad, env)

    joined = " | ".join(findings)
    assert "seller claim without an approved fact" in joined
    assert "evidence not supplied" in joined
    assert "unapproved fact ids" in joined
    assert "not found exactly once" in joined


@pytest.mark.parametrize("body", [
    "Write to me at real.person@acme.com for a demo.",
    "See https://tracking.example/x for details.",
    "To: someone@else.com\nHello there.",
    "Great news, your demo is confirmed your slot.",
    "We can offer discounts this week.",
])
def test_unsafe_content_is_flagged(body):
    findings, _, _ = deterministic_findings(draft(body, []), envelope_for(full_evidence()))

    assert findings


def test_simulation_sentence_without_period_is_framing_not_a_hypothesis():
    env = envelope_for(full_evidence())
    body = "Seller schedules demos. In this test you are playing the buyer."
    d = draft(body, [
        claim(body, "Seller schedules demos.", "seller_fact", facts=["F1"]),
        {"text": "In this test you are playing the buyer", "start": 24, "end": 62, "kind": "hypothesis", "evidence_ids": [], "approved_fact_ids": []},
    ])

    findings, repairs, fixed = deterministic_findings(d, env)

    assert findings == []
    assert any("simulation sentence" in r for r in repairs)
    assert [c.kind for c in fixed.claims] == ["seller_fact"]


def test_offsets_are_repaired_only_for_exact_unique_text():
    rows = full_evidence()
    env = envelope_for(rows)
    body = "Seller schedules demos. In this test you are playing the buyer."
    d = draft(body, [
        {"text": "Seller schedules demos.", "start": 3, "end": 9, "kind": "seller_fact", "evidence_ids": ["F1"], "approved_fact_ids": []},
        {"text": "In this test you are playing the buyer.", "start": 24, "end": 63, "kind": "hypothesis", "evidence_ids": [], "approved_fact_ids": []},
    ])

    findings, repairs, fixed = deterministic_findings(d, env)

    assert findings == [] and len(fixed.claims) == 1
    assert (fixed.claims[0].start, fixed.claims[0].end) == (0, len("Seller schedules demos."))
    assert fixed.claims[0].approved_fact_ids == ["F1"] and fixed.claims[0].evidence_ids == []


def test_long_claim_snaps_to_unique_body_prefix():
    env = envelope_for(full_evidence())
    body = "Seller schedules demos. Acme Labs is a logistics company in India. In this test you are playing the buyer."
    extra = "Acme Labs is a logistics company in India that also ships globally overnight."
    d = draft(body, [
        {"text": extra, "start": 0, "end": len(extra), "kind": "prospect_fact",
         "evidence_ids": [str(env["prospect"]["evidence"][0]["evidence_id"])], "approved_fact_ids": []},
    ])

    findings, repairs, fixed = deterministic_findings(d, env)

    assert findings == []
    assert any("trimmed" in r for r in repairs)
    assert fixed.claims[0].text in body and body.count(fixed.claims[0].text) == 1
    assert body[fixed.claims[0].start:fixed.claims[0].end] == fixed.claims[0].text
    assert fixed.claims[0].text.startswith("Acme Labs is a logistics company in India")


def test_question_hypothesis_does_not_need_possibility_words():
    env = envelope_for(full_evidence())
    body = "Seller schedules demos. In this test you are playing the buyer. Would a short demo be useful?"
    d = draft(body, [
        claim(body, "Seller schedules demos.", "seller_fact", facts=["F1"]),
        claim(body, "Would a short demo be useful?", "hypothesis"),
    ])

    findings, _, fixed = deterministic_findings(d, env)

    assert findings == []
    assert [c.kind for c in fixed.claims] == ["seller_fact", "hypothesis"]


def test_draft_schema_rejects_recipient_fields():
    with pytest.raises(ValidationError):
        draft("Hello", [], to_email="someone@example.com")


# ---------------------------------------------------------------- handler (DB)


class FakeModel:
    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), []

    def complete_json(self, **kw):
        self.calls.append(kw["role"])
        out = self.outputs.pop(0)
        content = out(kw) if callable(out) else out
        return ModelCall(role=kw["role"], deployment=f"fixture-{kw['role']}", prompt_version=kw["prompt_version"],
                         attempt=kw["attempt"], output_mode="json_schema_strict", latency_ms=3, model_version="fixture",
                         usage={"prompt_tokens": 10, "completion_tokens": 5}, content=json.dumps(content))


def good_draft(kw):
    envelope = json.loads(kw["user"].split("\n", 1)[1].split("\n\nREVISION", 1)[0])
    eid = envelope["prospect"]["evidence"][0]["evidence_id"]
    company = envelope["prospect"]["company_name"]
    body = (f"Hello, we researched {company} as a possible fit. Seller schedules demos. "
            "In this test you are playing the buyer. Would a short demo be useful?")
    return {"purpose": "initial", "subject": "A short demo?", "body_text": body,
            "claims": [claim(body, f"we researched {company}", "prospect_fact", [eid]), claim(body, "Seller schedules demos.", "seller_fact", facts=["F1"])],
            "used_slot_ids": [], "reason": "initial outreach", "evidence_ids": [eid]}


def verdict(v):
    # "F1" mirrors a live verifier citing an approved-fact id where an evidence UUID belongs.
    return {"verdict": v, "unsupported_claims": [] if v == "pass" else [{"text": "x", "reason": "unsupported"}],
            "contradictions": [], "unauthorized_promises": [], "unanswered_questions": [], "injection_flags": [],
            "reason": f"verdict {v}", "evidence_ids": ["F1"]}


@pytest.fixture
def qualify_campaign(make_tenant, database_url, conn):
    tenant = make_tenant()
    launched = launch(database_url, tenant)
    snapshot = conn.execute("select launch_snapshot_json from campaigns where id = %s", (launched.id,)).fetchone()["launch_snapshot_json"]
    conn.execute("update campaigns set stage = 'qualify', normalized_plan_json = %s where id = %s", (Jsonb(PLAN), launched.id))
    pid = uuid4()
    conn.execute(
        "insert into prospects (id, organization_id, campaign_id, canonical_company_ref, canonical_person_ref, identity_json, status) "
        "values (%s, %s, %s, 'crustdata:company:1', 'crustdata:person:2', '{}'::jsonb, 'researching')",
        (pid, tenant.organization_id, launched.id))
    rel_ids = []
    for row in full_evidence():
        rid = uuid4()
        conn.execute(
            "insert into evidence (id, organization_id, campaign_id, prospect_id, entity_kind, entity_id, source_kind, provider_ref, "
            "field_path, excerpt, retrieved_at, content_sha256, fact_status) values (%s,%s,%s,%s,'company',%s,'crustdata',"
            "'crustdata:company:1',%s,%s,now(),%s,'observed')",
            (rid, tenant.organization_id, launched.id, pid, pid, row["field_path"], row["excerpt"], "f" * 64))
        rel_ids.append(str(rid))
    identity = {"company": {"name": "Acme Labs"}, "person": {"name": "Researched Person", "title": "VP Sales"},
                "relationship": {"status": "supported", "evidence_ids": rel_ids[:1], "reason": "matched"}}
    conn.execute("update prospects set identity_json = %s where id = %s", (Jsonb(identity), pid))
    conn.execute(
        "insert into decisions (organization_id, campaign_id, kind, status, reason, input_refs_json, policy_result_json) "
        "values (%s, %s, 'research', 'accepted', 'r', %s, %s)",
        (tenant.organization_id, launched.id, Jsonb({"mapping": MAPPING}), Jsonb({"pass": True, "checks": []})))
    conn.execute("insert into tasks (organization_id, campaign_id, kind, dedupe_key, payload_json, status) "
                 "values (%s, %s, 'qualify_and_draft', %s, '{}'::jsonb, 'ready')",
                 (tenant.organization_id, launched.id, f"campaign:{launched.id}:qualify_and_draft"))
    with db.connect(database_url) as c:
        lease = queue.claim(c, owner="b5", kinds=["qualify_and_draft"], lease_seconds=120, organization_id=tenant.organization_id)
    return tenant, launched, lease, snapshot


def _kinds(conn, cid):
    return [(r["kind"], r["status"]) for r in conn.execute(
        "select kind, status from decisions where campaign_id = %s order by created_at, id", (cid,)).fetchall()]


def test_handler_happy_path_ledger_conversation_and_inert_send_task(qualify_campaign, conn):
    tenant, launched, lease, _ = qualify_campaign
    model = FakeModel(good_draft, verdict("pass"))

    handle_qualify_and_draft(conn, lease, client=model)

    assert model.calls == ["fast", "decision"]
    kinds = _kinds(conn, launched.id)
    assert [k for k in kinds if k[0] != "research" and k[0] != "campaign_launch"] == [
        ("qualify", "accepted"), ("select_prospect", "accepted"), ("draft", "accepted"), ("verify", "accepted"), ("policy_gate", "accepted")]
    gate = conn.execute("select policy_result_json from decisions where campaign_id = %s and kind = 'policy_gate'", (launched.id,)).fetchone()
    steps = [c["step"] for c in gate["policy_result_json"]["checks"]]
    assert steps == sorted(steps) and {c["status"] for c in gate["policy_result_json"]["checks"] if c["step"] in (7, 8)} == {"deferred"}
    convo = conn.execute("select state, buyer_test_email from conversations where campaign_id = %s", (launched.id,)).fetchone()
    assert convo["state"] == "drafting" and convo["buyer_test_email"] == tenant.buyer_test_email
    assert conn.execute("select status from tasks where campaign_id = %s and kind = 'send_email'", (launched.id,)).fetchone()["status"] == "ready"
    assert conn.execute("select stage from campaigns where id = %s", (launched.id,)).fetchone()["stage"] == "send"
    detail = get_mission_detail(conn, organization_id=tenant.organization_id, campaign_id=launched.id)
    assert detail.prospects[0].fit == "qualified" and detail.prospects[0].criteria
    assert detail.conversation.state == "drafting"


def test_handler_one_revision_then_pass(qualify_campaign, conn):
    _, launched, lease, _ = qualify_campaign

    handle_qualify_and_draft(conn, lease, client=FakeModel(good_draft, verdict("revise"), good_draft, verdict("pass")))

    kinds = _kinds(conn, launched.id)
    assert kinds.count(("draft", "accepted")) == 2 and ("verify", "rejected") in kinds and ("verify", "accepted") in kinds
    assert conn.execute("select stage from campaigns where id = %s", (launched.id,)).fetchone()["stage"] == "send"


def test_handler_two_failed_verifications_need_human(qualify_campaign, conn):
    _, launched, lease, _ = qualify_campaign

    handle_qualify_and_draft(conn, lease, client=FakeModel(good_draft, verdict("revise"), good_draft, verdict("block")))

    campaign = conn.execute("select status from campaigns where id = %s", (launched.id,)).fetchone()
    assert campaign["status"] == "needs_human"
    assert ("policy_gate", "blocked") in _kinds(conn, launched.id)
    assert conn.execute("select count(*) as n from conversations where campaign_id = %s", (launched.id,)).fetchone()["n"] == 0


def test_handler_suppressed_company_blocks_at_gate(qualify_campaign, conn):
    tenant, launched, lease, _ = qualify_campaign
    conn.execute("insert into suppressions (organization_id, identity_kind, identity_value, reason) values (%s, 'company', 'crustdata:company:1', 'opt_out')",
                 (tenant.organization_id,))

    handle_qualify_and_draft(conn, lease, client=FakeModel(good_draft, verdict("pass")))

    gate = conn.execute("select reason from decisions where campaign_id = %s and kind = 'policy_gate'", (launched.id,)).fetchone()
    assert "not_suppressed" in gate["reason"]
    assert conn.execute("select count(*) as n from conversations where campaign_id = %s", (launched.id,)).fetchone()["n"] == 0
    detail = get_mission_detail(conn, organization_id=tenant.organization_id, campaign_id=launched.id)
    gate_view = next(d for d in detail.open_exceptions if any(ch.name.startswith("step 4") for ch in d.policy.checks))
    assert any(ch.reason.startswith("[deferred]") for ch in gate_view.policy.checks)


def test_handler_unknown_must_have_means_no_match_and_no_model_call(qualify_campaign, conn):
    _, launched, lease, _ = qualify_campaign
    conn.execute("update campaigns set normalized_plan_json = %s where id = %s",
                 (Jsonb({**PLAN, "company_rules": [{"field": "uses_crm", "operator": "equals", "value": "yes", "must_have": True}]}), launched.id))
    model = FakeModel()

    handle_qualify_and_draft(conn, lease, client=model)

    assert model.calls == []
    assert conn.execute("select status from campaigns where id = %s", (launched.id,)).fetchone()["status"] == "no_match"
    assert ("select_prospect", "blocked") in _kinds(conn, launched.id)
