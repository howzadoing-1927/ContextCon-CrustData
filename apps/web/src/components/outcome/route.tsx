import type { CampaignState, ConversationState, ConversationView } from "@/lib/contracts";
import { cn } from "@/lib/utils";

export const STATIONS: { state: ConversationState; label: string; waiting?: boolean }[] = [
  { state: "researching", label: "Research" },
  { state: "qualified", label: "Qualified" },
  { state: "drafting", label: "Draft and verify" },
  { state: "waiting_reply", label: "Awaiting reply", waiting: true },
  { state: "evaluating_reply", label: "Read reply" },
  { state: "offering_slots", label: "Offer slots" },
  { state: "waiting_slot_acceptance", label: "Awaiting slot choice", waiting: true },
  { state: "booking", label: "Book" },
  { state: "booked", label: "Booked, read back" },
  { state: "completed", label: "Handoff written" },
];

const TERMINAL: Partial<Record<ConversationState | CampaignState, { label: string; tone: "bad" | "attention" | "quiet" }>> = {
  declined: { label: "Buyer declined", tone: "quiet" },
  suppressed: { label: "Opted out, suppressed", tone: "bad" },
  needs_human: { label: "Needs you", tone: "attention" },
  send_unknown: { label: "Send outcome unknown", tone: "attention" },
  stopped: { label: "Stopped", tone: "bad" },
  no_match: { label: "No match", tone: "quiet" },
  failed: { label: "Failed", tone: "bad" },
};

export interface RoutePosition {
  /** Index of the current or last-passed station. -1 before research starts. */
  index: number;
  terminal: { label: string; tone: "bad" | "attention" | "quiet" } | null;
  waiting: boolean;
  active: boolean;
  paused: boolean;
}

function branchIndex(conversation: ConversationView): number {
  const sent = conversation.messages.filter((m) => m.direction === "outbound" && m.status === "sent").length;
  const inbound = conversation.messages.filter((m) => m.direction === "inbound").length;
  if (conversation.booking) return 8;
  if (conversation.offered_slots.length && inbound >= 2) return 6;
  if (inbound >= 1) return conversation.offered_slots.length ? 6 : 4;
  if (sent >= 1) return 3;
  return 2;
}

export function routePosition(status: CampaignState, conversation: ConversationView | null): RoutePosition {
  const paused = status === "paused";
  if (!conversation) {
    const terminal = TERMINAL[status] ?? null;
    if (terminal) return { index: 0, terminal, waiting: false, active: false, paused };
    return { index: status === "draft" ? -1 : 0, terminal: null, waiting: false, active: status === "running", paused };
  }
  const terminal = TERMINAL[conversation.state] ?? null;
  if (terminal) return { index: branchIndex(conversation), terminal, waiting: false, active: false, paused };
  const index = STATIONS.findIndex((s) => s.state === conversation.state);
  const station = STATIONS[index];
  return {
    index,
    terminal: null,
    waiting: Boolean(station?.waiting) && !paused,
    active: !station?.waiting && conversation.state !== "completed" && status === "running",
    paused,
  };
}

const terminalTone = {
  bad: "border-bad text-bad",
  attention: "border-signal text-signal",
  quiet: "border-faint text-muted-foreground",
};

