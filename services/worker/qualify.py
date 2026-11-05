"""qualify_and_draft task: deterministic qualification -> select one prospect -> draft (fast) -> verify (decision),
one revision max -> policy gate (doc 04 steps 1-6) -> conversation ready for dispatch. Never sends.

Model calls run outside DB locks; prospects' fit, every ledger entry, usage, the conversation and the next task
commit in ONE fenced transaction.
"""

from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from services.core.contracts.version import CONTRACT_VERSION
from services.core.policy_gate import initial_send_gate
from services.core.qualification import Qualification, qualify
from services.models.client import ModelCall, ModelClient
from services.models.draft import CALLS_PER_ROUND, MAX_ROUNDS, DraftOutcome, build_envelope, draft_and_verify
from services.models.prompts import DRAFT_VERSION, VERIFY_VERSION

from . import queue
from .handlers import _add_usage

LEASE_SECONDS = 180
UNAVAILABLE_RETRY_SECONDS = 30


def _meta(call: ModelCall | None, prompt_version: str) -> dict[str, Any] | None:
    if call is None:
        return None
    return {"deployment": call.deployment, "model_version": call.model_version, "prompt_version": prompt_version,
            "usage": {**call.usage, "latency_ms": call.latency_ms, "output_mode": call.output_mode, "degraded_from": call.degraded_from}}


def _uuids(values) -> list[str]:
    """Model output may cite non-UUID references (e.g. fact ids); only real UUIDs go into the ledger's uuid[] column."""
    out = []
    for value in values or []:
        try:
            out.append(str(UUID(str(value))))
        except ValueError:
            continue
    return out


def _decision(conn, lease, *, kind: str, status: str, reason: str, checks: list[dict] | None = None, policy: dict | None = None,
              prospect_id: UUID | None = None, evidence_ids: list[str] | None = None, input_refs: dict | None = None,
              model: dict | None = None, proposed: dict | None = None) -> UUID:
    policy = policy or {"pass": all(c["pass"] for c in (checks or [])), "checks": checks or []}
    raw_refs = [str(v) for v in (evidence_ids or []) if str(v) not in _uuids([v])]
    evidence_ids = _uuids(evidence_ids)
    if raw_refs:
        input_refs = {**(input_refs or {}), "non_uuid_refs_cited": raw_refs}
    return conn.execute(
        """
        insert into decisions (organization_id, campaign_id, prospect_id, task_id, kind, status, reason, evidence_ids,
                               input_refs_json, model_metadata_json, policy_result_json, proposed_action_json)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id
        """,
        (lease.organization_id, lease.campaign_id, prospect_id, lease.task_id, kind, status, reason, evidence_ids or [],
         Jsonb(input_refs or {}), Jsonb(model) if model else None, Jsonb(policy), Jsonb(proposed) if proposed else None),
    ).fetchone()["id"]


def _set_campaign(conn, lease, *, status: str, stage: str, terminal: bool = False) -> None:
    conn.execute(
        "update campaigns set status = %s, stage = %s, version = version + 1, "
        "completed_at = case when %s then now() else completed_at end where organization_id = %s and id = %s",
        (status, stage, terminal, lease.organization_id, lease.campaign_id),
    )


def _write_qualifications(conn, lease, prospects: list[dict], results: dict[UUID, Qualification]) -> None:
    for p in prospects:
        q = results[p["id"]]
        fit = {"criteria": [c.contract() for c in q.criteria], "fit": q.fit, "hypotheses": q.hypotheses, "computed_by": "code"}
        status = {"qualified": "qualified", "rejected": "rejected"}.get(q.fit, "needs_evidence")
        conn.execute("update prospects set fit_json = %s, status = %s where organization_id = %s and id = %s",
                     (Jsonb(fit), status, lease.organization_id, p["id"]))
        failing = [c for c in q.criteria if c.result != "pass"]
        _decision(
            conn, lease, kind="qualify", prospect_id=p["id"],
            status={"qualified": "accepted", "rejected": "rejected"}.get(q.fit, "blocked"),
            reason=(f"{q.fit}: all criteria pass" if not failing
                    else f"{q.fit}: " + "; ".join(f"{c.name} {c.result} ({c.reason})" for c in failing[:4])),
            checks=[{"name": c.name, "pass": c.result == "pass", "reason": f"{c.result}: {c.reason}"} for c in q.criteria],
            evidence_ids=sorted({e for c in q.criteria for e in c.evidence_ids}),
            input_refs={"company_ref": p["canonical_company_ref"], "person_ref": p["canonical_person_ref"]},
        )


