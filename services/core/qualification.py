"""Deterministic qualification (doc 04): code, not a model score, decides eligibility.

eligible = identity supported AND every must-have passes AND no exclusion matches AND no unresolved conflict.
Missing data is `unknown`, and unknown is never turned into pass.
"""

import json
from dataclasses import dataclass
from typing import Any

from services.adapters.crustdata.mapping import _expand_round_range, _slug

FIELD_INDUSTRY = ("taxonomy.professional_network_industry",)
FIELD_SPECIALITIES = ("taxonomy.professional_network_specialities",)
FIELD_NAME = ("basic_info.name",)
FIELD_COUNTRY = ("locations.country",)
FIELD_LOCATION = ("locations.city", "locations.headquarters")
COUNTRY_ALIASES = {"india": {"ind", "india"}, "united states": {"usa", "united states", "united states of america"},
                   "united kingdom": {"gbr", "united kingdom"}}


@dataclass
class Criterion:
    name: str
    result: str  # pass | fail | unknown
    evidence_ids: list[str]
    reason: str
    kind: str  # identity | must_have | exclusion | conflict

    def contract(self) -> dict[str, Any]:
        return {"name": self.name, "result": self.result, "evidence_ids": self.evidence_ids, "reason": self.reason}


@dataclass
class Qualification:
    criteria: list[Criterion]
    fit: str  # qualified | rejected | needs_evidence
    hypotheses: list[dict[str, Any]]

    @property
    def eligible(self) -> bool:
        return self.fit == "qualified"


def _values(evidence: list[dict], suffixes: tuple[str, ...]) -> list[tuple[str, Any]]:
    """(evidence_id, decoded value) for evidence rows whose field_path ends with one of the suffixes."""
    out = []
    for row in evidence:
        path = row["field_path"].split("#", 1)[-1]
        if any(path == s or path.endswith("." + s) for s in suffixes):
            try:
                value = json.loads(row["excerpt"])
            except (TypeError, ValueError):
                value = row["excerpt"]
            out.append((str(row["id"]), value))
    return out


def _texts(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).lower() for v in value]
    return [str(value).lower()] if value is not None else []


