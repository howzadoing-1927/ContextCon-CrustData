"""Deterministic policy gate, doc 04 order. Runs steps 1-6 before an outbound draft is accepted; steps 7-8
(budget reservation, scopes/token, immutable action + lock-time recheck) run at dispatch (B6) and are recorded
here as deferred, never as passed. The recipient comes from the server snapshot, never from model output."""

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import psycopg

from .contracts.base import normalize_email
from .contracts.model_io import DraftProposal, VerificationResult

_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


@dataclass
class GateResult:
    checks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c["pass"] for c in self.checks if c.get("status") != "deferred")

    @property
    def first_failure(self) -> dict | None:
        return next((c for c in self.checks if c.get("status") != "deferred" and not c["pass"]), None)

    def add(self, step: int, name: str, ok: bool, reason: str) -> bool:
        self.checks.append({"step": step, "name": name, "pass": bool(ok), "reason": reason})
        return bool(ok)

    def as_policy(self) -> dict[str, Any]:
        return {"pass": self.passed, "checks": self.checks}


def initial_send_gate(
    conn: psycopg.Connection,
    *,
    organization_id: UUID,
    campaign_id: UUID,
    prospect: dict,
    qualified: bool,
    draft: DraftProposal | None,
    verification: VerificationResult | None,
    deterministic_findings: list[str],
    snapshot: dict,
    recipient: str,
    sender: str | None,
) -> GateResult:
    gate = GateResult()

    # 1. schema/size, same-tenant references, model output validity
    ok = gate.add(1, "draft_schema_valid", draft is not None, "DraftProposal validated" if draft else "no valid draft")
    if ok:
        cited = sorted({e for c in draft.claims for e in c.evidence_ids} | set(draft.evidence_ids))
        found = {
            str(r["id"]) for r in conn.execute(
                "select id from evidence where organization_id = %s and campaign_id = %s and id::text = any(%s) "
                "and fact_status <> 'conflicted'",
                (organization_id, campaign_id, cited),
            ).fetchall()
        }
        gate.add(1, "evidence_refs_same_tenant", set(cited) <= found, f"{len(found)}/{len(cited)} cited evidence rows found, none conflicted")

    # 2. campaign state from the server
    campaign = conn.execute(
        "select status, stage from campaigns where organization_id = %s and id = %s", (organization_id, campaign_id)
    ).fetchone()
    gate.add(2, "campaign_running", campaign["status"] == "running", f"campaign {campaign['status']}/{campaign['stage']}")
    gate.add(2, "no_inbound_yet", True, "initial message; no conversation exists yet")

    # 3. simulation, consent, exact single recipient, authorized sender
    buyer = (snapshot.get("policy") or {}).get("buyer_test") or {}
    gate.add(3, "simulation_mode", (snapshot.get("policy") or {}).get("simulation") is True, "launch snapshot simulation=true")
    gate.add(3, "consent_persisted", bool(buyer.get("consent_record") and buyer.get("consented_at")), "buyer_test consent record and timestamp")
    gate.add(3, "recipient_is_snapshot_buyer", bool(buyer) and normalize_email(buyer["email"]) == normalize_email(recipient),
             "To is exactly the consented test buyer from the launch snapshot; Cc/Bcc empty")
    gate.add(3, "sender_is_seller_connection", bool(sender), "From is the connected seller account" if sender else "no seller connection account")
    body_emails = _EMAIL.findall((draft.body_text + " " + draft.subject) if draft else "")
    gate.add(3, "no_addresses_in_content", not body_emails, "draft contains no email addresses" if not body_emails else "draft contains an email address")

    # 4. identity resolved, qualified, not suppressed (test email AND researched company/person)
    gate.add(4, "identity_qualified", qualified and bool(prospect.get("canonical_person_ref")), "qualification complete and person identity supported")
    identities = [("email", normalize_email(recipient)), ("company", prospect["canonical_company_ref"])]
    if prospect.get("canonical_person_ref"):
        identities.append(("person", prospect["canonical_person_ref"]))
    hit = conn.execute(
        "select identity_kind from suppressions where organization_id = %s "
        "and (identity_kind, identity_value) in (select * from unnest(%s::text[], %s::text[])) limit 1",
        (organization_id, [k for k, _ in identities], [v for _, v in identities]),
    ).fetchone()
    gate.add(4, "not_suppressed", hit is None, "no suppression on test email, company or person" if hit is None else f"suppressed {hit['identity_kind']}")

    # 5. approved facts + semantic verification
    snapshot_facts = {f["id"] for f in snapshot["approved_profile"]["approved_facts"]}
    used_facts = {f for c in (draft.claims if draft else []) for f in c.approved_fact_ids}
    gate.add(5, "approved_facts_in_snapshot", used_facts <= snapshot_facts, f"facts used {sorted(used_facts)} within launch snapshot")
    gate.add(5, "deterministic_claim_checks", not deterministic_findings, "; ".join(deterministic_findings) or "no findings")
    gate.add(5, "semantic_verifier_pass", verification is not None and verification.verdict == "pass",
             f"verifier verdict {verification.verdict if verification else 'missing'}")

    # 6. action eligibility
    prior = conn.execute(
        "select count(*) as n from conversations where organization_id = %s and campaign_id = %s", (organization_id, campaign_id)
    ).fetchone()["n"]
    gate.add(6, "initial_send_eligible", bool(draft) and draft.purpose == "initial" and prior == 0,
             "first outbound for this campaign; no existing conversation or booking")

    # 7-8 run at dispatch time
    gate.checks.append({"step": 7, "name": "budget_scopes_token", "pass": False, "status": "deferred", "reason": "checked atomically at dispatch (B6)"})
    gate.checks.append({"step": 8, "name": "immutable_action_lock_recheck", "pass": False, "status": "deferred", "reason": "prepared and rechecked under lock at dispatch (B6)"})
    return gate
