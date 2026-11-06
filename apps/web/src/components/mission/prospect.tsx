"use client";

import { Check, ChevronRight, CircleHelp, VenetianMask, X } from "lucide-react";
import { EvidenceList, Fact } from "@/components/outcome/evidence";
import { MonoId } from "@/components/outcome/mono";
import { Section } from "@/components/outcome/panel";
import { StatusChip, type Tone } from "@/components/outcome/status";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { CriterionResult, ProspectCase } from "@/lib/contracts";
import { cn } from "@/lib/utils";

const FIT: Record<ProspectCase["fit"], { label: string; tone: Tone }> = {
  qualified: { label: "Qualified", tone: "ok" },
  rejected: { label: "Rejected", tone: "quiet" },
  needs_evidence: { label: "Needs evidence", tone: "wait" },
};

const RESULT = {
  pass: { Icon: Check, label: "Pass", className: "text-ok" },
  fail: { Icon: X, label: "Fail", className: "text-bad" },
  unknown: { Icon: CircleHelp, label: "Unknown", className: "text-signal" },
} as const;

const RELATIONSHIP = {
  supported: "Current employment supported by evidence",
  unknown: "Current employment not established",
  conflicted: "Sources disagree about current employment",
} as const;

function Criteria({ criteria }: { criteria: CriterionResult[] }) {
  return (
    <table className="w-full text-left text-xs">
      <caption className="sr-only">Must-have criteria and how this prospect scored</caption>
      <thead className="text-2xs text-faint">
        <tr>
          <th scope="col" className="w-[38%] pb-1.5 font-medium">
            Must-have
          </th>
          <th scope="col" className="w-20 pb-1.5 font-medium">
            Result
          </th>
          <th scope="col" className="pb-1.5 font-medium">
            Why
          </th>
        </tr>
      </thead>
      <tbody className="divide-y divide-hairline border-t border-hairline align-top">
        {criteria.map((c) => {
          const r = RESULT[c.result];
          return (
            <tr key={c.name}>
              <th scope="row" className="py-2 pr-3 font-normal">
                {c.name}
              </th>
              <td className={cn("py-2 pr-3", r.className)}>
                <span className="inline-flex items-center gap-1 font-medium">
                  <r.Icon aria-hidden className="size-3.5" />
                  {r.label}
                </span>
              </td>
              <td className="py-2">
                <p className="text-muted-foreground">{c.reason}</p>
                <EvidenceList ids={c.evidence_ids} className="mt-1" />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function locationOf(prospect: ProspectCase) {
  if (prospect.company.location) return prospect.company.location;
  const fact = prospect.facts.find((item) => /headquarters|locations\.city/i.test(item.text));
  return fact?.text.replace(/^[^:]+:\s*/, "").replace(/^"|"$/g, "") ?? null;
}

export function FoundPeople({ prospects }: { prospects: ProspectCase[] }) {
  const people = prospects.filter((p) => p.person);
  if (!people.length) return null;
  return (
    <Section id="found-people" title="People found">
      <p className="mb-3 max-w-[64ch] text-xs text-muted-foreground">
        Restaurant owners and operators across India, with the work email Crustdata returned. Outbound still goes to the consented test inbox.
      </p>
      <ul className="divide-y divide-hairline border-t border-hairline">
        {people.map((p) => {
          const place = locationOf(p);
          return (
            <li key={p.id} className="grid grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1.1fr)] gap-3 py-3 max-sm:grid-cols-1">
              <div className="min-w-0">
                <p className="text-sm font-medium">{p.person?.name}</p>
                <p className="text-xs text-muted-foreground">{p.person?.title}</p>
              </div>
              <div className="min-w-0">
                <p className="text-sm">{p.company.name}</p>
                <p className="text-xs text-muted-foreground">{place ?? p.company.domain ?? "India"}</p>
              </div>
              <div className="min-w-0">
                {p.person?.found_email ? (
                  <p className="font-mono text-xs text-foreground">{p.person.found_email}</p>
                ) : (
                  <p className="text-xs text-muted-foreground">{p.company.domain ? `via ${p.company.domain}` : "Email not on the record"}</p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

export function OutreachDrafts({ prospects }: { prospects: ProspectCase[] }) {
  const drafts = prospects.filter((p) => p.draft && p.person);
  if (!drafts.length) return null;
  return (
    <Section id="outbound-drafts" title="Personalized outbound">
      <p className="mb-3 max-w-[64ch] text-xs text-muted-foreground">
        One short email per qualified person, written from the company evidence. Delivery is to the test inbox playing the buyer.
      </p>
      <ul className="flex flex-col gap-3">
        {drafts.map((p) => (
          <li key={p.id} className="rounded-md border border-hairline px-3 py-3">
            <p className="text-xs text-muted-foreground">
              To {p.person?.name}
              {p.person?.found_email ? <span className="font-mono"> · {p.person.found_email}</span> : null}
            </p>
            <p className="mt-1 text-sm font-medium">{p.draft?.subject}</p>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{p.draft?.body_text}</p>
          </li>
        ))}
      </ul>
    </Section>
  );
}

export function ProspectCaseView({ prospect }: { prospect: ProspectCase }) {
  const fit = FIT[prospect.fit];
  return (
    <Section id="prospect" title="Prospect case" actions={<StatusChip tone={fit.tone}>{fit.label}</StatusChip>}>
      <div className="grid grid-cols-2 gap-x-6 gap-y-3">
        <div className="min-w-0">
          <p className="text-2xs text-faint">Company</p>
          <p className="text-sm font-medium">{prospect.company.name}</p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-2xs text-muted-foreground">
            {prospect.company.domain && <span className="font-mono">{prospect.company.domain}</span>}
            <MonoId value={prospect.canonical_company_ref} length={22} />
          </p>
        </div>
        <div className="min-w-0">
          <p className="text-2xs text-faint">Person</p>
          {prospect.person ? (
            <>
              <p className="text-sm font-medium">
                {prospect.person.name}
                {prospect.person.title && <span className="font-normal text-muted-foreground">, {prospect.person.title}</span>}
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-2xs text-muted-foreground">
                <MonoId value={prospect.canonical_person_ref} length={22} />
              </p>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Not identified yet</p>
          )}
          <p
            className={cn(
              "mt-1 flex flex-wrap items-center gap-1.5 text-2xs",
              prospect.relationship.status === "supported" ? "text-muted-foreground" : "text-signal",
            )}
          >
            {RELATIONSHIP[prospect.relationship.status]}
            <EvidenceList ids={prospect.relationship.evidence_ids} empty="" />
          </p>
        </div>
      </div>

      <div className="mt-4">
        <Criteria criteria={prospect.criteria} />
      </div>

      {(prospect.facts.length > 0 || prospect.hypotheses.length > 0) && (
        <ul className="mt-3 divide-y divide-hairline border-t border-hairline">
          {prospect.facts.map((fact) => (
            <Fact key={fact.text} status="observed" evidenceIds={fact.evidence_ids}>
              {fact.text}
            </Fact>
          ))}
          {prospect.hypotheses.map((h) => (
            <Fact key={h.text} status="hypothesis" evidenceIds={h.basis_evidence_ids}>
              {h.text}
            </Fact>
          ))}
        </ul>
      )}

      <div className="mt-3 flex items-start gap-2.5 rounded-md border border-simbuyer/30 px-3 py-2">
        <VenetianMask aria-hidden className="mt-0.5 size-4 shrink-0 text-simbuyer" />
        <p className="max-w-[64ch] text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Delivery goes to a test inbox playing the buyer.</span> Every email for{" "}
          {prospect.person?.name ?? "this prospect"} is sent to <span className="font-mono text-2xs text-foreground">{prospect.delivery.buyer_test_email}</span>, a
          consenting teammate. The real person is never contacted.
        </p>
      </div>
    </Section>
  );
}

export function RejectedProspects({ prospects }: { prospects: ProspectCase[] }) {
  if (!prospects.length) return null;
  return (
    <Collapsible className="border-b border-hairline py-4">
      <CollapsibleTrigger className="group flex w-full items-center gap-2 text-left text-sm font-semibold">
        <ChevronRight aria-hidden className="size-4 text-muted-foreground transition-transform duration-150 group-data-[panel-open]:rotate-90" />
        Not chosen
        <span className="font-normal text-muted-foreground tabular">{prospects.length}</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-2 divide-y divide-hairline pl-6">
          {prospects.map((p) => (
            <li key={p.id} className="py-2.5">
              <div className="flex items-baseline gap-2">
                <p className="text-sm">{p.company.name}</p>
                <MonoId value={p.canonical_company_ref} length={22} />
              </div>
              {p.criteria
                .filter((c) => c.result !== "pass")
                .map((c) => (
                  <div key={c.name} className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                    <span className={RESULT[c.result].className}>{RESULT[c.result].label}:</span>
                    <span className="text-muted-foreground">{c.reason}</span>
                    <EvidenceList ids={c.evidence_ids} />
                  </div>
                ))}
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}
