"""Thin Crustdata REST client (API version 2025-11-01). See MAPPING.md for verified endpoint facts.

- Allowlisted endpoints only; every request carries Authorization, content-type and x-api-version.
- Paces each endpoint from x-ratelimit-* headers; 429 waits x-ratelimit-reset (+jitter), 5xx backs off;
  402 (credits) and 403 (permission/field) are terminal and never retried.
- Every successful call yields a ProviderReceipt; the API key never appears in receipts or errors.
"""

import hashlib
import json
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import httpx2

API_VERSION = "2025-11-01"
DEFAULT_BASE_URL = "https://api.crustdata.com"
MAX_ATTEMPTS = 3

# endpoint -> (default RPM, billable). Billable endpoints count against max_research_calls.
ENDPOINTS: dict[str, tuple[int, bool]] = {
    "/company/search/autocomplete": (300, False),
    "/company/identify": (30, False),
    "/company/search": (30, True),
    "/company/enrich": (15, True),
    "/person/search": (30, True),
    "/person/enrich": (15, True),
}


class CrustdataError(Exception):
    def __init__(self, message: str, *, endpoint: str, status: int | None, request_id: str | None = None) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.status = status
        self.request_id = request_id


class CrustdataUnavailable(CrustdataError):
    """Transient: network, timeout, 429 or 5xx after retries."""


class CrustdataDenied(CrustdataError):
    """Terminal: 401/403 endpoint or field not permitted, or 400 invalid request."""


class CrustdataOutOfCredits(CrustdataError):
    """Terminal: 402 insufficient credits."""


def sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass
class ProviderReceipt:
    endpoint: str
    api_version: str
    status: int
    request_id: str | None
    credits_used: float | None
    result_count: int | None
    request_sha256: str
    response_sha256: str
    billable: bool
    attempts: int
    latency_ms: int

    def ledger(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _Pace:
    min_interval: float
    next_allowed: float = 0.0


@dataclass
class CrustdataClient:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 20.0
    transport: httpx2.BaseTransport | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    receipts: list[ProviderReceipt] = field(default_factory=list)
    _paces: dict[str, _Pace] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._http = httpx2.Client(base_url=self.base_url.rstrip("/"), timeout=self.timeout, transport=self.transport)

    def close(self) -> None:
        self._http.close()

    def _headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
            "x-api-version": API_VERSION,
        }

    def _pace(self, endpoint: str) -> _Pace:
        if endpoint not in self._paces:
            self._paces[endpoint] = _Pace(min_interval=60.0 / ENDPOINTS[endpoint][0])
        return self._paces[endpoint]

    def _wait_turn(self, endpoint: str) -> None:
        pace = self._pace(endpoint)
        delay = pace.next_allowed - self.clock()
        if delay > 0:
            self.sleep(delay)

    def _after_response(self, endpoint: str, response: httpx2.Response) -> None:
        pace = self._pace(endpoint)
        now = self.clock()
        pace.next_allowed = now + pace.min_interval
        remaining = _int_header(response, "x-ratelimit-remaining")
        reset = _int_header(response, "x-ratelimit-reset")
        if remaining is not None and remaining <= 1 and reset:
            pace.next_allowed = max(pace.next_allowed, now + reset)

    def post(self, endpoint: str, body: dict[str, Any], *, count_key: str | None = None) -> tuple[Any, ProviderReceipt]:
        if endpoint not in ENDPOINTS:
            raise ValueError(f"endpoint not allowlisted: {endpoint}")
        request_sha = sha256_json({"endpoint": endpoint, "body": body})
        last_status: int | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._wait_turn(endpoint)
            started = self.clock()
            try:
                response = self._http.post(endpoint, json=body, headers=self._headers())
            except httpx2.HTTPError as exc:
                if attempt == MAX_ATTEMPTS:
                    raise CrustdataUnavailable(f"network error: {type(exc).__name__}", endpoint=endpoint, status=None) from exc
                self.sleep(min(2 ** attempt, 10) + random.uniform(0, 1))
                continue
            self._after_response(endpoint, response)
            last_status = response.status_code
            request_id = response.headers.get("x-request-id")
            if response.status_code == 200:
                data = response.json()
                count = len(data) if isinstance(data, list) else (len(data.get(count_key) or []) if count_key else None)
                receipt = ProviderReceipt(
                    endpoint=endpoint,
                    api_version=API_VERSION,
                    status=200,
                    request_id=request_id,
                    credits_used=_float_header(response, "x-credits-used"),
                    result_count=count,
                    request_sha256=request_sha,
                    response_sha256=sha256_json(data),
                    billable=ENDPOINTS[endpoint][1],
                    attempts=attempt,
                    latency_ms=int((self.clock() - started) * 1000),
                )
                self.receipts.append(receipt)
                return data, receipt
            message = _error_message(response)
            if response.status_code == 402:
                raise CrustdataOutOfCredits(message, endpoint=endpoint, status=402, request_id=request_id)
            if response.status_code in (400, 401, 403, 404):
                raise CrustdataDenied(message, endpoint=endpoint, status=response.status_code, request_id=request_id)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == MAX_ATTEMPTS:
                    break
                reset = _int_header(response, "x-ratelimit-reset") if response.status_code == 429 else None
                self.sleep((reset if reset is not None else min(2 ** attempt, 10)) + random.uniform(0, 1))
                continue
            raise CrustdataDenied(message, endpoint=endpoint, status=response.status_code, request_id=request_id)
        raise CrustdataUnavailable(f"gave up after {MAX_ATTEMPTS} attempts", endpoint=endpoint, status=last_status)


def _int_header(response: httpx2.Response, name: str) -> int | None:
    try:
        return int(float(response.headers.get(name, "")))
    except ValueError:
        return None


def _float_header(response: httpx2.Response, name: str) -> float | None:
    try:
        return float(response.headers.get(name, ""))
    except ValueError:
        return None


def _error_message(response: httpx2.Response) -> str:
    """Provider error text, bounded. Provider messages never echo our key, but cap length anyway."""
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        text = f"{error.get('type', 'error')}: {error.get('message', '')}"
    else:
        text = str(body.get("message") or body.get("description") or error or body)
    return text[:400]
