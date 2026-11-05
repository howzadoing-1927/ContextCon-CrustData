"use client";

import { Building2, CalendarCheck, FileText, Globe, Mail, ShieldCheck, UserRound } from "lucide-react";
import { createContext, useContext, useMemo } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { EvidenceSourceKind, EvidenceView, FactStatus } from "@/lib/contracts";
import { cn } from "@/lib/utils";
import { Instant, KeyValue, MonoId } from "./mono";

const EvidenceContext = createContext<Map<string, EvidenceView>>(new Map());

export function EvidenceProvider({ evidence, children }: { evidence: EvidenceView[]; children: React.ReactNode }) {
  const index = useMemo(() => new Map(evidence.map((e) => [e.id, e])), [evidence]);
  return <EvidenceContext.Provider value={index}>{children}</EvidenceContext.Provider>;
}

export function useEvidence(id: string): EvidenceView | undefined {
  return useContext(EvidenceContext).get(id);
}

export const SOURCE_META: Record<EvidenceSourceKind, { label: string; Icon: typeof Globe }> = {
  crustdata: { label: "Crustdata", Icon: Building2 },
  seller_website: { label: "Seller website", Icon: Globe },
  operator: { label: "Operator supplied", Icon: UserRound },
  google_message: { label: "Gmail", Icon: Mail },
  google_calendar: { label: "Google Calendar", Icon: CalendarCheck },
  policy: { label: "Policy", Icon: ShieldCheck },
};

const FACT_META: Record<FactStatus, { label: string; className: string }> = {
  observed: { label: "Observed", className: "text-info border-info/45" },
  operator_approved: { label: "Approved", className: "text-ok border-ok/45" },
  hypothesis: { label: "Hypothesis", className: "text-muted-foreground border-dashed border-faint" },
  conflicted: { label: "Conflicted", className: "text-bad border-bad/50" },
};

export function FactLabel({ status, className }: { status: FactStatus; className?: string }) {
  const meta = FACT_META[status];
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center rounded-sm border px-1.5 text-[0.6875rem] font-medium leading-none",
        meta.className,
        className,
      )}
    >
      {meta.label}
    </span>
  );
}

function EvidenceDetail({ evidence }: { evidence: EvidenceView }) {
  const source = SOURCE_META[evidence.source_kind];
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium">
          <source.Icon aria-hidden className="size-3.5 text-muted-foreground" />
          {source.label}
        </span>
        <FactLabel status={evidence.fact_status} />
      </div>
      <blockquote className="border-l border-hairline pl-2.5 text-sm text-foreground">{evidence.excerpt}</blockquote>
      <dl className="divide-y divide-hairline">
        {evidence.provider_ref && (
          <KeyValue label="Provider ref">
            <MonoId value={evidence.provider_ref} length={22} />
          </KeyValue>
        )}
        {evidence.field_path && (
          <KeyValue label="Field path">
            <span className="font-mono text-2xs text-muted-foreground">{evidence.field_path}</span>
          </KeyValue>
        )}
        {evidence.source_url && (
          <KeyValue label="Source">
            <a
              href={evidence.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-2xs text-info underline"
            >
              {evidence.source_url}
            </a>
          </KeyValue>
        )}
        <KeyValue label="Retrieved">
          <Instant value={evidence.retrieved_at} />
        </KeyValue>
        <KeyValue label="Source as of">
          {evidence.source_as_of ? <Instant value={evidence.source_as_of} /> : <span className="text-2xs text-faint">not reported</span>}
        </KeyValue>
        <KeyValue label="SHA-256">
          <MonoId value={evidence.content_sha256} length={12} />
        </KeyValue>
      </dl>
    </div>
  );
}

/** Small button that opens one evidence record. */
export function EvidenceChip({ id, className }: { id: string; className?: string }) {
  const evidence = useEvidence(id);
  if (!evidence) {
    return (
      <span title={id} className={cn("inline-flex h-5 items-center rounded-sm border border-dashed border-hairline px-1.5 font-mono text-[0.6875rem] text-faint", className)}>
        not loaded
      </span>
    );
  }
  const source = SOURCE_META[evidence.source_kind];
  return (
    <Popover>
      <PopoverTrigger
        aria-label={`Evidence from ${source.label}: ${evidence.excerpt}`}
        className={cn(
          "inline-flex h-5 items-center gap-1 rounded-sm border border-hairline bg-raised px-1.5 text-[0.6875rem] text-muted-foreground transition-colors duration-150 hover:border-input hover:text-foreground data-popup-open:border-signal/60 data-popup-open:text-foreground",
          className,
        )}
      >
        <source.Icon aria-hidden className="size-3" />
        <span className="font-mono">{evidence.content_sha256.slice(0, 6)}</span>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-96 gap-0 p-3">
        <EvidenceDetail evidence={evidence} />
      </PopoverContent>
    </Popover>
  );
}

export function EvidenceList({ ids, empty = "No evidence cited", className }: { ids: string[]; empty?: string; className?: string }) {
  if (!ids.length) return <span className={cn("text-2xs text-faint", className)}>{empty}</span>;
  return (
    <span className={cn("inline-flex flex-wrap gap-1", className)}>
      {ids.map((id) => (
        <EvidenceChip key={id} id={id} />
      ))}
    </span>
  );
}

/** A statement with its fact status and the evidence behind it. */
export function Fact({
  status,
  children,
  evidenceIds,
  className,
}: {
  status: FactStatus;
  children: React.ReactNode;
  evidenceIds: string[];
  className?: string;
}) {
  return (
    <li className={cn("flex flex-col gap-1.5 py-2", className)}>
      <div className="flex items-start gap-2">
        <FactLabel status={status} className="mt-px" />
        <p className={cn("text-sm", status === "hypothesis" && "text-muted-foreground italic")}>{children}</p>
      </div>
      <EvidenceList ids={evidenceIds} className="pl-[4.75rem]" empty={status === "hypothesis" ? "No supporting evidence" : "No evidence cited"} />
    </li>
  );
}
