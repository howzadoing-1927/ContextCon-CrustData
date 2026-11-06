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
MAX_ROLE_VARIANTS = 8
# Persona words founders type that are not job titles. Dropped before title search.
_GENERIC_ROLE_WORDS = {
    "leader", "leaders", "leadership", "buyer", "buyers", "decision", "maker", "makers",
    "stakeholder", "stakeholders", "executive", "executives", "management",
    "industry", "industries", "professional", "professionals", "people", "person",
    "role", "roles", "target", "targets", "customer", "customers", "champion",
    "team", "teams", "staff", "contact", "contacts",
}
_COLLECTIVE_ROLE = {"leader", "leaders", "leadership", "buyer", "buyers", "decision", "maker", "makers",
                    "stakeholder", "stakeholders", "champion"}
_ROLE_INDUSTRY_WORDS = {
    "restaurant", "restaurants", "hotel", "hotels", "school", "schools", "retail",
    "hospital", "hospitals", "clinic", "clinics",
}
_OWNER_WORDS = {"owner", "owners", "proprietor", "proprietors"}
_OWNER_TITLES = [["Owner"], ["Founder"], ["Proprietor"]]
_PERSONA_SUFFIX = re.compile(r"\b(owners?|founders?|operators?|managers?|leaders?|buyers?)\b", re.I)
# Real titles used when the founder wrote a persona instead of a title.
FALLBACK_ROLE_TERMS = [
    ["CEO"], ["Founder"], ["President"], ["Managing", "Director"],
    ["Director"], ["Vice", "President"], ["Head"], ["Partner"],
]
# Short codes founders type that are not Crustdata country/city labels. Values are autocomplete queries.
_GEO_EXPAND: dict[str, list[str]] = {
    "us": ["United States"],
    "usa": ["United States"],
    "america": ["United States"],
    "uk": ["United Kingdom"],
    "uae": ["United Arab Emirates"],
    "britain": ["United Kingdom"],
    "great britain": ["United Kingdom"],
    "up": ["Uttar Pradesh"],
    "mh": ["Maharashtra"],
    "gj": ["Gujarat"],
    "rj": ["Rajasthan"],
    "wb": ["West Bengal"],
    "pb": ["Punjab"],
    "hr": ["Haryana"],
    "kl": ["Kerala"],
    "ka": ["Karnataka"],
    "tn": ["Tamil Nadu"],
    "mp": ["Madhya Pradesh"],
    "ap": ["Andhra Pradesh"],
    "ts": ["Telangana"],
    "tg": ["Telangana"],
    "dl": ["Delhi"],
    "ncr": ["Delhi"],
    "delhi ncr": ["Delhi"],
    "od": ["Odisha"],
    "or": ["Odisha"],
    "jh": ["Jharkhand"],
    "br": ["Bihar"],
    "hp": ["Himachal Pradesh"],
    "cg": ["Chhattisgarh"],
    "ga": ["Goa"],
    "as": ["Assam"],
}
_REGION_COUNTRY = {
    "andhra pradesh": "India", "arunachal pradesh": "India", "assam": "India", "bihar": "India",
    "chhattisgarh": "India", "goa": "India", "gujarat": "India", "haryana": "India",
    "himachal pradesh": "India", "jharkhand": "India", "karnataka": "India", "kerala": "India",
    "madhya pradesh": "India", "maharashtra": "India", "manipur": "India", "meghalaya": "India",
    "mizoram": "India", "nagaland": "India", "odisha": "India", "punjab": "India",
    "rajasthan": "India", "sikkim": "India", "tamil nadu": "India", "telangana": "India",
    "tripura": "India", "uttar pradesh": "India", "uttarakhand": "India", "west bengal": "India",
    "delhi": "India", "jammu and kashmir": "India", "ladakh": "India", "puducherry": "India",
    "chandigarh": "India",
}
_COUNTRY_NEEDLES = {
    "india": {"ind", "india"},
    "united states": {"usa", "us", "united states", "united states of america"},
    "united kingdom": {"gbr", "uk", "united kingdom", "great britain"},
    "united arab emirates": {"uae", "united arab emirates"},
}


class Autocompleter(Protocol):
    def autocomplete(self, field: str, query: str, limit: int = 10) -> list[str]: ...


@dataclass
class Condition:
    field: str
    type: str
    value: Any

    def as_dict(self) -> dict[str, Any]:
        if self.field == "__group__":
            return {"op": self.type, "conditions": self.value}
        return {"field": self.field, "type": self.type, "value": self.value}


@dataclass
class CompanyQuery:
    conditions: list[Condition]
    role_terms: list[list[str]]
    fallback_role_terms: list[list[str]] = field(default_factory=list)

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


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def geography_terms(place: str) -> list[str]:
    """Place as typed, plus canonical expansions (UP → Uttar Pradesh, US → United States)."""
    seen: list[str] = []

    def add(term: str) -> None:
        cleaned = term.strip()
        if cleaned and _norm(cleaned) not in {_norm(item) for item in seen}:
            seen.append(cleaned)

    add(place)
    for key in (_norm(place), _compact(place)):
        for term in _GEO_EXPAND.get(key, []):
            add(term)
    return seen


def geography_needles(place: str) -> set[str]:
    """Lowercase terms that mean this place, for qualification matching."""
    needles = {_norm(term) for term in geography_terms(place)}
    extra: set[str] = set()
    for term in needles:
        extra.update(_COUNTRY_NEEDLES.get(term, set()))
    return needles | extra


def _exact(suggestions: list[str], term: str) -> str | None:
    target = _norm(term)
    return next((s for s in suggestions if _norm(s) == target), None)


