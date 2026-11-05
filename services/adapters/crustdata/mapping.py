"""Deterministic NormalizedPlan -> Crustdata company query.

Model output never names a Crustdata field: code picks the field, and values come only from Crustdata's free
autocomplete (exact indexed values). Anything that cannot be mapped is reported, never guessed, and is left
for qualification (B5) instead of narrowing the search.
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from services.core.contracts.model_io import NormalizedPlan

AUTOCOMPLETE = "/company/search/autocomplete"
FUNDING_RULE_FIELDS = {"funding_stage", "last_round_type", "funding_round", "funding"}
HEADCOUNT_RULE_FIELDS = {"employee_count", "headcount", "employees", "company_size"}
ROLE_STOPWORDS = {"of", "the", "and", "for", "a", "an", "&"}
MAX_INDUSTRY_VALUES = 3


class Autocompleter(Protocol):
    def autocomplete(self, field: str, query: str, limit: int = 10) -> list[str]: ...


@dataclass
class Condition:
    field: str
    type: str
    value: Any

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "type": self.type, "value": self.value}


@dataclass
class CompanyQuery:
    conditions: list[Condition]
    role_terms: list[list[str]]

    def filters(self) -> dict[str, Any]:
        return {"op": "and", "conditions": [c.as_dict() for c in self.conditions]}


@dataclass
class MappingReport:
    mapped: list[dict[str, Any]] = field(default_factory=list)
    unmapped: list[dict[str, Any]] = field(default_factory=list)
    weak_matches: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class UnmappablePlan(Exception):
    def __init__(self, message: str, report: MappingReport) -> None:
        super().__init__(message)
        self.report = report


def _norm(value: str) -> str:
    return " ".join(value.lower().split())


def _exact(suggestions: list[str], term: str) -> str | None:
    target = _norm(term)
    return next((s for s in suggestions if _norm(s) == target), None)


def role_terms(role: str) -> list[str]:
    words = [w for w in re.split(r"[\s/,\-]+", role) if w and w.lower() not in ROLE_STOPWORDS]
    return words[:4]


# Fixed abbreviation table: the same role written two ways. Never invents a different role.
_ROLE_ALIASES = {"vp": ["Vice", "President"], "cro": ["Chief", "Revenue", "Officer"], "cso": ["Chief", "Sales", "Officer"]}


def role_variants(role: str) -> list[list[str]]:
    base = role_terms(role)
    if not base:
        return []
    variants = [base]
    lowered = [w.lower() for w in base]
    for i, word in enumerate(lowered):
        if word in _ROLE_ALIASES:
            variants.append(base[:i] + _ROLE_ALIASES[word] + base[i + 1:])
    if lowered[:2] == ["vice", "president"]:
        variants.append(["VP"] + base[2:])
    return variants


def _range_bounds(value: Any) -> tuple[float | None, float | None]:
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
        return float(min(value)), float(max(value))
    return None, None


_ROUND_ORDER = ["pre_seed", "seed"] + [f"series_{c}" for c in "abcdefghij"]


def _slug(value: str) -> str:
    return "_".join(_norm(value).replace("-", " ").split())


def _expand_round_range(value: Any) -> list[str] | None:
    """'Series B'..'Series D' -> series_b, series_c, series_d. Only for two endpoints on the fixed round ladder."""
    if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, str) for v in value)):
        return None
    ends = [_slug(v) for v in value]
    if not all(e in _ROUND_ORDER for e in ends):
        return None
    low, high = sorted(_ROUND_ORDER.index(e) for e in ends)
    return _ROUND_ORDER[low : high + 1]


def _funding_values(value: Any, ac: Autocompleter, operator: str = "equals") -> list[str]:
    expanded = _expand_round_range(value) if operator == "range" else None
    raw = expanded if expanded is not None else (value if isinstance(value, list) else [value])
    picked = []
    for item in raw:
        if not isinstance(item, str):
            continue
        slug = _slug(item)
        available = ac.autocomplete("funding.last_round_type", slug, limit=20)
        match = _exact(available, slug) or _exact(available, item)
        if match and match not in picked:
            picked.append(match)
    return picked


def map_plan(plan: NormalizedPlan, ac: Autocompleter) -> tuple[CompanyQuery, MappingReport]:
    report = MappingReport()
    conditions: list[Condition] = []

    countries, cities = [], []
    for place in plan.geography:
        country = _exact(ac.autocomplete("locations.country", place, limit=10), place)
        if country:
            countries.append(country)
            report.mapped.append({"plan": f"geography:{place}", "field": "locations.country", "value": country})
            continue
        city = _exact(ac.autocomplete("city", place, limit=10), place)
        if city:
            cities.append(city)
            report.mapped.append({"plan": f"geography:{place}", "field": "locations.city", "value": city})
            continue
        report.unmapped.append({"plan": f"geography:{place}", "reason": "no exact country or city value in Crustdata"})
    if countries:
        conditions.append(Condition("locations.country", "in", countries))
    if cities:
        conditions.append(Condition("locations.city", "in", cities))

    industries, specialities = [], []
    for term in plan.industries:
        exact = _exact(ac.autocomplete("basic_info.industries", term, limit=20), term)
        if exact:
            industries.append(exact)
            report.mapped.append({"plan": f"industry:{term}", "field": "basic_info.industries", "value": exact})
            continue
        spec = [s for s in ac.autocomplete("taxonomy.professional_network_specialities", term, limit=20)
                if _norm(term) in _norm(s)][:MAX_INDUSTRY_VALUES]
        if spec:
            specialities.extend(s for s in spec if s not in specialities)
            report.weak_matches.append({
                "plan": f"industry:{term}", "field": "taxonomy.professional_network_specialities", "value": spec,
                "reason": "not a Crustdata industry label; matched company self-tagged specialities",
            })
            continue
        report.unmapped.append({"plan": f"industry:{term}", "reason": "no Crustdata industry or speciality value"})
    if industries:
        conditions.append(Condition("basic_info.industries", "in", industries))
    if specialities:
        conditions.append(Condition("taxonomy.professional_network_specialities", "in", specialities))

    for rule in plan.company_rules:
        key = _norm(rule.field).replace(" ", "_")
        label = f"rule:{rule.field} {rule.operator} {rule.value}"
        if not rule.must_have:
            report.unmapped.append({"plan": label, "reason": "not must_have; checked in qualification"})
        elif key in FUNDING_RULE_FIELDS:
            values = _funding_values(rule.value, ac, rule.operator)
            if values:
                conditions.append(Condition("funding.last_round_type", "in", values))
                report.mapped.append({"plan": label, "field": "funding.last_round_type", "value": values})
            else:
                report.unmapped.append({"plan": label, "reason": "no exact funding round value in Crustdata"})
        elif key in HEADCOUNT_RULE_FIELDS and rule.operator == "range":
            low, high = _range_bounds(rule.value)
            if low is None:
                report.unmapped.append({"plan": label, "reason": "range value is not two numbers"})
            else:
                conditions.append(Condition("headcount.total", "=>", low))
                conditions.append(Condition("headcount.total", "=<", high))
                report.mapped.append({"plan": label, "field": "headcount.total", "value": [low, high]})
        else:
            report.unmapped.append({"plan": label, "reason": "no verified Crustdata mapping for this rule field"})

    for exclusion in plan.exclusions:
        report.unmapped.append({"plan": f"exclusion:{exclusion}", "reason": "applied in qualification, not as a search filter"})
    for assumption in plan.assumptions:
        report.unmapped.append({"plan": f"assumption:{assumption.text}", "reason": "hypothesis; never used as a filter"})

    roles: list[list[str]] = []
    for role in plan.buyer_roles:
        variants = role_variants(role)
        roles.extend(v for v in variants if v not in roles)
        report.mapped.append({"plan": f"buyer_role:{role}", "field": "experience.employment_details.current.title", "value": variants})
    roles = roles[:6]

    if not (countries or cities) or not (industries or specialities):
        raise UnmappablePlan("plan needs at least one mapped geography and one mapped industry", report)
    if not roles:
        raise UnmappablePlan("plan has no buyer role to search for", report)
    return CompanyQuery(conditions=conditions, role_terms=roles), report
