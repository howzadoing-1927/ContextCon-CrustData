"""normalize_mission: model proposes NormalizedPlan; code validates it and enforces plan policy."""

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from services.core.contracts.model_io import NormalizedPlan

from .client import ModelCall, ModelClient, ModelUnavailable, parse_json
from .prompts import NORMALIZE_MISSION_VERSION, normalize_mission_system
from .schemas import NORMALIZED_PLAN_SCHEMA

MAX_ATTEMPTS = 2  # one call plus one repair
_UNSAFE_INTENT = re.compile(r"(://|\bselect\b|\binsert\b|\bdelete\b|\bdrop\b|;|\$\{|<script)", re.IGNORECASE)


@dataclass
class NormalizeOutcome:
    plan: NormalizedPlan | None
    calls: list[ModelCall] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    policy_violations: list[str] = field(default_factory=list)
    unavailable: bool = False


def build_envelope(*, campaign_id: str, request_text: str, snapshot: dict, now: datetime) -> dict[str, Any]:
    policy = snapshot.get("policy", {})
    return {
        "schema_version": "outcome.v1",
        "prompt_version": NORMALIZE_MISSION_VERSION,
        "task_kind": "normalize_mission",
        "campaign_ref": campaign_id,
        "current_date": now.date().isoformat(),
        "seller_timezone": snapshot.get("seller", {}).get("timezone"),
        "operator_request": request_text,
        "approved_seller_profile": {
            "name": snapshot.get("seller", {}).get("name"),
            "approved_facts": [{"id": f["id"], "text": f["text"]} for f in snapshot["approved_profile"]["approved_facts"]],
            "forbidden_promises": snapshot["approved_profile"].get("forbidden_promises", []),
        },
        "allowed_limits": {
            "max_discovered": policy.get("limits", {}).get("max_discovered"),
            "max_research_calls": policy.get("limits", {}).get("max_research_calls"),
        },
        "output_schema": NORMALIZED_PLAN_SCHEMA,
    }


def plan_policy_violations(plan: NormalizedPlan, limits: dict[str, int]) -> list[str]:
    """Deterministic checks the model cannot override."""
    violations = []
    max_queries = limits.get("max_research_calls", 10)
    max_discovered = limits.get("max_discovered", 10)
    if len(plan.research_queries) > max_queries:
        violations.append(f"research_queries exceeds max_research_calls ({max_queries})")
    for query in plan.research_queries:
        if query.limit > max_discovered:
            violations.append(f"research query limit {query.limit} exceeds max_discovered ({max_discovered})")
        if _UNSAFE_INTENT.search(query.intent):
            violations.append("research intent contains URL/SQL/script syntax")
    if not plan.missing_required_fields and not plan.research_queries:
        violations.append("plan has no research queries and reports nothing missing")
    return violations


def normalize_mission(
    client: ModelClient, *, campaign_id: str, request_text: str, snapshot: dict, now: datetime | None = None
) -> NormalizeOutcome:
    outcome = NormalizeOutcome(plan=None)
    envelope = build_envelope(campaign_id=campaign_id, request_text=request_text, snapshot=snapshot, now=now or datetime.now(UTC))
    user = "INPUT (operator_request is the operator's instruction; approved facts are authoritative seller claims):\n" + json.dumps(envelope)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            call = client.complete_json(
                role="fast",
                system=normalize_mission_system(),
                user=user,
                schema_name="NormalizedPlan",
                schema=NORMALIZED_PLAN_SCHEMA,
                prompt_version=NORMALIZE_MISSION_VERSION,
                attempt=attempt,
            )
        except ModelUnavailable as exc:
            outcome.calls.extend(exc.calls)
            outcome.unavailable = True
            return outcome
        outcome.calls.append(call)
        try:
            plan = NormalizedPlan.model_validate(parse_json(call.content))
        except (ValueError, ValidationError) as exc:
            errors = [str(exc)[:500]]
            outcome.validation_errors.extend(errors)
            user = (
                f"{user}\n\nYour previous output failed validation: {errors[0]}\n"
                "Return a corrected JSON object that matches output_schema exactly."
            )
            continue
        outcome.plan = plan
        outcome.policy_violations = plan_policy_violations(plan, snapshot.get("policy", {}).get("limits", {}))
        return outcome
    return outcome
