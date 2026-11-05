"use client";

import { Check, ChevronRight, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { EvidenceList } from "@/components/outcome/evidence";
import { MonoId } from "@/components/outcome/mono";
import { ProvenanceStamp } from "@/components/outcome/provenance";
import { StatusChip, type Tone } from "@/components/outcome/status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { describeError } from "@/lib/api/errors";
import type { DecisionStatus, DecisionView } from "@/lib/contracts";
import { formatCount, formatTime, humanize } from "@/lib/format";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

const STATUS: Record<DecisionStatus, { label: string; tone: Tone }> = {
  accepted: { label: "Accepted", tone: "quiet" },
  rejected: { label: "Rejected", tone: "quiet" },
  blocked: { label: "Blocked", tone: "attention" },
  resolved: { label: "Resolved", tone: "info" },
};

const ACTION_TONE: Record<string, Tone> = {
  prepared: "quiet",
  executing: "info",
  succeeded: "ok",
  failed: "bad",
  unknown: "attention",
  cancelled: "quiet",
};

function Value({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-faint">none</span>;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <span className="break-all">{String(value)}</span>;
  }
  return <span className="break-all">{JSON.stringify(value)}</span>;
}

function Pairs({ title, data }: { title: string; data: Record<string, unknown> | null | undefined }) {
  const entries = Object.entries(data ?? {}).filter(([k]) => k !== "resolution_types");
  if (!entries.length) return null;
  return (
    <div>
      <p className="text-2xs font-medium text-muted-foreground">{title}</p>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-2xs">
        {entries.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-faint">{k}</dt>
            <dd className="text-muted-foreground">
              <Value value={v} />
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function DecisionRow({ decision, timeZone, fresh }: { decision: DecisionView; timeZone: string; fresh: boolean }) {
  const { mode } = useSession();
  const [open, setOpen] = useState(decision.status === "blocked");
  const status = STATUS[decision.status];
  const tokensIn = Number(decision.model?.usage.tokens_in ?? 0);
  const tokensOut = Number(decision.model?.usage.tokens_out ?? 0);
  const provenance = mode === "LIVE" && decision.actual_action?.provider_ref ? "LIVE" : null;
  const panelId = `decision-${decision.id}`;

  return (
    <li className={cn("border-b border-hairline", fresh && "row-arrive", decision.status === "blocked" && "bg-signal/5")}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="group flex w-full items-start gap-2 px-4 py-2.5 text-left transition-colors duration-150 hover:bg-raised"
      >
        <ChevronRight
          aria-hidden
          className={cn("mt-0.5 size-3.5 shrink-0 text-faint transition-transform duration-150", open && "rotate-90")}
        />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="font-mono text-2xs text-faint">{formatTime(decision.created_at, timeZone).slice(0, 8)}</span>
            <span className="truncate text-xs font-medium">{humanize(decision.kind)}</span>
            <span className="ml-auto flex shrink-0 items-center gap-1.5">
              {provenance && <ProvenanceStamp kind={provenance} className="h-4 px-1 [&_svg]:size-2.5" />}
              {decision.status !== "accepted" && (
                <StatusChip tone={status.tone} className="h-5">
                  {status.label}
                </StatusChip>
              )}
            </span>
          </span>
          <span className={cn("mt-1 block text-xs text-muted-foreground", !open && "line-clamp-2")}>{decision.reason}</span>
        </span>
      </button>
      {open && (
        <div id={panelId} className="flex flex-col gap-3 px-4 pb-3 pl-9.5">
          {decision.evidence_ids.length > 0 && (
            <div>
              <p className="text-2xs font-medium text-muted-foreground">Evidence</p>
              <EvidenceList ids={decision.evidence_ids} className="mt-1" />
            </div>
          )}
          {decision.policy.checks.length > 0 && (
            <div>
              <p className="text-2xs font-medium text-muted-foreground">
                Policy {decision.policy.pass ? "passed" : <span className="text-signal">did not pass</span>}
              </p>
              <ul className="mt-1 flex flex-col gap-1">
                {decision.policy.checks.map((c) => (
                  <li key={c.name} className="flex items-start gap-1.5 text-xs">
                    {c.pass ? (
                      <Check aria-label="Passed" className="mt-0.5 size-3 shrink-0 text-ok" />
                    ) : (
                      <X aria-label="Failed" className="mt-0.5 size-3 shrink-0 text-bad" />
                    )}
                    <span>
                      <span className="font-mono text-2xs text-foreground">{c.name}</span>{" "}
                      <span className="text-muted-foreground">{c.reason}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {decision.actual_action && (
            <div>
              <p className="text-2xs font-medium text-muted-foreground">Effect</p>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                <StatusChip tone={ACTION_TONE[decision.actual_action.state] ?? "quiet"} className="h-5">
                  {humanize(decision.actual_action.state)}
                </StatusChip>
                <span className="text-2xs text-faint">action</span>
                <MonoId value={decision.actual_action.action_id} />
                <span className="text-2xs text-faint">provider</span>
                <MonoId value={decision.actual_action.provider_ref} length={18} />
              </div>
            </div>
          )}
          <Pairs title="Proposed action" data={decision.proposed_action} />
          <Pairs title="Inputs" data={decision.input_refs} />
          <Pairs title="Resolution" data={decision.resolution} />
          {decision.model && (
            <p className="font-mono text-2xs text-faint">
              {decision.model.deployment} · {decision.model.prompt_version}
              {decision.model.model_version && ` · ${decision.model.model_version}`} · {formatCount(tokensIn)} in / {formatCount(tokensOut)} out
            </p>
          )}
          <p className="flex items-center gap-1.5 text-2xs text-faint">
            Decision <MonoId value={decision.id} />
          </p>
        </div>
      )}
    </li>
  );
}

export type Ledger = ReturnType<typeof useLedger>;

export function useLedger(campaignId: string, signal: string) {
  const { client } = useSession();
  const [items, setItems] = useState<DecisionView[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const extra = useRef<DecisionView[]>([]);

  const loadFirst = useCallback(async () => {
    try {
      const page = await client.campaigns.ledger(campaignId, null, 50);
      const ids = new Set(page.data.items.map((d) => d.id));
      setItems([...page.data.items, ...extra.current.filter((d) => !ids.has(d.id))]);
      if (!extra.current.length) setCursor(page.data.next_cursor);
      setError(null);
    } catch (cause) {
      setError(cause);
    }
  }, [client, campaignId]);

  useEffect(() => {
    void loadFirst();
  }, [loadFirst, signal]);

  async function loadMore() {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const page = await client.campaigns.ledger(campaignId, cursor, 50);
      extra.current = [...extra.current, ...page.data.items];
      setItems((current) => [...(current ?? []), ...page.data.items]);
      setCursor(page.data.next_cursor);
    } catch (cause) {
      setError(cause);
    } finally {
      setLoadingMore(false);
    }
  }

  return { items, cursor, error, loadingMore, loadMore, retry: loadFirst };
}

export function DecisionLedger({ ledger, timeZone }: { ledger: Ledger; timeZone: string }) {
  const { items, cursor, error, loadingMore, loadMore, retry } = ledger;
  const { mode } = useSession();
  const seen = useRef<Set<string> | null>(null);
  const fresh = new Set<string>();
  if (items) {
    if (seen.current) for (const d of items) if (!seen.current.has(d.id)) fresh.add(d.id);
  }
  useEffect(() => {
    if (items) seen.current = new Set(items.map((d) => d.id));
  }, [items]);

  return (
    <section aria-labelledby="ledger-heading" className="flex min-h-0 flex-col">
      <header className="sticky top-0 z-10 flex items-baseline justify-between border-b border-hairline bg-shell px-4 py-2.5">
        <h2 id="ledger-heading" className="flex items-center gap-2 text-sm font-semibold">
          Decision ledger
          {mode === "FIXTURE" && <ProvenanceStamp kind="FIXTURE" className="h-4 px-1 [&_svg]:size-2.5" />}
        </h2>
        <span className="text-2xs text-faint tabular">{items ? `${items.length}${cursor ? "+" : ""} decisions · oldest first` : ""}</span>
      </header>
      {error != null && (
        <div role="alert" className="flex items-center justify-between gap-2 border-b border-hairline px-4 py-2 text-2xs text-signal">
          {describeError(error).title}
          <Button size="xs" variant="outline" onClick={() => void retry()}>
            Retry
          </Button>
        </div>
      )}
      {!items ? (
        <div className="space-y-2 p-4" aria-busy="true">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <p className="px-4 py-6 text-xs text-muted-foreground">No decisions yet. The first one appears when the worker plans the mission.</p>
      ) : (
        <ol aria-live="polite" aria-relevant="additions">
          {items.map((d) => (
            <DecisionRow key={d.id} decision={d} timeZone={timeZone} fresh={fresh.has(d.id)} />
          ))}
        </ol>
      )}
      {cursor && (
        <div className="p-3">
          <Button size="sm" variant="outline" className="w-full" onClick={() => void loadMore()} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Load more decisions"}
          </Button>
        </div>
      )}
    </section>
  );
}
