import type { CampaignState, ConversationState } from "@/lib/contracts";
import { cn } from "@/lib/utils";

export type Tone = "ok" | "info" | "wait" | "attention" | "bad" | "quiet";

const toneClass: Record<Tone, string> = {
  ok: "text-ok bg-ok/12 border-ok/30",
  info: "text-info bg-info/12 border-info/30",
  wait: "text-info border-info/40 bg-transparent",
  attention: "text-signal bg-signal/14 border-signal/40",
  bad: "text-bad bg-bad/12 border-bad/30",
  quiet: "text-muted-foreground bg-muted border-hairline",
};

const dotClass: Record<Tone, string> = {
  ok: "bg-ok",
  info: "bg-info",
  wait: "border border-info bg-transparent",
  attention: "bg-signal",
  bad: "bg-bad",
  quiet: "bg-faint",
};

export const CAMPAIGN_STATUS: Record<CampaignState, { label: string; tone: Tone }> = {
  draft: { label: "Draft", tone: "quiet" },
  running: { label: "Running", tone: "info" },
  waiting_reply: { label: "Waiting for buyer", tone: "wait" },
  completed: { label: "Completed", tone: "ok" },
  no_match: { label: "No match", tone: "quiet" },
  needs_human: { label: "Needs you", tone: "attention" },
  paused: { label: "Paused", tone: "quiet" },
  stopped: { label: "Stopped", tone: "bad" },
  failed: { label: "Failed", tone: "bad" },
};

export const CONVERSATION_STATE: Record<ConversationState, { label: string; tone: Tone }> = {
  researching: { label: "Researching", tone: "info" },
  qualified: { label: "Qualified", tone: "info" },
  drafting: { label: "Drafting", tone: "info" },
  waiting_reply: { label: "Waiting for reply", tone: "wait" },
  evaluating_reply: { label: "Reading reply", tone: "info" },
  offering_slots: { label: "Offering slots", tone: "info" },
  waiting_slot_acceptance: { label: "Waiting for slot choice", tone: "wait" },
  booking: { label: "Booking", tone: "info" },
  booked: { label: "Booked", tone: "ok" },
  completed: { label: "Completed", tone: "ok" },
  declined: { label: "Declined", tone: "quiet" },
  suppressed: { label: "Opted out", tone: "bad" },
  needs_human: { label: "Needs you", tone: "attention" },
  send_unknown: { label: "Send outcome unknown", tone: "attention" },
  stopped: { label: "Stopped", tone: "bad" },
};

export function StatusChip({ tone, children, className }: { tone: Tone; children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border px-2 text-2xs font-medium whitespace-nowrap transition-colors duration-150",
        toneClass[tone],
        className,
      )}
    >
      <span aria-hidden className={cn("size-1.5 rounded-full", dotClass[tone])} />
      {children}
    </span>
  );
}

export function CampaignStatus({ status, className }: { status: CampaignState; className?: string }) {
  const meta = CAMPAIGN_STATUS[status];
  return (
    <StatusChip tone={meta.tone} className={className}>
      {meta.label}
    </StatusChip>
  );
}

export function ConversationStatus({ state }: { state: ConversationState }) {
  const meta = CONVERSATION_STATE[state];
  return <StatusChip tone={meta.tone}>{meta.label}</StatusChip>;
}
