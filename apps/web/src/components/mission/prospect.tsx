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
              {prospect.person.found_email && (
                <p className="mt-1 flex flex-wrap items-center gap-x-2 text-2xs text-muted-foreground">
                  {prospect.person.found_email.email ? (
                    <>
                      <span>Found</span>
                      <span className="font-mono text-foreground">{prospect.person.found_email.email}</span>
                      <span className="text-faint">
                        {prospect.person.found_email.status} · Crustdata · not contacted
                      </span>
                    </>
                  ) : (
                    <span>No business email found ({prospect.person.found_email.status})</span>
                  )}
                </p>
              )}
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
          consenting teammate. The real person is never contacted
          {prospect.person?.found_email?.email ? ", even though their address was found" : ""}.
        </p>
      </div>
    </Section>
  );
}

export function PeopleList({
  prospects,
  selectedId,
  onSelect,
}: {
  prospects: ProspectCase[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const reached = prospects.filter((p) => p.delivery.conversation_id).length;
  return (
    <Section
      id="people"
      title="People"
      description={`${prospects.length} found · ${reached} emailed. Real emails are shown, never mailed; each person's email goes to a test inbox.`}
    >
      <div className="overflow-hidden rounded-md border border-hairline">
        <table className="w-full table-fixed text-left text-xs">
          <caption className="sr-only">People found for this mission</caption>
          <thead className="bg-shell text-2xs text-faint">
            <tr>
              <th scope="col" className="w-[30%] px-3 py-1.5 font-medium">Company and person</th>
              <th scope="col" className="w-[28%] px-3 py-1.5 font-medium">Real email found</th>
              <th scope="col" className="w-[26%] px-3 py-1.5 font-medium">Mailed to test inbox</th>
              <th scope="col" className="px-3 py-1.5 font-medium">State</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {prospects.map((p) => {
              const found = p.person?.found_email;
              const selected = p.id === selectedId;
              return (
                <tr
                  key={p.id}
                  aria-selected={selected}
                  onClick={() => onSelect(p.id)}
                  className={cn("cursor-pointer align-top transition-colors duration-150 hover:bg-raised", selected && "bg-raised")}
                >
                  <td className="px-3 py-2">
                    <button type="button" onClick={() => onSelect(p.id)} className="block w-full truncate text-left font-medium text-foreground">
                      {p.company.name}
                    </button>
                    <span className="block truncate text-2xs text-muted-foreground">
                      {p.person ? `${p.person.name}${p.person.title ? `, ${p.person.title}` : ""}` : "No person identified"}
                    </span>
                  </td>
                  <td className="truncate px-3 py-2 font-mono text-2xs">
                    {found?.email ?? <span className="font-sans text-faint">{found ? "None found" : "Not looked up yet"}</span>}
                  </td>
                  <td className="truncate px-3 py-2 font-mono text-2xs">
                    {p.delivery.conversation_id ? p.delivery.buyer_test_email : <span className="font-sans text-faint">Not emailed</span>}
                  </td>
                  <td className="px-3 py-2 text-2xs text-muted-foreground">
                    {p.delivery.conversation_state ? p.delivery.conversation_state.replaceAll("_", " ") : FIT[p.fit].label}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
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
