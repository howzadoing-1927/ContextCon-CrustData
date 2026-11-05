"""research task: NormalizedPlan -> Crustdata discovery -> person match -> evidence-backed prospects.

Provider calls happen outside DB locks with lease heartbeats between them. Results, evidence, usage, the ledger
entry, the next task and task completion commit in ONE fenced transaction. Identity is never invented: a company
without a supported current-employee match is stored as needs_evidence with no person.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from services.adapters.crustdata.adapter import (
    CompanyCandidate,
    EnrichResult,
    Observation,
    PeopleResult,
)
from services.adapters.crustdata.client import (
    CrustdataDenied,
    CrustdataError,
    CrustdataOutOfCredits,
    CrustdataUnavailable,
    ProviderReceipt,
    sha256_json,
)
from services.adapters.crustdata.mapping import CompanyQuery, MappingReport, UnmappablePlan, map_plan
from services.core.contracts.model_io import NormalizedPlan
from services.core.contracts.version import CONTRACT_VERSION

from . import queue

HARD_MAX_DISCOVERED = 10
HARD_MAX_ENRICHED = 3
LEASE_SECONDS = 120
UNAVAILABLE_RETRY_SECONDS = 60
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


class Research(Protocol):
    receipts: list[ProviderReceipt]

    def autocomplete(self, field: str, query: str, limit: int = 10) -> list[str]: ...
    def search_companies(self, query: CompanyQuery, limit: int): ...
    def find_people(self, ref: str, roles: list[list[str]], limit: int = 3) -> PeopleResult: ...
    def enrich_identity(self, ref: str) -> EnrichResult: ...


@dataclass
class Examined:
    company: CompanyCandidate
    people: PeopleResult
    enrich: EnrichResult | None = None


@dataclass
class RunResult:
    report: MappingReport | None = None
    discovered: list[CompanyCandidate] = field(default_factory=list)
    examined: list[Examined] = field(default_factory=list)
    total_count: int | None = None
    error: CrustdataError | UnmappablePlan | None = None
    budget_stop: str | None = None


def _billable(receipts: list[ProviderReceipt]) -> int:
    return sum(1 for r in receipts if r.billable)


def run_research(
    research: Research,
    plan: NormalizedPlan,
    *,
    max_discovered: int,
    max_enriched: int,
    research_budget: int,
    beat: Callable[[], None],
) -> RunResult:
    """Pure provider orchestration (no DB). Stops at caps and never exceeds the billable-call budget."""
    result = RunResult()
    try:
        query, result.report = map_plan(plan, research)
        if research_budget < 2:
            result.budget_stop = "research-call budget cannot cover one company search and one person search"
            return result
        beat()
        search = research.search_companies(query, limit=max_discovered)
        result.discovered, result.total_count = search.companies[:max_discovered], search.total_count
        matched = 0
        for company in result.discovered:
            # keep room for this person search and, if it matches, one enrich
            if _billable(research.receipts) + 2 > research_budget:
                result.budget_stop = "stopped person search to stay within max_research_calls"
                break
            if matched >= max_enriched:
                break
            beat()
            people = research.find_people(company.ref, query.role_terms)
            examined = Examined(company, people)
            result.examined.append(examined)
            if people.status == "supported":
                beat()
                examined.enrich = research.enrich_identity(company.ref)
                matched += 1
    except (CrustdataError, UnmappablePlan) as exc:
        result.error = exc
        if isinstance(exc, UnmappablePlan):
            result.report = exc.report
    return result


# ---------------------------------------------------------------- persistence


def _safe(value: Any) -> bool:
    return not (isinstance(value, str) and _EMAIL.search(value))


def _evidence_row(
    conn: psycopg.Connection, lease: queue.Lease, prospect_id: UUID, entity_kind: str, provider_ref: str, obs: Observation
) -> UUID | None:
    if not _safe(obs.value):
        return None
    evidence_id = uuid4()
    receipt = obs.receipt
    conn.execute(
        """
        insert into evidence (id, organization_id, campaign_id, prospect_id, entity_kind, entity_id, source_kind,
                              source_url, provider_ref, field_path, excerpt, retrieved_at, content_sha256, fact_status,
                              metadata_json)
        values (%s, %s, %s, %s, %s, %s, 'crustdata', null, %s, %s, %s, now(), %s, 'observed', %s)
        """,
        (
            evidence_id, lease.organization_id, lease.campaign_id, prospect_id, entity_kind, prospect_id,
            provider_ref, obs.field_path, json.dumps(obs.value, separators=(",", ":"), default=str)[:2000],
            obs.record_sha256,
            Jsonb({
                "endpoint": receipt.endpoint, "api_version": receipt.api_version, "request_id": receipt.request_id,
                "request_sha256": receipt.request_sha256, "response_sha256": receipt.response_sha256,
                "credits_used": receipt.credits_used,
            }),
        ),
    )
    return evidence_id


def _persist_prospect(conn: psycopg.Connection, lease: queue.Lease, item: Examined) -> dict[str, Any]:
    company, people = item.company, item.people
    existing = conn.execute(
        "select id from prospects where organization_id = %s and campaign_id = %s and canonical_company_ref = %s",
        (lease.organization_id, lease.campaign_id, company.ref),
    ).fetchone()
    if existing:
        return {"prospect_id": str(existing["id"]), "company_ref": company.ref, "status": "duplicate_skipped"}

    supported = people.status == "supported" and people.person is not None
    prospect_id = uuid4()
    conn.execute(
        """
        insert into prospects (id, organization_id, campaign_id, canonical_company_ref, canonical_person_ref,
                               identity_json, status)
        values (%s, %s, %s, %s, %s, '{}'::jsonb, %s)
        """,
        (prospect_id, lease.organization_id, lease.campaign_id, company.ref,
         people.person.ref if supported else None, "researching" if supported else "needs_evidence"),
    )
    company_evidence = [
        e for e in (_evidence_row(conn, lease, prospect_id, "company", company.ref, o) for o in company.observations) if e
    ]
    relationship_evidence: list[UUID] = []
    if supported:
        relationship_evidence = [
            e for e in (_evidence_row(conn, lease, prospect_id, "person", people.person.ref, o) for o in people.person.observations) if e
        ]
    enrich_evidence: list[UUID] = []
    if item.enrich:
        enrich_evidence = [
            e for e in (_evidence_row(conn, lease, prospect_id, "company", company.ref, o) for o in item.enrich.observations) if e
        ]
    identity = {
        "company": {"name": company.name, "domain": company.domain, "evidence_ids": [str(e) for e in company_evidence + enrich_evidence]},
        "person": {"name": people.person.name, "title": people.person.title} if supported else None,
        "relationship": {
            "status": people.status,
            "reason": people.reason,
            "evidence_ids": [str(e) for e in relationship_evidence],
            "remarks": people.remarks,
        },
        "missing_fields": item.enrich.missing_fields if item.enrich else None,
        "source": "crustdata",
    }
    conn.execute(
        "update prospects set identity_json = %s where organization_id = %s and id = %s",
        (Jsonb(identity), lease.organization_id, prospect_id),
    )
    return {
        "prospect_id": str(prospect_id),
        "company_ref": company.ref,
        "person_ref": people.person.ref if supported else None,
        "relationship": people.status,
        "status": "researching" if supported else "needs_evidence",
        "evidence_count": len(company_evidence) + len(relationship_evidence) + len(enrich_evidence),
        "relationship_evidence_ids": [str(e) for e in relationship_evidence],
    }


def _add_research_usage(conn: psycopg.Connection, lease: queue.Lease, calls: int) -> None:
    conn.execute(
        """
        update campaigns set budget_json = jsonb_set(budget_json, '{usage}',
            coalesce(budget_json -> 'usage', '{}'::jsonb) || jsonb_build_object(
              'research_calls', coalesce((budget_json -> 'usage' ->> 'research_calls')::int, 0) + %s))
        where organization_id = %s and id = %s
        """,
        (calls, lease.organization_id, lease.campaign_id),
    )


def _decision(conn, lease, *, status: str, reason: str, checks: list[dict], input_refs: dict, evidence_ids: list[str] | None = None,
              proposed: dict | None = None) -> UUID:
    return conn.execute(
        """
        insert into decisions (organization_id, campaign_id, task_id, kind, status, reason, evidence_ids, input_refs_json,
                               policy_result_json, proposed_action_json)
        values (%s, %s, %s, 'research', %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (
            lease.organization_id, lease.campaign_id, lease.task_id, status, reason, evidence_ids or [],
            Jsonb(input_refs), Jsonb({"pass": all(c["pass"] for c in checks), "checks": checks}),
            Jsonb(proposed) if proposed else None,
        ),
    ).fetchone()["id"]


