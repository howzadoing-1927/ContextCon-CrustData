"""Task handlers. Each does its network/model work outside DB locks, then commits state, ledger, usage, the
next task and task completion in ONE fenced transaction so a stale worker can never apply a result."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from services.core.contracts.version import CONTRACT_VERSION
from services.models.client import ModelCall, ModelClient
from services.models.normalize import MAX_ATTEMPTS, NormalizeOutcome, build_envelope, normalize_mission
from services.models.prompts import NORMALIZE_MISSION_VERSION

from . import queue

RUNNABLE = ("running",)
UNAVAILABLE_RETRY_SECONDS = 30


def _usage_delta(calls: list[ModelCall]) -> dict[str, int]:
    return {
        "model_calls": len(calls),
        "tokens_in": sum(c.usage.get("prompt_tokens") or 0 for c in calls),
        "tokens_out": sum(c.usage.get("completion_tokens") or 0 for c in calls),
    }


def _model_metadata(calls: list[ModelCall]) -> dict[str, Any] | None:
    if not calls:
        return None
    last = calls[-1]
    delta = _usage_delta(calls)
    return {
        "deployment": last.deployment,
        "model_version": last.model_version,
        "prompt_version": NORMALIZE_MISSION_VERSION,
        "usage": {**delta, "calls": [c.ledger() for c in calls]},
    }


def _add_usage(conn: psycopg.Connection, org: UUID, campaign_id: UUID, calls: list[ModelCall]) -> None:
    delta = _usage_delta(calls)
    conn.execute(
        """
        update campaigns set budget_json = jsonb_set(budget_json, '{usage}',
            coalesce(budget_json -> 'usage', '{}'::jsonb) || jsonb_build_object(
              'model_calls', coalesce((budget_json -> 'usage' ->> 'model_calls')::int, 0) + %(calls)s,
              'tokens_in', coalesce((budget_json -> 'usage' ->> 'tokens_in')::int, 0) + %(tin)s,
              'tokens_out', coalesce((budget_json -> 'usage' ->> 'tokens_out')::int, 0) + %(tout)s))
        where organization_id = %(org)s and id = %(cid)s
        """,
        {"calls": delta["model_calls"], "tin": delta["tokens_in"], "tout": delta["tokens_out"], "org": org, "cid": campaign_id},
    )


def _decision(
    conn: psycopg.Connection,
    lease: queue.Lease,
    *,
    status: str,
    reason: str,
    checks: list[dict],
    calls: list[ModelCall],
    input_refs: dict[str, Any],
    proposed: dict | None = None,
) -> UUID:
    return conn.execute(
        """
        insert into decisions (organization_id, campaign_id, task_id, kind, status, reason, input_refs_json,
                               model_metadata_json, policy_result_json, proposed_action_json)
        values (%s, %s, %s, 'normalize_mission', %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (
            lease.organization_id, lease.campaign_id, lease.task_id, status, reason, Jsonb(input_refs),
            Jsonb(_model_metadata(calls)) if calls else None,
            Jsonb({"pass": all(c["pass"] for c in checks), "checks": checks}),
            Jsonb(proposed) if proposed else None,
        ),
    ).fetchone()["id"]


def _set_campaign(conn: psycopg.Connection, lease: queue.Lease, *, status: str, stage: str, plan: dict | None = None) -> None:
    conn.execute(
        """
        update campaigns set status = %s, stage = %s, version = version + 1,
               normalized_plan_json = coalesce(%s, normalized_plan_json)
        where organization_id = %s and id = %s
        """,
        (status, stage, Jsonb(plan) if plan is not None else None, lease.organization_id, lease.campaign_id),
    )


