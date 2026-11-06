import pytest

from services.adapters.crustdata.mapping import UnmappablePlan, expand_buyer_roles, map_plan, role_variants
from services.core.contracts.model_io import NormalizedPlan

# Suggestions mirror values observed live on 2026-11-06 (FIXTURE).
SUGGESTIONS = {
    ("locations.country", "india"): ["India", "British Indian Ocean Territory"],
    ("locations.country", "bengaluru"): [],
    ("city", "bengaluru"): ["Bengaluru", "Bengaluru Urban", "Bengaluru South"],
    ("basic_info.industries", "fintech"): [],
    ("basic_info.industries", "financial services"): ["Financial Services"],
    ("taxonomy.professional_network_specialities", "fintech"): ["Fintech", "Fintech Solutions", "Financial Technology (FinTech)", "Fintech Marketing"],
    ("funding.last_round_type", "series_a"): ["series_a"],
    ("funding.last_round_type", "series_b"): ["series_b"],
    ("funding.last_round_type", "series_z"): [],
    ("locations.country", "up"): [],
    ("locations.country", "uttar pradesh"): [],
    ("city", "up"): ["Upton", "Uppsala"],
    ("city", "uttar pradesh"): [],
    ("locations.headquarters", "uttar pradesh"): [
        "Noida, Uttar Pradesh, India", "Lucknow, Uttar Pradesh, India", "Uttar Pradesh, India",
    ],
    ("locations.headquarters", "up"): ["Upland, California, United States", "Uppsala, Uppsala County, Sweden"],
    ("locations.country", "us"): [],
    ("locations.country", "united states"): ["United States"],
    ("city", "us"): [],
    ("city", "united states"): [],
    ("basic_info.industries", "restaurant owners"): [],
    ("basic_info.industries", "restaurant"): [],
    ("basic_info.industries", "restaurants"): ["Restaurants"],
}


class FakeAutocomplete:
    def __init__(self):
        self.calls = []

    def autocomplete(self, field, query, limit=10):
        self.calls.append((field, query))
        return SUGGESTIONS.get((field, query.lower()), [])


def plan(**overrides):
    base = {
        "objective": "book_demo", "geography": ["Bengaluru"], "industries": ["fintech"],
        "company_rules": [], "buyer_roles": ["VP of Sales"], "exclusions": ["banks"], "missing_required_fields": [],
        "assumptions": [{"text": "mid-market means 50-1000 employees", "status": "hypothesis"}],
        "research_queries": [{"intent": "find fintech", "limit": 10}], "stop_conditions": [],
    }
    return NormalizedPlan.model_validate({**base, **overrides})


def fields_of(query):
    return [c.field for c in query.conditions]


def test_city_and_speciality_fallback_with_weak_match_report():
    query, report = map_plan(plan(), FakeAutocomplete())

    assert query.filters()["conditions"][0] == {"field": "locations.city", "type": "in", "value": ["Bengaluru"]}
    assert query.conditions[1].field == "taxonomy.professional_network_specialities"
    assert query.conditions[1].value == ["Fintech", "Fintech Solutions", "Financial Technology (FinTech)"]
    assert report.weak_matches[0]["plan"] == "industry:fintech"
    assert {u["plan"] for u in report.unmapped} >= {"exclusion:banks", "assumption:mid-market means 50-1000 employees"}


def test_country_industry_funding_and_headcount_rules():
    rules = [
        {"field": "funding_stage", "operator": "equals", "value": ["Series A", "Series B", "Series Z"], "must_have": True},
        {"field": "employee_count", "operator": "range", "value": [50, 500], "must_have": True},
    ]
    query, report = map_plan(plan(geography=["India"], industries=["Financial Services"], company_rules=rules), FakeAutocomplete())

    as_dicts = query.filters()["conditions"]
    assert {"field": "locations.country", "type": "in", "value": ["India"]} in as_dicts
    assert {"field": "basic_info.industries", "type": "in", "value": ["Financial Services"]} in as_dicts
    assert {"field": "funding.last_round_type", "type": "in", "value": ["series_a", "series_b"]} in as_dicts
    assert {"field": "headcount.total", "type": "=>", "value": 50.0} in as_dicts
    assert {"field": "headcount.total", "type": "=<", "value": 500.0} in as_dicts
    assert report.weak_matches == []


