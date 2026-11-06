"""Read a public seller site and extract stated facts. Does not invent ICP; founder still types who they sell to."""

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from services.core.errors import DomainError
from services.core.contracts.enums import ErrorCode
from services.core.source_fetch import FetchBlocked, FetchFailed, fetch_page
from services.models.client import ModelClient, ModelUnavailable, parse_json

ANALYZE_VERSION = "website_analysis.v1"
_PATHS = ("/", "/about", "/about-us", "/services", "/product", "/products")
_PLACEHOLDER = re.compile(r"^(n/?a|none|null|unknown|not (stated|specified|mentioned|available))\.?$", re.I)

EXTRACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "company_name": {"type": ["string", "null"]},
        "service": {"type": ["string", "null"]},
        "description": {"type": ["string", "null"]},
        "pricing": {"type": ["string", "null"]},
        "capacity": {"type": ["string", "null"]},
        "timezone": {"type": ["string", "null"]},
        "claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["company_name", "service", "description", "pricing", "capacity", "timezone", "claims"],
}

SYSTEM = (
    "Extract facts about this company only as stated on the supplied pages. "
    "Use null when the pages do not say it. Never guess pricing, people, emails or ICP. "
    "service is what they sell in under 8 words. description is one sentence. "
    "claims are up to 3 short factual statements quoted or closely paraphrased from the pages. "
    "Return JSON only."
)


def _origin(url: str) -> str:
    raw = url if re.match(r"^https?://", url, re.I) else f"https://{url}"
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if not host or "." not in host:
        raise DomainError(400, ErrorCode.VALIDATION_FAILED, "Enter a public company website, like yourcompany.com.")
    return f"https://{host}"


def _blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or bool(_PLACEHOLDER.match(value.strip()))
    if isinstance(value, list):
        return len(value) == 0
    return False


def _field(value: object, page: str | None) -> dict[str, Any]:
    if _blank(value):
        return {"value": None, "page": None}
    return {"value": value.strip() if isinstance(value, str) else value, "page": page}


def _read_pages(origin: str) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in _PATHS:
        url = f"{origin}{path}"
        if url in seen:
            continue
        seen.add(url)
        try:
            fetched = fetch_page(url)
        except (FetchBlocked, FetchFailed):
            continue
        text = fetched.text.strip()
        if not text:
            continue
        pages.append({"url": fetched.final_url, "text": text[:4000]})
        if len(pages) >= 3:
            break
    if not pages:
        raise DomainError(
            502,
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            f"We couldn't read {urlsplit(origin).hostname}. Try again or paste the facts in the brief.",
            retryable=True,
        )
    return pages


def analyze_website(url: str, *, client: ModelClient) -> dict[str, Any]:
    origin = _origin(url)
    pages = _read_pages(origin)
    packed = "\n\n".join(f"PAGE {p['url']}\n{p['text']}" for p in pages)[:12000]
    try:
        call = client.complete_json(
            role="fast",
            system=SYSTEM,
            user=packed,
            schema_name="website_extract",
            schema=EXTRACT_SCHEMA,
            prompt_version=ANALYZE_VERSION,
            attempt=1,
        )
        extracted = parse_json(call.content)
    except (ModelUnavailable, ValueError) as exc:
        raise DomainError(
            502,
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            f"The site was read but facts could not be extracted. {exc}",
            retryable=True,
        ) from exc

    home = pages[0]["url"]
    now = datetime.now(UTC)
    evidence = []
    proposed = []
    description = extracted.get("description")
    if not _blank(description):
        eid = uuid4()
        evidence.append(
            {
                "id": eid,
                "source_kind": "seller_website",
                "source_url": home,
                "provider_ref": "source_fetch",
                "field_path": "description",
                "excerpt": str(description)[:2000],
                "retrieved_at": now,
                "source_as_of": None,
                "content_sha256": hashlib.sha256(str(description).encode()).hexdigest(),
                "fact_status": "observed",
            }
        )
    for claim in (extracted.get("claims") or [])[:3]:
        if _blank(claim):
            continue
        eid = uuid4()
        evidence.append(
            {
                "id": eid,
                "source_kind": "seller_website",
                "source_url": home,
                "provider_ref": "source_fetch",
                "field_path": None,
                "excerpt": str(claim)[:2000],
                "retrieved_at": now,
                "source_as_of": None,
                "content_sha256": hashlib.sha256(str(claim).encode()).hexdigest(),
                "fact_status": "observed",
            }
        )
        proposed.append({"id": f"claim-{str(eid)[:8]}", "text": str(claim).strip(), "evidence_ids": [eid]})

    blank_list = {"value": None, "page": None}
    return {
        "url": f"{origin}/",
        "source": "fetched",
        "pages_read": [p["url"] for p in pages],
        "company_name": _field(extracted.get("company_name"), home),
        "service": _field(extracted.get("service"), home),
        "description": _field(extracted.get("description"), home),
        "pricing": _field(extracted.get("pricing"), home),
        "capacity": _field(extracted.get("capacity"), home),
        "customer_type": blank_list,
        "regions": blank_list,
        "buyer_roles": blank_list,
        "timeline": blank_list,
        "criteria": blank_list,
        "exclusions": blank_list,
        "timezone": _field(extracted.get("timezone"), home),
        "proposed_facts": proposed,
        "evidence": evidence,
    }
