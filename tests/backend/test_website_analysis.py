from services.core.source_fetch import FetchedPage
from services.core.website_analysis import analyze_website
from tests.backend.test_normalize import FakeClient


def test_toastinc_brief_is_seeded_without_fetch():
    result = analyze_website("https://www.toastinc.in", client=FakeClient({}))

    assert result["service"]["value"] == "Restaurant management"
    assert result["capacity"]["value"] == "100"
    assert result["description"]["value"] == "Comprehensive restaurant management partner"
    assert result["pricing"]["value"] == "To be discussed in meeting"
    assert result["customer_type"]["value"] == "Restaurant owners"
    assert result["regions"]["value"] == ["India"]
    assert result["buyer_roles"]["value"] == ["Restaurant owners"]
    assert result["criteria"]["value"] == ["Must own a restaurant"]


def test_analyze_website_fills_stated_icp(monkeypatch):
    page = FetchedPage(
        requested_url="https://example-schools.test/",
        final_url="https://example-schools.test/",
        status=200,
        content_type="text/html",
        text="We help K-12 schools in India. Principals book a demo.",
        truncated=False,
    )
    monkeypatch.setattr("services.core.website_analysis.fetch_page", lambda url: page)

    extracted = {
        "company_name": "Example Schools",
        "service": "Board exam prep",
        "description": "Helps K-12 schools in India prepare for board exams.",
        "pricing": None,
        "capacity": None,
        "timezone": "Asia/Kolkata",
        "customer_type": "K-12 schools",
        "regions": ["India"],
        "buyer_roles": ["Principal"],
        "timeline": None,
        "criteria": ["Has an academic coordinator"],
        "exclusions": [],
        "claims": ["Helps K-12 schools prepare for board exams."],
    }

    result = analyze_website("https://example-schools.test", client=FakeClient(extracted))

    assert result["customer_type"] == {"value": "K-12 schools", "page": page.final_url}
    assert result["regions"] == {"value": ["India"], "page": page.final_url}
    assert result["buyer_roles"] == {"value": ["Principal"], "page": page.final_url}
    assert result["criteria"] == {"value": ["Has an academic coordinator"], "page": page.final_url}
    assert result["exclusions"] == {"value": None, "page": None}
