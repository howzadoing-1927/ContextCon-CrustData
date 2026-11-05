"use client";

import { CalendarCheck, ExternalLink } from "lucide-react";
import { EvidenceList, FactLabel } from "@/components/outcome/evidence";
import { MonoId } from "@/components/outcome/mono";
import { ProvenanceStamp } from "@/components/outcome/provenance";
import { StatusChip, type Tone } from "@/components/outcome/status";
import type { Handoff } from "@/lib/contracts";
import { formatSlot } from "@/lib/format";
import { useSession } from "@/lib/session";

const NOTIFY: Record<Handoff["notification_status"], { label: string; tone: Tone }> = {
  not_requested: { label: "Not requested", tone: "quiet" },
  pending: { label: "Sending", tone: "wait" },
  sent: { label: "Sent", tone: "ok" },
  failed: { label: "Failed", tone: "bad" },
};

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <h3 className="text-2xs font-medium text-muted-foreground">{title}</h3>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function Items({ items, empty, ordered }: { items: string[]; empty: string; ordered?: boolean }) {
  if (!items.length) return <p className="text-xs text-faint">{empty}</p>;
  const List = ordered ? "ol" : "ul";
  return (
    <List className={ordered ? "list-decimal space-y-1 pl-4 text-sm marker:text-faint" : "space-y-1 text-sm"}>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </List>
  );
}

export function HandoffCard({ handoff }: { handoff: Handoff }) {
  const { mode } = useSession();
  const { booking } = handoff;
  const notify = NOTIFY[handoff.notification_status];
  return (
    <section aria-labelledby="handoff-heading" className="mt-5 rounded-lg border border-ok/30 bg-shell">
      <header className="flex flex-wrap items-start gap-x-4 gap-y-2 border-b border-hairline px-5 py-4">
        <CalendarCheck aria-hidden className="mt-1 size-5 text-ok" />
        <div className="min-w-0 flex-1">
          <h2 id="handoff-heading" className="text-base font-semibold">
            Meeting booked, handoff written
          </h2>
          <p className="mt-1 text-lg font-medium tabular">{formatSlot(booking.start, booking.end, booking.timezone)}</p>
          <p className="font-mono text-2xs text-muted-foreground">{formatSlot(booking.start, booking.end, "UTC")}</p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <ProvenanceStamp kind={mode === "FIXTURE" ? "FIXTURE" : "LIVE"} />
          <StatusChip tone="wait">Invitation sent · acceptance not verified</StatusChip>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-hairline px-5 py-2.5 text-2xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          Event <MonoId value={booking.event_id} length={20} />
        </span>
        <span>
          Calendar <span className="font-mono">{booking.calendar_id}</span>
        </span>
        <span className="flex items-center gap-1.5">
          Action <MonoId value={booking.action_id} />
        </span>
        {booking.html_link && (
          <a href={booking.html_link} target="_blank" rel="noopener noreferrer" className="ml-auto inline-flex items-center gap-1 text-info underline">
            Open in Google Calendar
            <ExternalLink aria-hidden className="size-3" />
          </a>
        )}
      </div>

      <div className="grid grid-cols-2 gap-x-8 gap-y-5 px-5 py-4">
        <div className="col-span-2">
          <Block title="Why this prospect">
            <p className="max-w-[62ch] text-sm">{handoff.fit_summary}</p>
            <EvidenceList ids={handoff.fit_evidence_ids} className="mt-1.5" />
          </Block>
        </div>
        <Block title="What the buyer said">
          {handoff.buyer_stated_needs.length ? (
            <ul className="space-y-1.5">
              {handoff.buyer_stated_needs.map((need) => (
                <li key={need.message_id} className="text-sm">
                  {need.text}{" "}
                  <a href={`#msg-${need.message_id}`} className="text-2xs text-muted-foreground underline">
                    in thread
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-faint">The buyer didn&apos;t state a need.</p>
          )}
        </Block>
        <Block title="Not confirmed by the buyer">
          {handoff.hypotheses.length ? (
            <ul className="space-y-1.5">
              {handoff.hypotheses.map((h) => (
                <li key={h} className="flex items-start gap-2 text-sm text-muted-foreground italic">
                  <FactLabel status="hypothesis" className="mt-px not-italic" />
                  {h}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-faint">No open hypotheses.</p>
          )}
        </Block>
        <Block title="Open questions">
          <Items items={handoff.open_questions} empty="None." />
        </Block>
        <Block title="Next steps">
          <Items items={handoff.next_steps} empty="None." ordered />
        </Block>
      </div>

      <footer className="flex items-center gap-2 border-t border-hairline px-5 py-2.5 text-2xs text-muted-foreground">
        Owner notification
        <StatusChip tone={notify.tone} className="h-5">
          {notify.label}
        </StatusChip>
        {handoff.owner_email && <span className="font-mono">{handoff.owner_email}</span>}
      </footer>
    </section>
  );
}
