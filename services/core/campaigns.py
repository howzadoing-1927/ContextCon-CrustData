"""Campaign launch (one transaction: campaign + normalize_mission task + launch decision) and reads.

Every query is scoped by the caller's organization_id; the request body never selects a tenant.
"""

import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from .admin import REQUIRED_GOOGLE_SCOPES
from .contracts.base import normalize_email
from .contracts.enums import ErrorCode
from .contracts.requests import CampaignCreate
from .contracts.version import CONTRACT_VERSION
from .contracts.views import CampaignLaunchView, CampaignView, DecisionView, MissionDetail, Usage
from .errors import DomainError

ZERO_USAGE = {
    "model_calls": 0,
    "research_calls": 0,
    "outbound_attempts": 0,
    "calendar_attempts": 0,
    "tokens_in": 0,
    "tokens_out": 0,
    "estimated_cost": None,
}

_CAMPAIGN_COLUMNS = """
c.id, c.request_key, c.request_hash, c.request_text, c.mode, c.status, c.version, c.stage,
c.profile_version, c.config_version, c.budget_json, c.created_at, c.updated_at,
(select d.id from public.decisions d
  where d.organization_id = c.organization_id and d.campaign_id = c.id
  order by d.created_at desc, d.id desc limit 1) as last_decision_id
"""


def request_hash(body: CampaignCreate) -> str:
    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def launch_task_dedupe_key(campaign_id: UUID) -> str:
    return f"campaign:{campaign_id}:normalize_mission"


