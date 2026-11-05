"""Seller workspace: source evidence, approved profile (CAS on profile_version) and policy (CAS on config_version).

Approval is the business-authority boundary: only operator-approved facts that cite same-tenant evidence
become seller claims. Ingested website text stays untrusted evidence and is never auto-approved.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from .contracts.enums import ErrorCode
from .contracts.requests import PastedTextSource, PolicyUpdate, ProfileUpdate, WebsiteSource
from .contracts.views import EvidenceView, HealthReady, OrganizationView
from .errors import DomainError
from .source_fetch import FetchBlocked, FetchFailed, fetch_page

EXCERPT_MAX_CHARS = 60_000


def canonical_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def evidence_view(row: dict[str, Any]) -> EvidenceView:
    return EvidenceView(
        id=row["id"],
        source_kind=row["source_kind"],
        source_url=row["source_url"],
        provider_ref=row["provider_ref"],
        field_path=row["field_path"],
        excerpt=row["excerpt"],
        retrieved_at=row["retrieved_at"],
        source_as_of=row["source_as_of"],
        content_sha256=row["content_sha256"],
        fact_status=row["fact_status"],
    )


# ---------------------------------------------------------------- sources


def _existing_source(conn: psycopg.Connection, organization_id: UUID, key: str) -> dict | None:
    return conn.execute(
        "select * from evidence where organization_id = %s and entity_kind = 'seller_source' "
        "and metadata_json ->> 'request_key' = %s",
        (organization_id, key),
    ).fetchone()


def ingest_source(
    conn: psycopg.Connection,
    *,
    organization_id: UUID,
    user_id: UUID,
    idempotency_key: str,
    source: WebsiteSource | PastedTextSource,
    fetch=None,
) -> tuple[EvidenceView, bool]:
    """Create one immutable evidence row. Returns (evidence, replayed). Website fetch runs before the write."""
    request_hash = canonical_hash(source.model_dump(mode="json"))
    existing = _existing_source(conn, organization_id, idempotency_key)
    if existing is not None:
        if existing["metadata_json"].get("request_hash") != request_hash:
            raise DomainError(409, ErrorCode.CONFLICT, "Idempotency-Key was already used with a different source.")
        return evidence_view(existing), True

    now = datetime.now(UTC)
    metadata: dict[str, Any] = {"request_key": idempotency_key, "request_hash": request_hash, "added_by": str(user_id)}
    if isinstance(source, WebsiteSource):
        try:
            page = (fetch or fetch_page)(source.url)
        except FetchBlocked as exc:
            raise DomainError(
                422,
                ErrorCode.DOMAIN_INVALID,
                "Website fetch is not allowed for this URL; paste the seller text instead.",
                details={"reason": str(exc), "fallback": "pasted_text"},
            ) from exc
        except FetchFailed as exc:
            raise DomainError(
                503,
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Website could not be fetched; retry or paste the seller text instead.",
                retryable=True,
                details={"reason": str(exc), "fallback": "pasted_text"},
            ) from exc
        text = page.text
        source_kind, source_url = "seller_website", page.final_url
        metadata.update(
            {"requested_url": page.requested_url, "http_status": page.status, "content_type": page.content_type,
             "fetch_truncated": page.truncated, "untrusted": True}
        )
    else:
        text = source.text
        source_kind, source_url = "operator", None
        metadata.update({"title": source.title, "untrusted": True})

    excerpt = text[:EXCERPT_MAX_CHARS]
    metadata["excerpt_truncated"] = len(text) > EXCERPT_MAX_CHARS
    evidence_id = uuid4()
    row = conn.execute(
        """
        insert into evidence
          (id, organization_id, entity_kind, entity_id, source_kind, source_url, excerpt, retrieved_at,
           content_sha256, fact_status, metadata_json)
        values (%s, %s, 'seller_source', %s, %s, %s, %s, %s, %s, 'observed', %s)
        returning *
        """,
        (
            evidence_id, organization_id, organization_id, source_kind, source_url, excerpt, now,
            hashlib.sha256(text.encode()).hexdigest(), Jsonb(metadata),
        ),
    ).fetchone()
    return evidence_view(row), False


# ---------------------------------------------------------------- profile


def update_profile(
    conn: psycopg.Connection, *, organization_id: UUID, user_id: UUID, update: ProfileUpdate
) -> None:
    """Compare-and-swap on profile_version. Same approval_key+body replays; same key, other body is 409."""
    body = update.model_dump(mode="json", exclude={"expected_profile_version"})
    body_hash = canonical_hash(body)
    org = conn.execute(
        "select profile_version, last_profile_approval_key, last_profile_approval_hash from organizations "
        "where id = %s for update",
        (organization_id,),
    ).fetchone()
    if org["last_profile_approval_key"] == update.approval_key:
        if org["last_profile_approval_hash"] != body_hash:
            raise DomainError(409, ErrorCode.CONFLICT, "approval_key was already used with a different profile.")
        return
    if update.expected_profile_version != org["profile_version"]:
        raise DomainError(
            409,
            ErrorCode.CONFLICT,
            "Profile changed since it was loaded; reload and re-approve.",
            details={"current_profile_version": org["profile_version"]},
        )

    cited = sorted({eid for fact in update.approved_facts for eid in fact.evidence_ids})
    found = {
        r["id"]
        for r in conn.execute(
            "select id from evidence where organization_id = %s and id = any(%s) and fact_status <> 'conflicted'",
            (organization_id, cited),
        ).fetchall()
    }
    missing = [str(e) for e in cited if e not in found]
    if missing:
        raise DomainError(
            422,
            ErrorCode.DOMAIN_INVALID,
            "Approved facts must cite existing evidence in this workspace.",
            details={"unknown_evidence_ids": missing},
        )

    profile = {
        "approved_facts": [fact.model_dump(mode="json") for fact in update.approved_facts],
        "faq": [item.model_dump(mode="json") for item in update.faq],
        "forbidden_promises": update.forbidden_promises,
    }
    conn.execute(
        """
        update organizations
        set name = %s, website_url = %s, timezone = %s, approved_profile_json = %s,
            profile_version = profile_version + 1, approved_at = now(), approved_by = %s,
            last_profile_approval_key = %s, last_profile_approval_hash = %s
        where id = %s
        """,
        (
            update.name, update.website_url, update.timezone, Jsonb(profile), user_id,
            update.approval_key, body_hash, organization_id,
        ),
    )


# ---------------------------------------------------------------- policy


def update_policy(
    conn: psycopg.Connection, *, organization_id: UUID, idempotency_key: str, update: PolicyUpdate
) -> None:
    """Compare-and-swap on config_version; the latest request key/hash lives in policy_json for replay."""
    body = update.model_dump(mode="json", exclude={"expected_config_version"})
    body_hash = canonical_hash(body)
    org = conn.execute(
        "select config_version, policy_json from organizations where id = %s for update", (organization_id,)
    ).fetchone()
    last = org["policy_json"].get("last_request", {})
    if last.get("key") == idempotency_key:
        if last.get("hash") != body_hash:
            raise DomainError(409, ErrorCode.CONFLICT, "Idempotency-Key was already used with a different policy.")
        return
    if update.expected_config_version != org["config_version"]:
        raise DomainError(
            409,
            ErrorCode.CONFLICT,
            "Policy changed since it was loaded; reload and retry.",
            details={"current_config_version": org["config_version"]},
        )
    policy = {**body, "last_request": {"key": idempotency_key, "hash": body_hash}}
    conn.execute(
        "update organizations set policy_json = %s, config_version = config_version + 1 where id = %s",
        (Jsonb(policy), organization_id),
    )


# ---------------------------------------------------------------- view


def workspace_view(
    conn: psycopg.Connection, *, organization_id: UUID, role: str, worker: HealthReady
) -> OrganizationView:
    org = conn.execute(
        "select id, name, website_url, timezone, profile_version, approved_at, approved_profile_json, "
        "config_version, policy_json from organizations where id = %s",
        (organization_id,),
    ).fetchone()
    connections = conn.execute(
        "select purpose, status, account_email, granted_scopes, calendar_id from connections "
        "where organization_id = %s order by purpose",
        (organization_id,),
    ).fetchall()
    profile_json, policy = org["approved_profile_json"], org["policy_json"]
    profile = None
    if org["approved_at"] is not None and profile_json.get("approved_facts"):
        profile = {
            "approved_facts": profile_json.get("approved_facts", []),
            "faq": profile_json.get("faq", []),
            "forbidden_promises": profile_json.get("forbidden_promises", []),
        }
    return OrganizationView.model_validate(
        {
            "id": org["id"],
            "name": org["name"],
            "website_url": org["website_url"],
            "timezone": org["timezone"],
            "role": role,
            "profile_version": org["profile_version"],
            "approved_at": org["approved_at"],
            "profile": profile,
            "config_version": org["config_version"],
            "policy": {
                "simulation": policy.get("simulation") is True,
                "consented_recipients": policy.get("consented_recipients", []),
                "selected_calendar_id": policy.get("selected_calendar_id"),
                "working_hours": policy.get("working_hours"),
                "duration_minutes": policy.get("duration_minutes"),
                "limits": policy.get("limits"),
            },
            "connections": [dict(c) for c in connections],
            "worker": worker,
        }
    )
