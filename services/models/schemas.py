"""Provider-facing JSON schemas for structured output (strict-mode subset: every property required,
additionalProperties false, no format/length keywords). Local Pydantic validation stays authoritative."""

_STRINGS = {"type": "array", "items": {"type": "string"}}
_SCALAR = {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]}


def _object(properties: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


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