def handle_qualify_and_draft(conn: psycopg.Connection, lease: queue.Lease, *, client: ModelClient) -> None:
    campaign = conn.execute(
        "select status, stage, normalized_plan_json, launch_snapshot_json, budget_json, limits_json, buyer_test_email "
        "from campaigns where organization_id = %s and id = %s",
        (lease.organization_id, lease.campaign_id),
    ).fetchone()
    if campaign["status"] != "running" or campaign["stage"] != "qualify":
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    plan, snapshot = campaign["normalized_plan_json"], campaign["launch_snapshot_json"]
    research = conn.execute(
        "select input_refs_json from decisions where organization_id = %s and campaign_id = %s and kind = 'research' "
        "and status = 'accepted' order by created_at desc limit 1",
        (lease.organization_id, lease.campaign_id),
    ).fetchone()
    mapping = (research or {}).get("input_refs_json", {}).get("mapping") if research else None
    prospects = conn.execute(
        "select id, canonical_company_ref, canonical_person_ref, identity_json from prospects "
        "where organization_id = %s and campaign_id = %s order by created_at, id",
        (lease.organization_id, lease.campaign_id),
    ).fetchall()
    evidence = conn.execute(
        "select id, prospect_id, provider_ref, field_path, excerpt, fact_status from evidence "
        "where organization_id = %s and campaign_id = %s",
        (lease.organization_id, lease.campaign_id),
    ).fetchall()
    by_prospect = {p["id"]: [e for e in evidence if e["prospect_id"] == p["id"]] for p in prospects}
    results = {p["id"]: qualify(p, by_prospect[p["id"]], plan, mapping) for p in prospects}
    selected = next((p for p in prospects if results[p["id"]].eligible), None)

    if selected is None:
        with queue.fenced(conn, lease):
            _write_qualifications(conn, lease, prospects, results)
            _decision(conn, lease, kind="select_prospect", status="blocked",
                      reason=f"None of {len(prospects)} prospects is eligible (identity, must-haves, exclusions, conflicts); no draft written.",
                      input_refs={"fits": {str(p["id"]): results[p["id"]].fit for p in prospects}})
            _set_campaign(conn, lease, status="no_match", stage="qualify", terminal=True)
            queue.complete(conn, lease)
        return

    used = campaign["budget_json"].get("usage", {}).get("model_calls", 0)
    if used + MAX_ROUNDS * CALLS_PER_ROUND > campaign["limits_json"]["max_model_calls"]:
        with queue.fenced(conn, lease):
            _write_qualifications(conn, lease, prospects, results)
            _decision(conn, lease, kind="draft", status="blocked", prospect_id=selected["id"],
                      reason="Model-call budget cannot cover draft + verify + one revision; no call made.",
                      checks=[{"name": "model_budget", "pass": False, "reason": f"{used} calls used"}])
            _set_campaign(conn, lease, status="needs_human", stage="qualify")
            queue.complete(conn, lease)
        return

    queue.heartbeat(conn, lease, LEASE_SECONDS)
    envelope = build_envelope(campaign_id=str(lease.campaign_id), snapshot=snapshot, prospect=selected,
                              evidence=by_prospect[selected["id"]], hypotheses=results[selected["id"]].hypotheses)
    outcome: DraftOutcome = draft_and_verify(client, envelope)
    seller = conn.execute(
        "select id, account_email from connections where organization_id = %s and provider = 'google' and purpose = 'seller' "
        "and status = 'connected'",
        (lease.organization_id,),
    ).fetchone()

    with queue.fenced(conn, lease):
        current = conn.execute("select status, stage from campaigns where organization_id = %s and id = %s for update",
                               (lease.organization_id, lease.campaign_id)).fetchone()
        _add_usage(conn, lease.organization_id, lease.campaign_id, outcome.calls)
        if current["status"] != "running" or current["stage"] != "qualify":
            _decision(conn, lease, kind="draft", status="rejected", reason=f"Campaign became {current['status']}; draft discarded.",
                      checks=[{"name": "campaign_running", "pass": False, "reason": current["status"]}])
            queue.complete(conn, lease)
            return

        _write_qualifications(conn, lease, prospects, results)
        others = [p for p in prospects if p["id"] != selected["id"]]
        _decision(conn, lease, kind="select_prospect", status="accepted", prospect_id=selected["id"],
                  reason=f"Selected the first eligible prospect ({selected['canonical_company_ref']}); P0 allows one conversation.",
                  evidence_ids=sorted({e for c in results[selected["id"]].criteria for e in c.evidence_ids}),
                  input_refs={"selected": str(selected["id"]),
                              "not_selected": {str(p["id"]): results[p["id"]].fit for p in others}})

        last_draft_id = None
        for i, rnd in enumerate(outcome.rounds, start=1):
            last_draft_id = _decision(
                conn, lease, kind="draft", prospect_id=selected["id"],
                status="accepted" if rnd.draft and not rnd.findings else "rejected",
                reason=(f"Draft attempt {i}: " + ("no deterministic findings" if rnd.draft and not rnd.findings
                        else "; ".join((rnd.draft_errors or rnd.findings)[:3]))),
                checks=[{"name": "deterministic", "pass": not rnd.findings and rnd.draft is not None,
                         "reason": "; ".join(rnd.findings + rnd.draft_errors) or "none"}],
                evidence_ids=list(rnd.draft.evidence_ids) if rnd.draft else [],
                input_refs={"attempt": i, "repairs": rnd.repairs, "prompt_version": DRAFT_VERSION},
                model=_meta(rnd.draft_call, DRAFT_VERSION),
                proposed=rnd.draft.model_dump(mode="json") if rnd.draft else None,
            )
            if rnd.verify_call or rnd.verify_errors:
                v = rnd.verification
                _decision(
                    conn, lease, kind="verify", prospect_id=selected["id"],
                    status="accepted" if v and v.verdict == "pass" else "rejected",
                    reason=f"Verify attempt {i}: " + (f"{v.verdict}: {v.reason}" if v else "; ".join(rnd.verify_errors)[:300]),
                    checks=[{"name": "semantic_verifier", "pass": bool(v and v.verdict == "pass"), "reason": v.verdict if v else "invalid output"}],
                    evidence_ids=list(v.evidence_ids) if v else [],
                    input_refs={"attempt": i, "draft_decision_id": str(last_draft_id), "prompt_version": VERIFY_VERSION},
                    model=_meta(rnd.verify_call, VERIFY_VERSION),
                    proposed=v.model_dump(mode="json") if v else None,
                )

        if outcome.unavailable:
            final = lease.attempt >= lease.max_attempts
            _decision(conn, lease, kind="draft", status="blocked" if final else "rejected", prospect_id=selected["id"],
                      reason="Model deployment unavailable" + ("; needs operator attention." if final else "; retry scheduled."),
                      checks=[{"name": "model_available", "pass": False, "reason": "ModelUnavailable"}])
            if final:
                _set_campaign(conn, lease, status="needs_human", stage="qualify")
            queue.fail(conn, lease, {"error_class": "ModelUnavailable"}, retry_after_seconds=None if final else UNAVAILABLE_RETRY_SECONDS)
            return

        final_round = outcome.final
        gate = initial_send_gate(
            conn, organization_id=lease.organization_id, campaign_id=lease.campaign_id, prospect=selected,
            qualified=results[selected["id"]].eligible, draft=final_round.draft if final_round else None,
            verification=final_round.verification if final_round else None,
            deterministic_findings=(final_round.findings + final_round.draft_errors) if final_round else ["no draft"],
            snapshot=snapshot, recipient=campaign["buyer_test_email"], sender=seller["account_email"] if seller else None,
        )
        failure = gate.first_failure
        gate_id = _decision(
            conn, lease, kind="policy_gate", prospect_id=selected["id"], status="accepted" if gate.passed else "blocked",
            reason=("Steps 1-6 pass; steps 7-8 run at dispatch." if gate.passed
                    else f"Blocked at step {failure['step']} {failure['name']}: {failure['reason']}"),
            policy=gate.as_policy(), input_refs={"draft_decision_id": str(last_draft_id)},
        )
        if not (outcome.ready and gate.passed and seller):
            _set_campaign(conn, lease, status="needs_human", stage="qualify")
            queue.complete(conn, lease)
            return

        conversation_id = uuid4()
        conn.execute(
            """
            insert into conversations (id, organization_id, campaign_id, prospect_id, connection_id, buyer_test_email, state,
                                       version, crm_json)
            values (%s, %s, %s, %s, %s, %s, 'drafting', 1, %s)
            """,
            (conversation_id, lease.organization_id, lease.campaign_id, selected["id"], seller["id"], campaign["buyer_test_email"],
             Jsonb({"stage": "draft_ready", "draft_decision_id": str(last_draft_id), "gate_decision_id": str(gate_id),
                    "last_decision_id": str(gate_id)})),
        )
        _set_campaign(conn, lease, status="running", stage="send")
        conn.execute(
            "insert into tasks (organization_id, campaign_id, conversation_id, kind, dedupe_key, payload_json, status) "
            "values (%s, %s, %s, 'send_email', %s, %s, 'ready') on conflict (organization_id, dedupe_key) do nothing",
            (lease.organization_id, lease.campaign_id, conversation_id, f"email:{conversation_id}:initial:initial",
             Jsonb({"schema_version": CONTRACT_VERSION, "campaign_id": str(lease.campaign_id), "conversation_id": str(conversation_id),
                    "expected_conversation_version": 1, "trigger_message_id": None, "decision_id": str(last_draft_id),
                    "input_ref_ids": [str(gate_id)]})),
        )
        queue.complete(conn, lease)
