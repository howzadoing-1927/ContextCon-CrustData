"""Display-only business-email lookup for the selected prospect (POST /person/enrich, contact.business_emails).

The result is shown in the UI as "found". It is never evidence, never given to the drafter, and never a recipient:
outbound email always goes to the campaign's consented test inbox.
"""

from datetime import UTC, datetime
from typing import Any

from .client import CrustdataClient, CrustdataError

FIELDS = ["crustdata_person_id", "contact.business_emails"]


def _emails(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        found = [e for e in node.get("business_emails") or [] if isinstance(e, dict) and e.get("email")]
        for value in node.values():
            found += _emails(value)
        return found
    if isinstance(node, list):
        return [e for item in node for e in _emails(item)]
    return []


def lookup_business_email(client: CrustdataClient, person_ref: str) -> dict[str, Any]:
    """`person_ref` is `crustdata:person:<id>`. Returns a display record; never raises for provider errors."""
    looked_up_at = datetime.now(UTC).isoformat()
    try:
        person_id = int(person_ref.rsplit(":", 1)[-1])
        data, receipt = client.post("/person/enrich", {"crustdata_person_ids": [person_id], "fields": FIELDS})
    except (ValueError, CrustdataError) as exc:
        return {"email": None, "status": "lookup_failed", "detail": str(exc)[:200], "source": "crustdata:/person/enrich",
                "looked_up_at": looked_up_at}
    emails = _emails(data)
    best = next((e for e in emails if str(e.get("status", "")).lower() in ("valid", "verified")), emails[0] if emails else None)
    return {"email": best["email"].strip().lower() if best else None, "status": (best or {}).get("status") or "not_found",
            "source": "crustdata:/person/enrich", "credits_used": receipt.credits_used, "request_id": receipt.request_id,
            "looked_up_at": looked_up_at}