def _set_campaign(conn, lease, *, status: str, stage: str, terminal: bool = False) -> None:
    conn.execute(
        """
        update campaigns set status = %s, stage = %s, version = version + 1,
               completed_at = case when %s then now() else completed_at end
        where organization_id = %s and id = %s
        """,
        (status, stage, terminal, lease.organization_id, lease.campaign_id),
    )


def handle_research(conn: psycopg.Connection, lease: queue.Lease, *, research_factory: Callable[[], Research]) -> None:
    campaign = conn.execute(
        "select status, stage, normalized_plan_json, limits_json, budget_json from campaigns "
        "where organization_id = %s and id = %s",
        (lease.organization_id, lease.campaign_id),
    ).fetchone()
    if campaign["status"] != "running" or campaign["stage"] != "research" or not campaign["normalized_plan_json"]:
        with queue.fenced(conn, lease):
            queue.complete(conn, lease)
        return

    limits = campaign["limits_json"]
    plan = NormalizedPlan.model_validate(campaign["normalized_plan_json"])
    used = campaign["budget_json"].get("usage", {}).get("research_calls", 0)
    budget = limits["max_research_calls"] - used
    max_discovered = min(limits["max_discovered"], HARD_MAX_DISCOVERED)
    max_enriched = min(limits["max_enriched"], HARD_MAX_ENRICHED)
    input_refs: dict[str, Any] = {
        "plan_sha256": sha256_json(campaign["normalized_plan_json"]),
        "caps": {"max_discovered": max_discovered, "max_enriched": max_enriched, "research_budget": budget},
        "provider": {"name": "crustdata", "api_version": "2025-11-01"},
    }

    queue.heartbeat(conn, lease, LEASE_SECONDS)
    research = research_factory()
    run = run_research(
        research, plan, max_discovered=max_discovered, max_enriched=max_enriched, research_budget=budget,
        beat=lambda: queue.heartbeat(conn, lease, LEASE_SECONDS),
    )
    receipts = [r.ledger() for r in research.receipts]
    billable = _billable(research.receipts)
    input_refs.update({
        "mapping": run.report.as_dict() if run.report else None,
        "receipts": receipts,
        "billable_calls": billable,
        "credits_used": round(sum(r.credits_used or 0 for r in research.receipts), 4),
        "discovered": [{"company_ref": c.ref, "name": c.name} for c in run.discovered],
        "total_count": run.total_count,
        "budget_stop": run.budget_stop,
    })

    with queue.fenced(conn, lease):
        current = conn.execute(
            "select status, stage from campaigns where organization_id = %s and id = %s for update",
            (lease.organization_id, lease.campaign_id),
        ).fetchone()
        _add_research_usage(conn, lease, billable)
        if current["status"] != "running" or current["stage"] != "research":
            _decision(conn, lease, status="rejected", reason=f"Campaign became {current['status']} during research; results discarded.",
                      checks=[{"name": "campaign_running", "pass": False, "reason": current["status"]}], input_refs=input_refs)
            queue.complete(conn, lease)
            return

        error = run.error
        if isinstance(error, UnmappablePlan):
            _decision(conn, lease, status="blocked", reason=f"Plan could not be mapped to verified Crustdata filters: {error}.",
                      checks=[{"name": "plan_mappable", "pass": False, "reason": str(error)}], input_refs=input_refs)
            _set_campaign(conn, lease, status="needs_human", stage="research")
            queue.complete(conn, lease)
            return
        if isinstance(error, (CrustdataOutOfCredits, CrustdataDenied)):
            kind = "insufficient credits" if isinstance(error, CrustdataOutOfCredits) else "request denied"
            _decision(conn, lease, status="blocked", reason=f"Crustdata {kind} on {error.endpoint} (HTTP {error.status}); not retried.",
                      checks=[{"name": "provider_access", "pass": False, "reason": str(error)[:300]}], input_refs=input_refs)
            _set_campaign(conn, lease, status="needs_human", stage="research")
            queue.complete(conn, lease)
            return
        if isinstance(error, CrustdataUnavailable):
            final = lease.attempt >= lease.max_attempts
            _decision(conn, lease, status="blocked" if final else "rejected",
                      reason=f"Crustdata unavailable on {error.endpoint}" + ("; needs operator attention." if final else "; retry scheduled."),
                      checks=[{"name": "provider_available", "pass": False, "reason": str(error)[:300]}], input_refs=input_refs)
            if final:
                _set_campaign(conn, lease, status="needs_human", stage="research")
                queue.fail(conn, lease, {"error_class": "CrustdataUnavailable"}, retry_after_seconds=None)
            else:
                queue.fail(conn, lease, {"error_class": "CrustdataUnavailable"}, retry_after_seconds=UNAVAILABLE_RETRY_SECONDS)
            return

        if run.budget_stop and not run.examined:
            _decision(conn, lease, status="blocked", reason=f"Research budget exhausted before any company could be checked: {run.budget_stop}.",
                      checks=[{"name": "research_budget", "pass": False, "reason": run.budget_stop}], input_refs=input_refs)
            _set_campaign(conn, lease, status="needs_human", stage="research")
            queue.complete(conn, lease)
            return

        outcomes = [_persist_prospect(conn, lease, item) for item in run.examined]
        input_refs["prospects"] = outcomes
        supported = [o for o in outcomes if o.get("relationship") == "supported"]
        relationship_evidence = [e for o in supported for e in o["relationship_evidence_ids"]]
        checks = [
            {"name": "plan_mapped", "pass": True, "reason": f"{len(run.report.mapped)} mapped, {len(run.report.weak_matches)} weak, {len(run.report.unmapped)} left for qualification"},
            {"name": "caps", "pass": True, "reason": f"discovered {len(run.discovered)}/{max_discovered}, enriched {sum(1 for e in run.examined if e.enrich)}/{max_enriched}, billable calls {billable}/{budget}"},
            {"name": "identity_supported", "pass": bool(supported),
             "reason": f"{len(supported)} of {len(outcomes)} examined companies have a current employee with the buyer role"},
        ]
        if supported:
            _decision(conn, lease, status="accepted",
                      reason=f"Found {len(supported)} company/person pair(s) with Crustdata employment evidence; qualification queued.",
                      checks=checks, input_refs=input_refs, evidence_ids=relationship_evidence)
            _set_campaign(conn, lease, status="running", stage="qualify")
            conn.execute(
                """
                insert into tasks (organization_id, campaign_id, kind, dedupe_key, payload_json, status)
                values (%s, %s, 'qualify_and_draft', %s, %s, 'ready')
                on conflict (organization_id, dedupe_key) do nothing
                """,
                (lease.organization_id, lease.campaign_id, f"campaign:{lease.campaign_id}:qualify_and_draft",
                 Jsonb({"schema_version": CONTRACT_VERSION, "campaign_id": str(lease.campaign_id), "conversation_id": None,
                        "expected_conversation_version": None, "trigger_message_id": None, "decision_id": None,
                        "input_ref_ids": [o["prospect_id"] for o in supported]})),
            )
        else:
            _decision(conn, lease, status="blocked",
                      reason="No examined company had a current employee with the buyer role in Crustdata; identity not invented.",
                      checks=checks, input_refs=input_refs)
            _set_campaign(conn, lease, status="no_match", stage="research", terminal=True)
        queue.complete(conn, lease)
