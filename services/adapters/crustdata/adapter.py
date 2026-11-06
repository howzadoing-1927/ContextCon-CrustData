"""Crustdata research adapter implementing the doc 03 contracts:
search_companies, find_people and enrich_identity. Every method sends an explicit `fields` list and returns its
provider receipts. Person results never request or keep contact data or profile URLs.
"""

from dataclasses import dataclass, field
from typing import Any

from .client import CrustdataClient, ProviderReceipt, sha256_json
from .mapping import AUTOCOMPLETE, CompanyQuery

COMPANY_SEARCH_FIELDS = [
    "crustdata_company_id",
    "basic_info.name",
    "basic_info.primary_domain",
    "basic_info.employee_count_range",
    "locations.country",
    "locations.city",
]
PERSON_SEARCH_FIELDS = [
    "crustdata_person_id",
    "basic_profile.name",
    "basic_profile.current_title",
    "experience.employment_details.current",
]
CURRENT_ROLE_KEEP = ("crustdata_company_id", "name", "title", "is_default", "seniority_level", "function_category", "start_date")
ENRICH_FIELDS = ["basic_info", "headcount", "funding", "locations", "taxonomy"]
ENRICH_OBSERVED = {
    "basic_info.name": ("basic_info", "name"),
    "basic_info.primary_domain": ("basic_info", "primary_domain"),
    "basic_info.employee_count_range": ("basic_info", "employee_count_range"),
    "basic_info.year_founded": ("basic_info", "year_founded"),
    "basic_info.description": ("basic_info", "description"),
    "headcount.total": ("headcount", "total"),
    "funding.last_round_type": ("funding", "last_round_type"),
    "funding.last_fundraise_date": ("funding", "last_fundraise_date"),
    "funding.total_investment_usd": ("funding", "total_investment_usd"),
    "locations.country": ("locations", "country"),
    "locations.headquarters": ("locations", "headquarters"),
    "taxonomy.professional_network_industry": ("taxonomy", "professional_network_industry"),
    "taxonomy.professional_network_specialities": ("taxonomy", "professional_network_specialities"),
}
DESCRIPTION_MAX = 500


def company_ref(company_id: int | str) -> str:
    return f"crustdata:company:{company_id}"


def person_ref(person_id: int | str) -> str:
    return f"crustdata:person:{person_id}"


def provider_id(ref: str) -> int:
    """Crustdata's API takes integer IDs; our refs stay opaque strings everywhere else."""
    return int(ref.rsplit(":", 1)[1])


@dataclass
class Observation:
    field_path: str
    value: Any
    record_sha256: str
    receipt: ProviderReceipt


@dataclass
class CompanyCandidate:
    ref: str
    name: str | None
    domain: str | None
    observations: list[Observation]


@dataclass
class CompanySearchResult:
    companies: list[CompanyCandidate]
    total_count: int | None
    has_more: bool
    receipt: ProviderReceipt


@dataclass
class PersonMatch:
    ref: str
    name: str | None
    title: str | None
    observations: list[Observation]


@dataclass
class PeopleResult:
    company_ref: str
    status: str  # supported | conflicted | unknown
    person: PersonMatch | None
    reason: str
    remarks: list[dict[str, Any]]
    receipt: ProviderReceipt


@dataclass
class EnrichResult:
    company_ref: str
    observations: list[Observation]
    missing_fields: list[str]
    receipt: ProviderReceipt


def _dig(record: dict, *keys: str) -> Any:
    value: Any = record
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _title_matches(title: str | None, terms: list[str]) -> bool:
    words = (title or "").lower()
    return bool(terms) and all(term.lower() in words for term in terms)


