"""Adapter tests on recorded FIXTURE responses shaped like the live 2025-11-01 responses observed on 2026-11-06."""

import json

import httpx2
import pytest

from services.adapters.crustdata.adapter import (
    COMPANY_SEARCH_FIELDS,
    PERSON_SEARCH_FIELDS,
    CrustdataResearch,
    company_ref,
)
from services.adapters.crustdata.client import CrustdataClient
from services.adapters.crustdata.mapping import CompanyQuery, Condition

COMPANY_SEARCH = {
    "companies": [
        {"crustdata_company_id": 5878, "basic_info": {"name": "Happay", "primary_domain": "happay.in", "employee_count_range": "201-500"},
         "locations": {"country": "IND", "city": "Bengaluru"}},
        {"crustdata_company_id": 6636, "basic_info": {"name": "propelld", "primary_domain": "propelld.com", "employee_count_range": None},
         "locations": {"country": "IND", "city": "Bengaluru"}},
    ],
    "next_cursor": "abc",
    "total_count": 7,
}


def person(pid, company_id, title, extra_role=None):
    roles = [{
        "crustdata_company_id": company_id, "name": "Happay", "title": title, "is_default": True, "seniority_level": "Vice President",
        "function_category": "Sales", "start_date": "2024-01-01T00:00:00", "company_professional_network_profile_url": "https://example.invalid/c",
        "business_email_verified": True, "company_website": "http://happay.in",
    }]
    if extra_role:
        roles.append(extra_role)
    return {"crustdata_person_id": pid, "basic_profile": {"name": "Asha Rao", "current_title": title},
            "experience": {"employment_details": {"current": roles}}}


ENRICH = [{
    "matched_on": "5878", "match_type": "crustdata_company_id",
    "matches": [{"confidence_score": 1.0, "company_data": {
        "crustdata_company_id": 5878,
        "basic_info": {"name": "Happay", "primary_domain": "happay.in", "employee_count_range": "201-500", "year_founded": 2012,
                       "description": "x" * 900},
        "headcount": {"total": 226},
        "funding": {"last_round_type": "series_b", "last_fundraise_date": "2020-01-01", "total_investment_usd": None},
        "locations": {"country": "IND", "headquarters": "Bellandur, Karnataka, India"},
        "taxonomy": {"professional_network_industry": "Software Development"},
    }}],
}]


def research_with(routes):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        status, payload = routes[request.url.path](body)
        return httpx2.Response(status, json=payload, headers={"x-request-id": f"req-{len(requests)}", "x-credits-used": "0.23"})

    client = CrustdataClient(api_key="k", transport=httpx2.MockTransport(handler), sleep=lambda s: None)
    return CrustdataResearch(client), requests


QUERY = CompanyQuery(conditions=[Condition("locations.city", "in", ["Bengaluru"])], role_terms=[["VP", "Sales"], ["Vice", "President", "Sales"]])


def test_search_companies_sends_explicit_fields_and_returns_refs():
    research, requests = research_with({"/company/search": lambda b: (200, COMPANY_SEARCH)})

    result = research.search_companies(QUERY, limit=10)

    path, body = requests[0]
    assert body["fields"] == COMPANY_SEARCH_FIELDS and body["limit"] == 10
    assert body["filters"] == {"op": "and", "conditions": [{"field": "locations.city", "type": "in", "value": ["Bengaluru"]}]}
    assert [c.ref for c in result.companies] == ["crustdata:company:5878", "crustdata:company:6636"]
    assert result.total_count == 7 and result.has_more is True
    propelld = result.companies[1]
    assert "crustdata:/company/search#basic_info.employee_count_range" not in {o.field_path for o in propelld.observations}


def test_find_people_supported_only_when_employer_id_matches():
    research, requests = research_with({"/person/search": lambda b: (200, {"profiles": [person(11, 5878, "VP Sales")], "remarks": []})})

    result = research.find_people(company_ref(5878), QUERY.role_terms)

    _, body = requests[0]
    assert body["fields"] == PERSON_SEARCH_FIELDS and body["explain"] is True
    assert body["filters"]["conditions"][0] == {"field": "experience.employment_details.current.company_id", "type": "=", "value": 5878}
    assert body["filters"]["conditions"][1]["op"] == "or"
    assert result.status == "supported" and result.person.ref == "crustdata:person:11"
    paths = {o.field_path for o in result.person.observations}
    assert "crustdata:/person/search#experience.employment_details.current[crustdata_company_id=5878].title" in paths


def test_find_people_conflicted_when_returned_employer_differs():
    research, _ = research_with({"/person/search": lambda b: (200, {"profiles": [person(11, 9999, "VP Sales")], "remarks": []})})

    result = research.find_people(company_ref(5878), QUERY.role_terms)

    assert result.status == "conflicted" and result.person is None


def test_find_people_conflicted_when_title_does_not_match():
    research, _ = research_with({"/person/search": lambda b: (200, {"profiles": [person(11, 5878, "Sales Executive")], "remarks": []})})

    assert research.find_people(company_ref(5878), QUERY.role_terms).status == "conflicted"


def test_find_people_unknown_keeps_explain_remarks():
    remarks = [{"code": "condition_eliminates_all", "path": "filters.conditions[1]", "matches_without": 195, "message": "x"}]
    research, _ = research_with({"/person/search": lambda b: (200, {"profiles": [], "remarks": remarks})})

    result = research.find_people(company_ref(5878), QUERY.role_terms)

    assert result.status == "unknown" and result.person is None
    assert result.remarks == [{"code": "condition_eliminates_all", "path": "filters.conditions[1]", "matches_without": 195}]


def test_person_observations_never_include_contact_or_profile_urls():
    research, _ = research_with({"/person/search": lambda b: (200, {"profiles": [person(11, 5878, "VP Sales")], "remarks": []})})

    result = research.find_people(company_ref(5878), QUERY.role_terms)

    blob = json.dumps([o.value for o in result.person.observations]) + json.dumps([o.field_path for o in result.person.observations])
    assert "profile_url" not in blob and "business_email" not in blob and "@" not in blob and "http" not in blob


def test_enrich_identity_reports_missing_fields_and_bounds_description():
    research, requests = research_with({"/company/enrich": lambda b: (200, ENRICH)})

    result = research.enrich_identity(company_ref(5878))

    _, body = requests[0]
    assert body == {"crustdata_company_ids": [5878], "fields": ["basic_info", "headcount", "funding", "locations", "taxonomy"]}
    assert "funding.total_investment_usd" in result.missing_fields
    values = {o.field_path.split("#")[1]: o.value for o in result.observations}
    assert values["funding.last_round_type"] == "series_b" and values["headcount.total"] == 226
    assert len(values["basic_info.description"]) == 500


def test_enrich_identity_with_no_match_reports_everything_missing():
    research, _ = research_with({"/company/enrich": lambda b: (200, [{"matched_on": "5878", "matches": []}])})

    result = research.enrich_identity(company_ref(5878))

    assert result.observations == [] and "basic_info.name" in result.missing_fields