def _hq_phrase_hits(suggestions: list[str], phrase: str) -> list[str]:
    needle = _norm(phrase)
    return [item for item in suggestions if needle and needle in _norm(item)]


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


def _dedupe_terms(groups: list[list[str]]) -> list[list[str]]:
    seen: set[tuple[str, ...]] = set()
    out: list[list[str]] = []
    for group in groups:
        key = tuple(w.lower() for w in group)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(group)
    return out


def _industry_queries(term: str) -> list[str]:
    """'Restaurant owners' → Restaurant owners, Restaurant, Restaurants (real industry labels)."""
    queries = [term]
    stem = " ".join(_PERSONA_SUFFIX.sub("", term).split())
    if stem and _norm(stem) != _norm(term):
        queries.append(stem)
        if not stem.lower().endswith("s"):
            queries.append(f"{stem}s")
    return list(dict.fromkeys(queries))


def expand_buyer_roles(roles: list[str]) -> tuple[list[list[str]], list[list[str]]]:
    """Title-search terms plus fallback exec titles. Always OR fallbacks so research does not die on personas."""
    primary: list[list[str]] = []
    for role in roles:
        words = {w.lower() for w in re.split(r"[\s/,\-]+", role) if w}
        if words & _OWNER_WORDS:
            primary.extend(_OWNER_TITLES)
        for variant in role_variants(role):
            keep = [w for w in variant if w.lower() not in _GENERIC_ROLE_WORDS and w.lower() not in _ROLE_INDUSTRY_WORDS]
            if keep:
                primary.append(keep)
        if words & _COLLECTIVE_ROLE:
            primary.extend([list(term) for term in FALLBACK_ROLE_TERMS])
    primary = _dedupe_terms(primary)
    fallback = [list(term) for term in FALLBACK_ROLE_TERMS]
    return _dedupe_terms(primary + fallback)[:MAX_ROLE_VARIANTS], []


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

    countries, cities, headquarters = [], [], []
    for place in plan.geography:
        mapped = False
        for term in geography_terms(place):
            country = _exact(ac.autocomplete("locations.country", term, limit=10), term)
            if country:
                if country not in countries:
                    countries.append(country)
                report.mapped.append({"plan": f"geography:{place}", "field": "locations.country", "value": country})
                mapped = True
                break
            city = _exact(ac.autocomplete("city", term, limit=10), term)
            if city:
                if city not in cities:
                    cities.append(city)
                report.mapped.append({"plan": f"geography:{place}", "field": "locations.city", "value": city})
                mapped = True
                break
        if mapped:
            continue
        # States/regions are not countries or cities. Confirm the phrase exists in HQ autocomplete, then
        # filter locations.headquarters with contains — `in` on one HQ string misses cities in that state.
        for term in geography_terms(place):
            if len(term.strip()) < 3:
                continue
            hits = _hq_phrase_hits(ac.autocomplete("locations.headquarters", term, limit=10), term)
            if not hits:
                continue
            if term not in headquarters:
                headquarters.append(term)
            report.mapped.append({"plan": f"geography:{place}", "field": "locations.headquarters", "value": term})
            parent = _REGION_COUNTRY.get(_norm(term))
            if parent:
                country = _exact(ac.autocomplete("locations.country", parent, limit=10), parent)
                if country and country not in countries:
                    countries.append(country)
                    report.mapped.append({"plan": f"geography:{place}", "field": "locations.country", "value": country})
            mapped = True
            break
        if not mapped:
            report.unmapped.append({"plan": f"geography:{place}", "reason": "no exact country, city, or headquarters region in Crustdata"})
    if countries:
        conditions.append(Condition("locations.country", "in", countries))
    if cities:
        conditions.append(Condition("locations.city", "in", cities))
    if headquarters:
        hq_conds = [Condition("locations.headquarters", "(.)", phrase) for phrase in headquarters]
        if len(hq_conds) == 1:
            conditions.append(hq_conds[0])
        else:
            conditions.append(Condition("__group__", "or", [item.as_dict() for item in hq_conds]))

    industries, specialities = [], []
    for term in plan.industries:
        mapped = False
        for query in _industry_queries(term):
            exact = _exact(ac.autocomplete("basic_info.industries", query, limit=20), query)
            if exact:
                if exact not in industries:
                    industries.append(exact)
                report.mapped.append({"plan": f"industry:{term}", "field": "basic_info.industries", "value": exact})
                mapped = True
                break
        if mapped:
            continue
        spec: list[str] = []
        for query in _industry_queries(term):
            spec.extend(
                s for s in ac.autocomplete("taxonomy.professional_network_specialities", query, limit=20)
                if _norm(query) in _norm(s) and s not in spec
            )
            if len(spec) >= MAX_INDUSTRY_VALUES:
                break
        spec = spec[:MAX_INDUSTRY_VALUES]
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

    if not plan.buyer_roles:
        raise UnmappablePlan("plan has no buyer role to search for", report)
    roles, fallback_roles = expand_buyer_roles(plan.buyer_roles)
    for role in plan.buyer_roles:
        report.mapped.append({
            "plan": f"buyer_role:{role}",
            "field": "experience.employment_details.current.title",
            "value": roles or fallback_roles,
        })

    missing = []
    if not (countries or cities or headquarters):
        missing.append("geography")
    if not (industries or specialities):
        missing.append("industry")
    if missing:
        raise UnmappablePlan("plan needs at least one mapped " + " and one mapped ".join(missing), report)
    return CompanyQuery(
        conditions=conditions,
        role_terms=roles or fallback_roles,
        fallback_role_terms=fallback_roles,
    ), report