@dataclass
class CrustdataResearch:
    client: CrustdataClient
    receipts: list[ProviderReceipt] = field(default_factory=list)

    def _post(self, endpoint: str, body: dict, count_key: str | None = None) -> tuple[Any, ProviderReceipt]:
        data, receipt = self.client.post(endpoint, body, count_key=count_key)
        self.receipts.append(receipt)
        return data, receipt

    def autocomplete(self, field: str, query: str, limit: int = 10) -> list[str]:
        data, _ = self._post(AUTOCOMPLETE, {"field": field, "query": query, "limit": limit}, count_key="suggestions")
        return [s["value"] for s in data.get("suggestions", []) if isinstance(s, dict) and s.get("value")]

    def search_companies(self, query: CompanyQuery, limit: int) -> CompanySearchResult:
        body = {
            "filters": query.filters(),
            "fields": COMPANY_SEARCH_FIELDS,
            "sorts": [{"field": "crustdata_company_id", "order": "asc"}],
            "limit": limit,
        }
        data, receipt = self._post("/company/search", body, count_key="companies")
        companies = []
        for record in (data.get("companies") or [])[:limit]:
            cid = record.get("crustdata_company_id")
            if cid is None:
                continue
            record_sha = sha256_json(record)
            observations = [
                Observation(f"crustdata:/company/search#{path}", value, record_sha, receipt)
                for path, value in (
                    ("basic_info.name", _dig(record, "basic_info", "name")),
                    ("basic_info.primary_domain", _dig(record, "basic_info", "primary_domain")),
                    ("basic_info.employee_count_range", _dig(record, "basic_info", "employee_count_range")),
                    ("locations.country", _dig(record, "locations", "country")),
                    ("locations.city", _dig(record, "locations", "city")),
                )
                if value not in (None, "", [])
            ]
            companies.append(
                CompanyCandidate(company_ref(cid), _dig(record, "basic_info", "name"), _dig(record, "basic_info", "primary_domain"), observations)
            )
        return CompanySearchResult(companies, data.get("total_count"), bool(data.get("next_cursor")), receipt)

    def find_people(self, ref: str, roles: list[list[str]], limit: int = 3) -> PeopleResult:
        cid = provider_id(ref)
        conditions = [{"field": "experience.employment_details.current.company_id", "type": "=", "value": cid}]
        if roles:
            role_conditions = [
                {"field": "experience.employment_details.current.title", "type": "(.)", "value": " ".join(terms)} for terms in roles
            ]
            conditions.append(role_conditions[0] if len(role_conditions) == 1 else {"op": "or", "conditions": role_conditions})
        body = {"filters": {"op": "and", "conditions": conditions}, "fields": PERSON_SEARCH_FIELDS, "limit": limit, "explain": True}
        data, receipt = self._post("/person/search", body, count_key="profiles")
        profiles = data.get("profiles") or []
        remarks = [{k: r.get(k) for k in ("code", "path", "matches_without")} for r in data.get("remarks") or [] if isinstance(r, dict)]
        if not profiles:
            return PeopleResult(ref, "unknown", None, "no current employee with a matching title returned", remarks, receipt)

        for profile in profiles:
            pid = profile.get("crustdata_person_id")
            roles_now = _dig(profile, "experience", "employment_details", "current") or []
            for role in roles_now:
                if not isinstance(role, dict) or role.get("crustdata_company_id") != cid:
                    continue
                if pid is None:
                    continue
                if roles and not any(_title_matches(role.get("title"), terms) for terms in roles):
                    continue
                kept = {k: role.get(k) for k in CURRENT_ROLE_KEEP}
                record_sha = sha256_json({"crustdata_person_id": pid, "current_role": kept})
                path = "crustdata:/person/search#experience.employment_details.current"
                observations = [
                    Observation(f"{path}[crustdata_company_id={cid}].crustdata_company_id", cid, record_sha, receipt),
                    Observation(f"{path}[crustdata_company_id={cid}].title", role.get("title"), record_sha, receipt),
                    Observation(f"{path}[crustdata_company_id={cid}].is_default", role.get("is_default"), record_sha, receipt),
                    Observation("crustdata:/person/search#basic_profile.name", _dig(profile, "basic_profile", "name"), record_sha, receipt),
                ]
                if role.get("seniority_level"):
                    observations.append(Observation(f"{path}[crustdata_company_id={cid}].seniority_level", role["seniority_level"], record_sha, receipt))
                return PeopleResult(
                    ref,
                    "supported",
                    PersonMatch(person_ref(pid), _dig(profile, "basic_profile", "name"), role.get("title"), observations),
                    "current role at this company ID with a matching title",
                    remarks,
                    receipt,
                )
        return PeopleResult(
            ref, "conflicted", None,
            "profiles returned but none has a current role at this company ID with a matching title", remarks, receipt,
        )

    def enrich_identity(self, ref: str) -> EnrichResult:
        cid = provider_id(ref)
        data, receipt = self._post("/company/enrich", {"crustdata_company_ids": [cid], "fields": ENRICH_FIELDS})
        entry = data[0] if isinstance(data, list) and data else {}
        matches = entry.get("matches") or []
        record = (matches[0].get("company_data") or {}) if matches else {}
        if record.get("crustdata_company_id") not in (None, cid):
            record = {}
        record_sha = sha256_json(record)
        observations, missing = [], []
        for path, keys in ENRICH_OBSERVED.items():
            value = _dig(record, *keys)
            if value in (None, "", []):
                missing.append(path)
                continue
            if path == "basic_info.description" and isinstance(value, str):
                value = value[:DESCRIPTION_MAX]
            observations.append(Observation(f"crustdata:/company/enrich#{path}", value, record_sha, receipt))
        return EnrichResult(ref, observations, missing, receipt)
