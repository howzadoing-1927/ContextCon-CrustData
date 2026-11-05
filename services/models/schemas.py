"""Provider-facing JSON schemas for structured output (strict-mode subset: every property required,
additionalProperties false, no format/length keywords). Local Pydantic validation stays authoritative."""

_STRINGS = {"type": "array", "items": {"type": "string"}}
_SCALAR = {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]}


def _object(properties: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


DRAFT_PROPOSAL_SCHEMA = _object(
    {
        "purpose": {"type": "string", "enum": ["initial", "answer", "clarify", "offer_slots", "confirm"]},
        "subject": {"type": "string"},
        "body_text": {"type": "string"},
        "claims": {
            "type": "array",
            "items": _object(
                {
                    "text": {"type": "string"},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "kind": {"type": "string", "enum": ["seller_fact", "prospect_fact", "hypothesis", "scheduling_fact"]},
                    "evidence_ids": _STRINGS,
                    "approved_fact_ids": _STRINGS,
                }
            ),
        },
        "used_slot_ids": _STRINGS,
        "reason": {"type": "string"},
        "evidence_ids": _STRINGS,
    }
)

VERIFICATION_RESULT_SCHEMA = _object(
    {
        "verdict": {"type": "string", "enum": ["pass", "revise", "block"]},
        "unsupported_claims": {"type": "array", "items": _object({"text": {"type": "string"}, "reason": {"type": "string"}})},
        "contradictions": _STRINGS,
        "unauthorized_promises": _STRINGS,
        "unanswered_questions": _STRINGS,
        "injection_flags": _STRINGS,
        "reason": {"type": "string"},
        "evidence_ids": _STRINGS,
    }
)

NORMALIZED_PLAN_SCHEMA = _object(
    {
        "objective": {"type": "string", "enum": ["book_demo"]},
        "geography": _STRINGS,
        "industries": _STRINGS,
        "company_rules": {
            "type": "array",
            "items": _object(
                {
                    "field": {"type": "string"},
                    "operator": {"type": "string", "enum": ["equals", "contains", "range"]},
                    "value": {"anyOf": [*_SCALAR["anyOf"], {"type": "array", "items": _SCALAR}]},
                    "must_have": {"type": "boolean"},
                }
            ),
        },
        "buyer_roles": _STRINGS,
        "exclusions": _STRINGS,
        "missing_required_fields": _STRINGS,
        "assumptions": {
            "type": "array",
            "items": _object({"text": {"type": "string"}, "status": {"type": "string", "enum": ["hypothesis"]}}),
        },
        "research_queries": {
            "type": "array",
            "items": _object({"intent": {"type": "string"}, "limit": {"type": "integer"}}),
        },
        "stop_conditions": _STRINGS,
    }
)