def _campaign_view(row: dict[str, Any]) -> CampaignView:
    return CampaignView(
        id=row["id"],
        request_text=row["request_text"],
        mode=row["mode"],
        status=row["status"],
        version=row["version"],
        stage=row["stage"],
        profile_version=row["profile_version"],
        config_version=row["config_version"],
        usage=Usage.model_validate(row["budget_json"].get("usage", ZERO_USAGE)),
        last_decision_id=row["last_decision_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _select_campaign_by_key(conn: psycopg.Connection, organization_id: UUID, key: str) -> dict | None:
    return conn.execute(
        f"select {_CAMPAIGN_COLUMNS} from public.campaigns c where c.organization_id = %s and c.request_key = %s",
        (organization_id, key),
    ).fetchone()


def _replay(conn: psycopg.Connection, organization_id: UUID, row: dict, body_hash: str) -> CampaignLaunchView:
    if row["request_hash"] != body_hash:
        raise DomainError(
            409,
            ErrorCode.CONFLICT,
            "Idempotency-Key was already used with a different request body.",
            details={"field": "Idempotency-Key"},
        )
    task = conn.execute(
        "select id from public.tasks where organization_id = %s and dedupe_key = %s",
        (organization_id, launch_task_dedupe_key(row["id"])),
    ).fetchone()
    return CampaignLaunchView(**_campaign_view(row).model_dump(), task_id=task["id"])


def _check_launch_policy(conn: psycopg.Connection, organization_id: UUID, body: CampaignCreate) -> list[dict]:
    org = conn.execute(
        "select profile_version, config_version, approved_at, policy_json from public.organizations where id = %s",
        (organization_id,),
    ).fetchone()
    if body.profile_version != org["profile_version"] or body.config_version != org["config_version"]:
        raise DomainError(
            409,
            ErrorCode.CONFLICT,
            "Profile or policy version is stale; reload the workspace.",
            details={"current_profile_version": org["profile_version"], "current_config_version": org["config_version"]},
        )
    if org["approved_at"] is None:
        raise DomainError(422, ErrorCode.DOMAIN_INVALID, "Seller profile is not approved.", details={"field": "profile"})

    policy = org["policy_json"]
    if policy.get("simulation") is not True:
        raise DomainError(422, ErrorCode.DOMAIN_INVALID, "Workspace policy must be simulation-only.")

    consented = {
        normalize_email(r["email"])
        for r in policy.get("consented_recipients", [])
        if r.get("role") == "buyer_test" and r.get("consent_record")
    }
    if body.buyer_test_email not in consented:
        raise DomainError(
            422,
            ErrorCode.RECIPIENT_NOT_ALLOWED,
            "Only the consented test buyer can receive this message.",
            details={"field": "buyer_test_email"},
        )

    policy_limits = policy.get("limits", {})
    over = sorted(k for k, v in body.limits.model_dump().items() if k in policy_limits and v > policy_limits[k])
    if over:
        raise DomainError(
            422, ErrorCode.DOMAIN_INVALID, "Requested limits exceed workspace policy.", details={"fields": over}
        )

    connection = conn.execute(
        """
        select status, granted_scopes from public.connections
        where organization_id = %s and provider = 'google' and purpose = 'seller'
        """,
        (organization_id,),
    ).fetchone()
    missing_scopes = sorted(set(REQUIRED_GOOGLE_SCOPES) - set(connection["granted_scopes"] if connection else []))
    if connection is None or connection["status"] != "connected" or missing_scopes:
        raise DomainError(
            422,
            ErrorCode.DOMAIN_INVALID,
            "Seller Google account is not connected with the required scopes.",
            details={"connection_status": connection["status"] if connection else None, "missing_scopes": missing_scopes},
        )

    return [
        {"name": "versions_current", "pass": True, "reason": "profile and config versions match the workspace"},
        {"name": "profile_approved", "pass": True, "reason": "seller profile has an approval timestamp"},
        {"name": "simulation_only", "pass": True, "reason": "workspace policy simulation=true"},
        {"name": "recipient_allowlist", "pass": True, "reason": "buyer_test_email exactly matches a consented buyer_test"},
        {"name": "limits_within_policy", "pass": True, "reason": "requested limits do not exceed workspace limits"},
        {"name": "seller_google_ready", "pass": True, "reason": "seller connection connected with required scopes"},
    ]


def launch_campaign(
    conn: psycopg.Connection, *, organization_id: UUID, user_id: UUID, idempotency_key: str, body: CampaignCreate
) -> CampaignLaunchView:
    """Must run inside one transaction. Replays return the original result; a different body is 409."""
    body_hash = request_hash(body)
    existing = _select_campaign_by_key(conn, organization_id, idempotency_key)
    if existing is not None:
        return _replay(conn, organization_id, existing, body_hash)

    checks = _check_launch_policy(conn, organization_id, body)

    campaign_id = uuid4()
    inserted = conn.execute(
        """
        insert into public.campaigns
          (id, organization_id, request_key, request_hash, request_text, mode, buyer_test_email, status, stage,
           version, profile_version, config_version, limits_json, budget_json, started_at)
        values (%s, %s, %s, %s, %s, 'simulation', %s, 'running', 'normalize_mission', 1, %s, %s, %s, %s, now())
        on conflict (organization_id, request_key) do nothing
        returning id
        """,
        (
            campaign_id, organization_id, idempotency_key, body_hash, body.request_text, body.buyer_test_email,
            body.profile_version, body.config_version, Jsonb(body.limits.model_dump()), Jsonb({"usage": ZERO_USAGE}),
        ),
    ).fetchone()
    if inserted is None:
        # A concurrent request with the same key committed first.
        return _replay(conn, organization_id, _select_campaign_by_key(conn, organization_id, idempotency_key), body_hash)

    task = conn.execute(
        """
        insert into public.tasks (organization_id, campaign_id, kind, dedupe_key, payload_json, status)
        values (%s, %s, 'normalize_mission', %s, %s, 'ready')
        returning id
        """,
        (
            organization_id,
            campaign_id,
            launch_task_dedupe_key(campaign_id),
            Jsonb(
                {
                    "schema_version": CONTRACT_VERSION,
                    "campaign_id": str(campaign_id),
                    "conversation_id": None,
                    "expected_conversation_version": None,
                    "trigger_message_id": None,
                    "decision_id": None,
                    "input_ref_ids": [],
                }
            ),
        ),
    ).fetchone()
    conn.execute(
        """
        insert into public.decisions
          (organization_id, campaign_id, task_id, kind, status, reason, input_refs_json, policy_result_json)
        values (%s, %s, %s, 'campaign_launch', 'accepted', %s, %s, %s)
        """,
        (
            organization_id,
            campaign_id,
            task["id"],
            "Launch passed pre-enqueue policy checks; normalize_mission queued.",
            Jsonb(
                {
                    "request_hash": body_hash,
                    "profile_version": body.profile_version,
                    "config_version": body.config_version,
                    "launched_by": str(user_id),
                }
            ),
            Jsonb({"pass": True, "checks": checks}),
        ),
    )
    row = _select_campaign_by_key(conn, organization_id, idempotency_key)
    return CampaignLaunchView(**_campaign_view(row).model_dump(), task_id=task["id"])


def _decision_view(row: dict[str, Any]) -> DecisionView:
    return DecisionView.model_validate(
        {
            "id": row["id"],
            "kind": row["kind"],
            "status": row["status"],
            "reason": row["reason"],
            "evidence_ids": row["evidence_ids"],
            "input_refs": row["input_refs_json"],
            "model": row["model_metadata_json"],
            "policy": row["policy_result_json"],
            "proposed_action": row["proposed_action_json"],
            "actual_action": None,
            "resolution": row["resolution_json"],
            "created_at": row["created_at"],
        }
    )


def get_mission_detail(conn: psycopg.Connection, *, organization_id: UUID, campaign_id: UUID) -> MissionDetail:
    row = conn.execute(
        f"select {_CAMPAIGN_COLUMNS} from public.campaigns c where c.organization_id = %s and c.id = %s",
        (organization_id, campaign_id),
    ).fetchone()
    if row is None:
        raise DomainError(404, ErrorCode.NOT_FOUND, "Campaign not found.")
    exceptions = conn.execute(
        """
        select * from public.decisions
        where organization_id = %s and campaign_id = %s and status = 'blocked'
        order by created_at, id
        """,
        (organization_id, campaign_id),
    ).fetchall()
    # Prospects, conversation, evidence and handoff mapping arrive with B4-B7; nothing writes them in B2.
    return MissionDetail(
        **_campaign_view(row).model_dump(),
        prospects=[],
        conversation=None,
        open_exceptions=[_decision_view(d) for d in exceptions],
        evidence=[],
        handoff=None,
    )
