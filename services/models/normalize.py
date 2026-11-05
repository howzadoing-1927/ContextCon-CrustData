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
_KNOWN_MUST_HAVE_FIELDS = {
    "funding_stage", "last_round_type", "funding_round", "funding",
    "employee_count", "headcount", "employees", "company_size",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _already_filled(item: str, filled: set[str]) -> bool:
    slug = _slug(item)
    if slug in filled or item.lower() in filled:
        return True
    return any(token in slug for token in filled if len(token) >= 6)


def apply_founder_icp(plan: NormalizedPlan, snapshot: dict) -> NormalizedPlan:
    """Founder ICP is the only targeting source. Notes cannot change who we sell to."""
    icp = snapshot.get("ideal_customer") or {}
    customer_type = str(icp.get("customer_type") or "").strip()
    roles = [str(role).strip() for role in icp.get("buyer_roles") or [] if str(role).strip()]
    regions = [str(place).strip() for place in icp.get("regions") or [] if str(place).strip()]
    exclusions = [str(item).strip() for item in icp.get("exclusions") or [] if str(item).strip()]
    if not customer_type and not roles:
        return plan
    filled: set[str] = set()
    updates: dict[str, Any] = {"exclusions": exclusions}
    if customer_type:
        updates["industries"] = [customer_type]
        filled.update({"industry", "industries", "customer_type"})
    if roles:
        updates["buyer_roles"] = roles
        filled.update({"buyer_role", "buyer_roles", "buyer_title"})
    updates["geography"] = regions
    if regions:
        filled.update({"geography", "region", "regions"})
    updates["missing_required_fields"] = [
        item for item in plan.missing_required_fields if not _already_filled(item, filled)
    ]
    return plan.model_copy(update=updates)


def repair_plan(plan: NormalizedPlan) -> NormalizedPlan:
    """Drop 'missing' fields the plan already filled, and don't let unmapped must-haves block research."""
    filled = set()
    if plan.geography:
        filled.update({"geography", "region", "regions"})
    if plan.industries:
        filled.update({"industry", "industries"})
    if plan.buyer_roles:
        filled.update({"buyer_role", "buyer_roles", "buyer_title"})
    rules = []
    for rule in plan.company_rules:
        key = _slug(rule.field)
        filled.add(key)
        filled.add(rule.field.lower())
        if rule.must_have and key not in _KNOWN_MUST_HAVE_FIELDS:
            rule = rule.model_copy(update={"must_have": False})
        rules.append(rule)
    missing = [item for item in plan.missing_required_fields if not _already_filled(item, filled)]
    if rules == list(plan.company_rules) and missing == list(plan.missing_required_fields):
        return plan
    return plan.model_copy(update={"company_rules": rules, "missing_required_fields": missing})


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
        "operator_notes": request_text,
        "approved_seller_profile": {
            "name": snapshot.get("seller", {}).get("name"),
            "approved_facts": [{"id": f["id"], "text": f["text"]} for f in snapshot["approved_profile"]["approved_facts"]],
            "forbidden_promises": snapshot["approved_profile"].get("forbidden_promises", []),
        },
        "ideal_customer": snapshot.get("ideal_customer"),
        "seller_brief": snapshot.get("seller_brief"),
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
    user = (
        "INPUT (ideal_customer is the targeting source of truth; operator_request is optional notes and must not "
        "change who to sell to; approved facts are authoritative seller claims):\n" + json.dumps(envelope)
    )
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
        plan = repair_plan(apply_founder_icp(plan, snapshot))
        outcome.plan = plan
        outcome.policy_violations = plan_policy_violations(plan, snapshot.get("policy", {}).get("limits", {}))
        return outcome
    return outcome