def test_funding_range_expands_along_round_ladder():
    rules = [{"field": "funding_stage", "operator": "range", "value": ["Series B", "Series D"], "must_have": True}]
    SUGGESTIONS[("funding.last_round_type", "series_c")] = ["series_c"]
    SUGGESTIONS[("funding.last_round_type", "series_d")] = ["series_d"]

    query, _ = map_plan(plan(company_rules=rules), FakeAutocomplete())

    assert {"field": "funding.last_round_type", "type": "in", "value": ["series_b", "series_c", "series_d"]} in query.filters()["conditions"]


def test_unknown_and_soft_rules_are_reported_not_filtered():
    rules = [
        {"field": "uses_salesforce; drop table", "operator": "equals", "value": "yes", "must_have": True},
        {"field": "employee_count", "operator": "range", "value": [50, 500], "must_have": False},
    ]
    query, report = map_plan(plan(company_rules=rules), FakeAutocomplete())

    assert set(fields_of(query)) == {"locations.city", "taxonomy.professional_network_specialities"}
    reasons = {u["plan"]: u["reason"] for u in report.unmapped}
    assert "no verified Crustdata mapping" in reasons["rule:uses_salesforce; drop table equals yes"]
    assert "not must_have" in reasons["rule:employee_count range [50, 500]"]


def test_model_text_never_becomes_a_filter_field():
    query, _ = map_plan(plan(company_rules=[{"field": "basic_info.name", "operator": "equals", "value": "Acme", "must_have": True}]), FakeAutocomplete())

    assert "basic_info.name" not in fields_of(query)


@pytest.mark.parametrize(
    "overrides",
    [{"geography": ["Atlantis"]}, {"industries": ["underwater basket weaving"]}, {"buyer_roles": []}],
)
def test_unmappable_plan_is_refused(overrides):
    with pytest.raises(UnmappablePlan):
        map_plan(plan(**overrides), FakeAutocomplete())


def test_role_variants_cover_abbreviations_only():
    assert role_variants("VP of Sales") == [["VP", "Sales"], ["Vice", "President", "Sales"]]
    assert role_variants("Vice President Sales") == [["Vice", "President", "Sales"], ["VP", "Sales"]]
    assert role_variants("Head of Sales") == [["Head", "Sales"]]


def test_persona_roles_expand_to_real_titles():
    primary, fallback = expand_buyer_roles(["Health Industry Leaders"])
    assert ["Health"] in primary
    assert ["CEO"] in primary
    assert fallback == []
    owners, owner_fallback = expand_buyer_roles(["Restaurant owners"])
    assert ["Owner"] in owners
    assert ["CEO"] in owners
    assert owner_fallback == []
    specific, _ = expand_buyer_roles(["VP of Sales"])
    assert ["VP", "Sales"] in specific
    assert ["CEO"] in specific


def test_customer_type_with_persona_maps_to_industry():
    query, report = map_plan(
        plan(geography=["India"], industries=["Restaurant owners"]), FakeAutocomplete()
    )
    assert {"field": "basic_info.industries", "type": "in", "value": ["Restaurants"]} in query.filters()["conditions"]
    assert any(row.get("value") == "Restaurants" for row in report.mapped)


def test_state_abbreviation_maps_via_headquarters_contains():
    query, report = map_plan(plan(geography=["UP"]), FakeAutocomplete())

    as_dicts = query.filters()["conditions"]
    assert {"field": "locations.headquarters", "type": "(.)", "value": "Uttar Pradesh"} in as_dicts
    assert {"field": "locations.country", "type": "in", "value": ["India"]} in as_dicts
    assert "Upton" not in str(as_dicts)
    assert "Uppsala" not in str(as_dicts)
    assert any(row["plan"] == "geography:UP" and row["field"] == "locations.headquarters" for row in report.mapped)


def test_country_abbreviation_expands_before_autocomplete():
    query, _ = map_plan(plan(geography=["US"]), FakeAutocomplete())

    assert {"field": "locations.country", "type": "in", "value": ["United States"]} in query.filters()["conditions"]