export function MissionRoute({ position, className }: { position: RoutePosition; className?: string }) {
  const { index, terminal, waiting, active, paused } = position;
  return (
    <ol aria-label="Mission route" className={cn("relative flex flex-col", className)}>
      {STATIONS.map((station, i) => {
        const passed = i < index || (i === index && (station.state === "completed" || terminal !== null));
        const current = i === index && !terminal && station.state !== "completed";
        const reached = i <= index;
        const isLast = i === STATIONS.length - 1;
        const branchHere = terminal !== null && i === index;
        return (
          <li key={station.state} className="relative grid grid-cols-[1.25rem_1fr] gap-x-2.5">
            {!isLast && (
              <span
                aria-hidden
                className={cn(
                  "absolute top-[1.125rem] bottom-[-0.375rem] left-[0.625rem] w-px -translate-x-1/2",
                  i < index && !(terminal && i >= index) ? "bg-muted-foreground/70" : "border-l border-dashed border-hairline bg-transparent",
                )}
              />
            )}
            <span className="relative flex h-6 items-center justify-center">
              <span
                aria-hidden
                className={cn(
                  "relative z-10 rounded-full transition-all duration-200 ease-out-expo",
                  current
                    ? cn(
                        "size-3 border-2 border-signal",
                        waiting || paused ? "bg-background" : "bg-signal",
                        active && "station-active",
                      )
                    : passed
                      ? "size-2 bg-muted-foreground"
                      : "size-2 border border-faint bg-background",
                )}
              />
            </span>
            <div className="min-h-9 pb-3">
              <p
                className={cn(
                  "text-xs leading-6",
                  current ? "font-semibold text-foreground" : reached ? "text-muted-foreground" : "text-faint",
                )}
              >
                {station.label}
                {current && (
                  <span className="sr-only">
                    {" "}
                    (current{waiting ? ", waiting" : ""}
                    {paused ? ", paused" : ""})
                  </span>
                )}
              </p>
              {current && (waiting || paused) && (
                <p className="text-2xs text-signal">{paused ? "Paused here" : "Nothing running. Waiting on the buyer"}</p>
              )}
              {branchHere && terminal && (
                <div className="mt-1 flex items-center gap-2">
                  <span aria-hidden className="h-px w-4 bg-current text-faint" />
                  <span
                    className={cn(
                      "inline-flex h-6 items-center gap-1.5 rounded-sm border px-2 text-2xs font-semibold",
                      terminalTone[terminal.tone],
                    )}
                  >
                    <span aria-hidden className="size-1.5 rounded-full bg-current" />
                    {terminal.label}
                  </span>
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Compact horizontal route for list rows. */
export function MiniRoute({ position, className }: { position: RoutePosition; className?: string }) {
  const { index, terminal, active } = position;
  return (
    <span aria-hidden className={cn("inline-flex items-center", className)}>
      {STATIONS.map((station, i) => {
        const passed = i < index || (i === index && (terminal !== null || station.state === "completed"));
        const current = i === index && !terminal && station.state !== "completed";
        return (
          <span key={station.state} className="inline-flex items-center">
            {i > 0 && <span className={cn("h-px w-2.5", i <= index ? "bg-muted-foreground/70" : "bg-hairline")} />}
            <span
              className={cn(
                "rounded-full",
                current
                  ? cn("size-2 border border-signal", active ? "bg-signal" : "bg-background")
                  : passed
                    ? "size-1.5 bg-muted-foreground"
                    : "size-1.5 border border-hairline",
                terminal && i === index && (terminal.tone === "bad" ? "bg-bad" : terminal.tone === "attention" ? "bg-signal" : "bg-faint"),
              )}
            />
          </span>
        );
      })}
    </span>
  );
}

/** Narrow-width route: dots plus the current station and any terminal branch, spelled out. */
export function CompactRoute({ position, className }: { position: RoutePosition; className?: string }) {
  const { index, terminal, waiting, paused } = position;
  const station = STATIONS[Math.max(index, 0)];
  const status = index < 0 ? "Not started" : station.label;
  return (
    <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-1.5", className)}>
      <MiniRoute position={position} />
      <p className="text-xs">
        <span className="sr-only">Mission route: </span>
        <span className="font-medium text-foreground">{status}</span>
        {!terminal && (waiting || paused) && <span className="text-signal"> · {paused ? "paused" : "waiting on the buyer"}</span>}
      </p>
      {terminal && (
        <span className="flex items-center gap-2">
          <span aria-hidden className="h-px w-4 bg-current text-faint" />
          <span className={cn("inline-flex h-6 items-center gap-1.5 rounded-sm border px-2 text-2xs font-semibold", terminalTone[terminal.tone])}>
            <span aria-hidden className="size-1.5 rounded-full bg-current" />
            {terminal.label}
          </span>
        </span>
      )}
    </div>
  );
}