def handle_normalize_mission(conn: psycopg.Connection, lease: queue.Lease, *, client: ModelClient) -> None:
    campaign = conn.execute(
        "select status, request_text, request_hash, launch_snapshot_json, budget_json, limits_json "
        "from campaigns where organization_id = %s and id = %s",
        (lease.organization_id, lease.campaign_id),
    ).fetchone()
    snapshot = campaign["launch_snapshot_json"]
    input_refs = {
        "request_hash": campaign["request_hash"],
        "profile_version": snapshot.get("profile_version"),
        "config_version": snapshot.get("config_version"),
        "prompt_version": NORMALIZE_MISSION_VERSION,
    }

    if campaign["status"] not in RUNNABLE:
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    used = campaign["budget_json"].get("usage", {}).get("model_calls", 0)
    if used + MAX_ATTEMPTS > campaign["limits_json"]["max_model_calls"]:
        with queue.fenced(conn, lease):
            _decision(conn, lease, status="blocked", reason="Model-call budget would be exceeded; no call was made.",
                      checks=[{"name": "model_budget", "pass": False, "reason": f"{used} calls used"}], calls=[], input_refs=input_refs)
            _set_campaign(conn, lease, status="needs_human", stage="normalize_mission")
            queue.complete(conn, lease)
        return

    queue.heartbeat(conn, lease, 120)
    now = datetime.now(UTC)
    envelope = build_envelope(campaign_id=str(lease.campaign_id), request_text=campaign["request_text"], snapshot=snapshot, now=now)
    input_refs["envelope_sha256"] = hashlib.sha256(json.dumps(envelope, sort_keys=True, default=str).encode()).hexdigest()
    outcome: NormalizeOutcome = normalize_mission(
        client, campaign_id=str(lease.campaign_id), request_text=campaign["request_text"], snapshot=snapshot, now=now
    )

    with queue.fenced(conn, lease):
        current = conn.execute(
            "select status from campaigns where organization_id = %s and id = %s for update",
            (lease.organization_id, lease.campaign_id),
        ).fetchone()
        _add_usage(conn, lease.organization_id, lease.campaign_id, outcome.calls)
        if current["status"] not in RUNNABLE:
            _decision(conn, lease, status="rejected", reason=f"Campaign became {current['status']} during normalization; plan discarded.",
                      checks=[{"name": "campaign_running", "pass": False, "reason": current["status"]}],
                      calls=outcome.calls, input_refs=input_refs)
            queue.complete(conn, lease)
            return

        if outcome.unavailable:
            final = lease.attempt >= lease.max_attempts
            _decision(
                conn, lease, status="blocked" if final else "rejected",
                reason="Model deployment unavailable" + ("; needs operator attention." if final else "; retry scheduled."),
                checks=[{"name": "model_available", "pass": False, "reason": (outcome.calls[-1].error if outcome.calls else "not configured") or "error"}],
                calls=outcome.calls, input_refs=input_refs,
            )
            if final:
                _set_campaign(conn, lease, status="needs_human", stage="normalize_mission")
                queue.fail(conn, lease, {"error_class": "ModelUnavailable"}, retry_after_seconds=None)
            else:
                queue.fail(conn, lease, {"error_class": "ModelUnavailable"}, retry_after_seconds=UNAVAILABLE_RETRY_SECONDS)
            return

        if outcome.plan is None:
            _decision(conn, lease, status="blocked",
                      reason="Model output failed NormalizedPlan validation twice; no plan was accepted.",
                      checks=[{"name": "schema_valid", "pass": False, "reason": e[:300]} for e in outcome.validation_errors],
                      calls=outcome.calls, input_refs=input_refs)
            _set_campaign(conn, lease, status="needs_human", stage="normalize_mission")
            queue.complete(conn, lease)
            return

        plan = outcome.plan.model_dump(mode="json")
        checks = [{"name": "schema_valid", "pass": True, "reason": "NormalizedPlan validated locally"}]
        checks += [{"name": "plan_policy", "pass": False, "reason": v} for v in outcome.policy_violations] or [
            {"name": "plan_policy", "pass": True, "reason": "query count/limits within policy; no unsafe intent syntax"}
        ]
        if outcome.policy_violations:
            _decision(conn, lease, status="blocked", reason="Proposed plan violates research policy; not accepted.",
                      checks=checks, calls=outcome.calls, input_refs=input_refs, proposed=plan)
            _set_campaign(conn, lease, status="needs_human", stage="normalize_mission")
            queue.complete(conn, lease)
            return

        if outcome.plan.missing_required_fields:
            checks.append({"name": "required_fields", "pass": False,
                           "reason": "missing: " + ", ".join(outcome.plan.missing_required_fields)})
            _decision(conn, lease, status="blocked",
                      reason="Mission is missing required information; operator clarification needed before research.",
                      checks=checks, calls=outcome.calls, input_refs=input_refs, proposed=plan)
            _set_campaign(conn, lease, status="needs_human", stage="clarification", plan=plan)
            queue.complete(conn, lease)
            return

        checks.append({"name": "required_fields", "pass": True, "reason": "no missing required fields"})
        decision_id = _decision(conn, lease, status="accepted",
                                reason="Normalized the request into a validated research plan; company-first research queued.",
                                checks=checks, calls=outcome.calls, input_refs=input_refs, proposed=plan)
        _set_campaign(conn, lease, status="running", stage="research", plan=plan)
        conn.execute(
            """
            insert into tasks (organization_id, campaign_id, kind, dedupe_key, payload_json, status)
            values (%s, %s, 'research', %s, %s, 'ready')
            on conflict (organization_id, dedupe_key) do nothing
            """,
            (
                lease.organization_id, lease.campaign_id, f"campaign:{lease.campaign_id}:research",
                Jsonb({"schema_version": CONTRACT_VERSION, "campaign_id": str(lease.campaign_id), "conversation_id": None,
                       "expected_conversation_version": None, "trigger_message_id": None,
                       "decision_id": str(decision_id), "input_ref_ids": []}),
            ),
        )
        queue.complete(conn, lease)