def _stem(term: str) -> str:
    term = term.lower().strip()
    for suffix in ("ies", "es", "s", "ing"):
        if term.endswith(suffix) and len(term) - len(suffix) >= 3:
            return term[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return term


def _geography(place: str, evidence: list[dict]) -> Criterion:
    target = place.lower()
    accepted = COUNTRY_ALIASES.get(target, {target})
    country = _values(evidence, FIELD_COUNTRY)
    location = _values(evidence, FIELD_LOCATION)
    for eid, value in country:
        if any(t in accepted for t in _texts(value)):
            return Criterion(f"geography:{place}", "pass", [eid], f"HQ country observed as {value}", "must_have")
    for eid, value in location:
        if any(target in t for t in _texts(value)):
            return Criterion(f"geography:{place}", "pass", [eid], f"HQ location observed as {value}", "must_have")
    if country or location:
        seen = [v for _, v in country + location]
        return Criterion(f"geography:{place}", "fail", [e for e, _ in country + location], f"observed location {seen} does not match", "must_have")
    return Criterion(f"geography:{place}", "unknown", [], "no location evidence", "must_have")


def _industry(term: str, mapped_value: Any, weak: bool, evidence: list[dict]) -> Criterion:
    wanted = {str(v).lower() for v in (mapped_value if isinstance(mapped_value, list) else [mapped_value])} | {term.lower()}
    for fields, label in ((FIELD_INDUSTRY, "industry"), (FIELD_SPECIALITIES, "self-tagged speciality")):
        for eid, value in _values(evidence, fields):
            hits = [t for t in _texts(value) if t in wanted or term.lower() in t]
            if hits:
                return Criterion(f"industry:{term}", "pass", [eid], f"observed {label} {hits[0]!r}" + (" (weak: self-tagged)" if weak or label != "industry" else ""), "must_have")
    seen = _values(evidence, FIELD_INDUSTRY + FIELD_SPECIALITIES)
    if seen:
        return Criterion(f"industry:{term}", "unknown", [e for e, _ in seen],
                         "industry evidence present but does not mention the requested industry", "must_have")
    return Criterion(f"industry:{term}", "unknown", [], "no industry evidence", "must_have")


def _rule(rule: dict, evidence: list[dict]) -> Criterion:
    name = f"rule:{rule['field']}"
    key = _slug(rule["field"])
    if key in {"funding_stage", "last_round_type", "funding_round", "funding"}:
        allowed = _expand_round_range(rule["value"]) if rule["operator"] == "range" else None
        if allowed is None:
            raw = rule["value"] if isinstance(rule["value"], list) else [rule["value"]]
            allowed = [_slug(str(v)) for v in raw]
        observed = _values(evidence, ("funding.last_round_type",))
        if not observed:
            return Criterion(name, "unknown", [], "no funding round evidence", "must_have")
        eid, value = observed[0]
        ok = _slug(str(value)) in allowed
        return Criterion(name, "pass" if ok else "fail", [eid], f"last round observed as {value}; required {allowed}", "must_have")
    if key in {"employee_count", "headcount", "employees", "company_size"} and rule["operator"] == "range":
        bounds = rule["value"]
        observed = _values(evidence, ("headcount.total",))
        if not observed or not (isinstance(bounds, list) and len(bounds) == 2):
            return Criterion(name, "unknown", [], "no headcount evidence", "must_have")
        eid, value = observed[0]
        ok = float(min(bounds)) <= float(value) <= float(max(bounds))
        return Criterion(name, "pass" if ok else "fail", [eid], f"headcount observed as {value}; required {bounds}", "must_have")
    return Criterion(name, "unknown", [], "no verified data source for this must-have", "must_have")


def _exclusion(term: str, evidence: list[dict]) -> Criterion:
    stem = _stem(term)
    rows = _values(evidence, FIELD_NAME + FIELD_INDUSTRY + FIELD_SPECIALITIES)
    for eid, value in rows:
        if any(stem in t for t in _texts(value)):
            return Criterion(f"exclusion:{term}", "fail", [eid], f"excluded: observed {value!r} matches {term!r}", "exclusion")
    if rows:
        return Criterion(f"exclusion:{term}", "pass", [e for e, _ in rows], f"name/industry evidence does not match {term!r}", "exclusion")
    return Criterion(f"exclusion:{term}", "unknown", [], "no evidence to rule the exclusion out", "exclusion")


def _conflict(evidence: list[dict]) -> Criterion:
    conflicted = [str(r["id"]) for r in evidence if r["fact_status"] == "conflicted"]
    if conflicted:
        return Criterion("no_conflict", "fail", conflicted, "conflicted evidence present", "conflict")
    for fields in (FIELD_NAME, ("basic_info.primary_domain",)):
        by_endpoint: dict[str, str] = {}
        for row in evidence:
            path = row["field_path"]
            if path.split("#", 1)[-1] in fields:
                by_endpoint[path.split("#", 1)[0]] = str(json.loads(row["excerpt"])).lower()
        if len(set(by_endpoint.values())) > 1:
            return Criterion("no_conflict", "fail", [], f"{fields[0]} differs between sources: {sorted(set(by_endpoint.values()))}", "conflict")
    return Criterion("no_conflict", "pass", [], "no conflicting identity evidence", "conflict")


def qualify(prospect: dict, evidence: list[dict], plan: dict, mapping: dict | None) -> Qualification:
    identity = prospect["identity_json"] or {}
    relationship = identity.get("relationship") or {}
    status = relationship.get("status")
    criteria = [
        Criterion(
            "identity",
            "pass" if status == "supported" and relationship.get("evidence_ids") else ("fail" if status == "conflicted" else "unknown"),
            relationship.get("evidence_ids", []),
            relationship.get("reason") or "no relationship evidence",
            "identity",
        )
    ]
    mapping = mapping or {}
    mapped_industry = {m["plan"].split(":", 1)[1]: m["value"] for m in mapping.get("mapped", []) if m["plan"].startswith("industry:")}
    weak_industry = {m["plan"].split(":", 1)[1]: m["value"] for m in mapping.get("weak_matches", []) if m["plan"].startswith("industry:")}

    criteria += [_geography(place, evidence) for place in plan.get("geography", [])]
    for term in plan.get("industries", []):
        weak = term in weak_industry
        criteria.append(_industry(term, weak_industry.get(term) if weak else mapped_industry.get(term, term), weak, evidence))
    criteria += [_rule(rule, evidence) for rule in plan.get("company_rules", []) if rule.get("must_have")]
    criteria += [_exclusion(term, evidence) for term in plan.get("exclusions", [])]
    criteria.append(_conflict(evidence))

    gating = [c for c in criteria if c.kind in ("identity", "must_have", "conflict")]
    exclusions = [c for c in criteria if c.kind == "exclusion"]
    if all(c.result == "pass" for c in gating) and all(c.result == "pass" for c in exclusions):
        fit = "qualified"
    elif any(c.result == "fail" for c in criteria):
        fit = "rejected"
    else:
        fit = "needs_evidence"
    hypotheses = [{"text": a["text"], "basis_evidence_ids": []} for a in plan.get("assumptions", [])]
    return Qualification(criteria, fit, hypotheses)
