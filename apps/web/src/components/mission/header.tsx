"use client";

import { Pause, Play, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { ProvenanceStamp } from "@/components/outcome/provenance";
import { CampaignStatus } from "@/components/outcome/status";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { describeError, isApiError } from "@/lib/api/errors";
import type { CampaignControl, Limits, MissionDetail } from "@/lib/contracts";
import { formatCount, humanize, relativeAge } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useMutation } from "@/lib/use-mutation";
import { cn } from "@/lib/utils";

const TERMINAL = new Set(["completed", "no_match", "stopped", "failed"]);

function compact(n: number) {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function UsageStrip({ detail, limits }: { detail: MissionDetail; limits: Limits | null }) {
  const u = detail.usage;
  const cost = u.estimated_cost;
  const items: [string, React.ReactNode, string?][] = [
    ["Model", <>{u.model_calls}{limits && <span className="text-faint">/{limits.max_model_calls}</span>}</>],
    ["Research", <>{u.research_calls}{limits && <span className="text-faint">/{limits.max_research_calls}</span>}</>],
    ["Email", <>{u.outbound_attempts}{limits && <span className="text-faint">/{limits.max_outbound_messages}</span>}</>],
    ["Calendar", <>{u.calendar_attempts}</>],
    ["Tokens", <>{compact(u.tokens_in)} in · {compact(u.tokens_out)} out</>, `${formatCount(u.tokens_in)} in, ${formatCount(u.tokens_out)} out`],
    [
      "Cost",
      cost ? <>{String(cost.amount)} {cost.currency}</> : <span className="text-faint">unknown</span>,
      cost ? `Estimated from ${cost.pricing_source}` : "The provider didn't report a price, so cost is unknown, not zero.",
    ],
  ];
  return (
    <dl className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-2xs">
      {items.map(([label, value, title]) => (
        <div key={label} className="flex items-baseline gap-1.5" title={title}>
          <dt className="text-faint">{label}</dt>
          <dd className="font-mono text-muted-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Controls({ detail, canControl, onChanged }: { detail: MissionDetail; canControl: boolean; onChanged: () => void }) {
  const { client } = useSession();
  const [pending, setPending] = useState<{ action: CampaignControl; fromVersion: number; fromStatus: string } | null>(null);
  const [stopOpen, setStopOpen] = useState(false);
  const control = useMutation("control", (action: CampaignControl, key: string) =>
    client.campaigns.control(detail.id, { action, expected_version: detail.version }, key),
  );

  useEffect(() => {
    if (pending && (detail.version > pending.fromVersion || detail.status !== pending.fromStatus)) setPending(null);
  }, [detail.version, detail.status, pending]);

  const terminal = TERMINAL.has(detail.status);
  if (terminal) return null;

  async function send(action: CampaignControl) {
    const result = await control.run(action);
    setStopOpen(false);
    if (result) {
      setPending({ action, fromVersion: detail.version, fromStatus: detail.status });
      onChanged();
    }
  }

  const disabledReason = !canControl ? "Only owners can pause or stop a mission." : undefined;
  const busy = control.pending || pending !== null;
  const canPause = detail.status === "running" || detail.status === "waiting_reply" || detail.status === "draft";

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1.5" title={disabledReason}>
        {detail.status === "paused" ? (
          <Button size="sm" variant="outline" disabled={!canControl || busy} onClick={() => send("resume")}>
            <Play data-icon="inline-start" />
            Resume
          </Button>
        ) : (
          canPause && (
            <Button size="sm" variant="outline" disabled={!canControl || busy} onClick={() => send("pause")}>
              <Pause data-icon="inline-start" />
              Pause
            </Button>
          )
        )}
        <Popover open={stopOpen} onOpenChange={setStopOpen}>
          <PopoverTrigger
            render={
              <Button size="sm" variant="destructive" disabled={!canControl || busy}>
                <Square data-icon="inline-start" />
                Stop
              </Button>
            }
          />
          <PopoverContent align="end" className="w-80 p-3">
            <p className="text-sm font-medium">Stop this mission?</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Nothing new starts. A provider call already in flight finishes or is reconciled first. A stopped mission can&apos;t be resumed.
            </p>
            <div className="mt-3 flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setStopOpen(false)}>
                Keep running
              </Button>
              <Button size="sm" variant="destructive" onClick={() => send("stop")} disabled={control.pending}>
                Stop mission
              </Button>
            </div>
          </PopoverContent>
        </Popover>
      </div>
      <p role="status" className="text-2xs text-muted-foreground">
        {pending
          ? `${humanize(pending.action)} requested at v${pending.fromVersion}. Takes effect after the step in flight.`
          : control.error != null
            ? <span className="text-bad">{isApiError(control.error) && control.error.code === "CONFLICT" ? "Mission changed. Try again on the current version." : describeError(control.error).title}</span>
            : null}
      </p>
    </div>
  );
}

export function MissionHeader({
  detail,
  limits,
  canControl,
  fetchedAt,
  stale,
  now,
  onChanged,
}: {
  detail: MissionDetail;
  limits: Limits | null;
  canControl: boolean;
  fetchedAt: number | null;
  stale: boolean;
  now: number;
  onChanged: () => void;
}) {
  const { mode } = useSession();
  const [expanded, setExpanded] = useState(false);
  const long = detail.request_text.length > 220;

  return (
    <header className="border-b border-hairline bg-background px-5 py-3">
      <div className="flex items-start gap-6">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <CampaignStatus status={detail.status} />
            {mode === "FIXTURE" && <ProvenanceStamp kind="FIXTURE" />}
            <span className="font-mono text-2xs text-faint">
              v{detail.version} · {humanize(detail.stage)}
            </span>
            <span className={cn("text-2xs tabular", stale ? "font-medium text-signal" : "text-faint")}>
              {stale ? "Updates failing · last good " : "Updated "}
              {relativeAge(fetchedAt, now)}
            </span>
          </div>
          <h1 className={cn("mt-1.5 max-w-[80ch] text-base font-medium text-pretty", !expanded && "line-clamp-2")}>{detail.request_text}</h1>
          {long && (
            <button type="button" onClick={() => setExpanded((v) => !v)} className="text-2xs text-muted-foreground underline">
              {expanded ? "Show less" : "Show full request"}
            </button>
          )}
          <div className="mt-2">
            <UsageStrip detail={detail} limits={limits} />
          </div>
        </div>
        <Controls detail={detail} canControl={canControl} onChanged={onChanged} />
      </div>
    </header>
  );
}
