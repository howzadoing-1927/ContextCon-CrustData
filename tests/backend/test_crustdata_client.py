"""CrustdataClient behavior against a fake transport (no network)."""

import json

import httpx2
import pytest

from services.adapters.crustdata.client import (
    API_VERSION,
    CrustdataClient,
    CrustdataDenied,
    CrustdataOutOfCredits,
    CrustdataUnavailable,
)

SECRET = "test-crustdata-key-SECRET-123"


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 2))
        self.now += seconds

    def time(self):
        return self.now


def make_client(responses, clock=None):
    seen = []
    queue = list(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        status, body, headers = queue.pop(0)
        return httpx2.Response(status, json=body, headers=headers)

    clock = clock or Clock()
    client = CrustdataClient(api_key=SECRET, transport=httpx2.MockTransport(handler), sleep=clock.sleep, clock=clock.time)
    return client, seen, clock


OK_HEADERS = {"x-request-id": "req-1", "x-credits-used": "0.33", "x-ratelimit-remaining": "29", "x-ratelimit-reset": "60"}


def test_sends_required_headers_and_records_receipt():
    client, seen, _ = make_client([(200, {"companies": [{"crustdata_company_id": 1}], "total_count": 1}, OK_HEADERS)])

    data, receipt = client.post("/company/search", {"filters": {}, "fields": ["crustdata_company_id"], "limit": 1}, count_key="companies")

    request = seen[0]
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    assert request.headers["x-api-version"] == API_VERSION == "2025-11-01"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content)["fields"] == ["crustdata_company_id"]
    assert receipt.request_id == "req-1" and receipt.credits_used == 0.33 and receipt.result_count == 1
    assert receipt.billable is True and len(receipt.request_sha256) == 64
    assert SECRET not in json.dumps(receipt.ledger())


def test_non_allowlisted_endpoint_is_refused():
    client, seen, _ = make_client([])

    with pytest.raises(ValueError):
        client.post("/person/contact/enrich", {})
    assert seen == []


def test_429_waits_reset_then_succeeds():
    client, seen, clock = make_client([
        (429, {"error": {"type": "rate_limit_error", "message": "slow down"}}, {"x-ratelimit-reset": "7", "x-ratelimit-remaining": "0"}),
        (200, {"suggestions": []}, OK_HEADERS),
    ])

    _, receipt = client.post("/company/search/autocomplete", {"field": "city", "query": "x"}, count_key="suggestions")

    assert len(seen) == 2 and receipt.attempts == 2
    assert any(7 <= s < 8.01 for s in clock.sleeps)


def test_pacing_waits_when_remaining_is_low():
    client, _, clock = make_client([
        (200, {"suggestions": []}, {"x-ratelimit-remaining": "1", "x-ratelimit-reset": "30"}),
        (200, {"suggestions": []}, OK_HEADERS),
    ])

    client.post("/company/search/autocomplete", {"field": "city", "query": "a"})
    client.post("/company/search/autocomplete", {"field": "city", "query": "b"})

    assert clock.sleeps and clock.sleeps[-1] == pytest.approx(30, abs=0.01)


@pytest.mark.parametrize(("status", "exc"), [(402, CrustdataOutOfCredits), (403, CrustdataDenied), (400, CrustdataDenied)])
def test_terminal_errors_are_not_retried(status, exc):
    client, seen, _ = make_client([(status, {"error": {"type": "x", "message": "no"}}, {"x-request-id": "req-9"})])

    with pytest.raises(exc) as info:
        client.post("/company/enrich", {"crustdata_company_ids": [1], "fields": ["basic_info"]})

    assert len(seen) == 1 and info.value.status == status and info.value.request_id == "req-9"
    assert SECRET not in str(info.value)


def test_5xx_retries_three_times_then_unavailable():
    client, seen, _ = make_client([(503, {"error": "down"}, {})] * 3)

    with pytest.raises(CrustdataUnavailable):
        client.post("/person/search", {"filters": {}, "fields": ["crustdata_person_id"], "limit": 1})
    assert len(seen) == 3
