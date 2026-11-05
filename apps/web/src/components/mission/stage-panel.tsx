"use client";

import { Hourglass, Inbox } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Notice } from "@/components/outcome/panel";
import { useWorkspace } from "@/components/outcome/workspace-context";
import { Button } from "@/components/ui/button";
import { describeError } from "@/lib/api/errors";
import type { DecisionView, MissionDetail } from "@/lib/contracts";
import { relativeAge } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useMutation } from "@/lib/use-mutation";

export function nextExpected(detail: MissionDetail): string {
  const conv = detail.conversation;
  if (detail.status === "paused") return "Nothing until an owner resumes.";
  if (detail.status === "needs_human") return "Your decision on the open exception.";
  if (detail.status === "draft") return "The worker picks up the mission.";
  if (detail.status === "completed") return "Nothing. The mission is complete.";
  if (detail.status === "no_match" || detail.status === "failed" || detail.status === "stopped") return "Nothing. The mission has ended.";
  if (!conv) return "Research finishes: a prospect qualifies, or none match.";
  switch (conv.state) {
    case "researching":
      return "Research finishes: a prospect qualifies, or none match.";
    case "qualified":
    case "drafting":
      return "The draft passes verification, then goes to the test inbox.";
    case "waiting_reply":
      return "The buyer replies in the test inbox.";
    case "evaluating_reply":
      return "The reply is classified and the next step chosen.";
    case "offering_slots":
      return "Free times are checked and offered.";
    case "waiting_slot_acceptance":
      return "The buyer picks one of the offered times.";
    case "booking":
      return "The event is created and read back.";
    case "booked":
      return "The handoff is written.";
    default:
      return "Nothing. The conversation has ended.";
  }
}

function lastOutboundAt(detail: MissionDetail): number | null {
  const sent = detail.conversation?.messages.filter((m) => m.direction === "outbound" && m.sent_at) ?? [];
  const last = sent.at(-1)?.sent_at;
  return last ? Date.parse(last) : null;
}

function WaitingPanel({ detail, now, onPolled }: { detail: MissionDetail; now: number; onPolled: () => void }) {
  const { client } = useSession();
  const [queuedAt, setQueuedAt] = useState<number | null>(null);
  const poll = useMutation("poll", (_: void, key: string) => client.campaigns.poll(detail.id, key));
  const slot = detail.conversation?.state === "waiting_slot_acceptance";

  return (
    <div className="flex items-start gap-3 rounded-lg border border-hairline bg-shell px-4 py-3.5">
      <Hourglass aria-hidden className="mt-0.5 size-4 shrink-0 text-signal" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{slot ? "Waiting for the buyer to pick a time" : "Waiting for the buyer to reply"}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Nothing is running. The worker checks the test inbox on a schedule; last email sent {relativeAge(lastOutboundAt(detail), now)}.
          {slot && " A preference like “Thursday afternoon” isn't an acceptance; it comes back to you instead of being booked."}
        </p>
        {queuedAt && !poll.error && (
          <p role="status" className="mt-1.5 text-2xs text-muted-foreground">
            Inbox check queued {relativeAge(queuedAt, now)}. New mail appears in the thread and the ledger.
          </p>
        )}
        {poll.error != null && <p className="mt-1.5 text-2xs text-bad">{describeError(poll.error).title}</p>}
      </div>
      <Button
        size="sm"
        variant="outline"
        disabled={poll.pending}
        onClick={async () => {
          const result = await poll.run();
          if (result) {
            setQueuedAt(Date.now());
            onPolled();
          }
        }}
      >
        <Inbox data-icon="inline-start" />
        {poll.pending ? "Queuing…" : "Check inbox now"}
      </Button>
    </div>
  );
}

export function lastDecisionReason(detail: MissionDetail, ledger: DecisionView[] | null): string | null {
  return ledger?.find((d) => d.id === detail.last_decision_id)?.reason ?? ledger?.at(-1)?.reason ?? null;
}

export function StagePanel({
  detail,
  now,
  onRefresh,
  lastReason,
}: {
  detail: MissionDetail;
  now: number;
  onRefresh: () => void;
  lastReason: string | null;
}) {
  const { health } = useWorkspace();
  const conv = detail.conversation;
  const workerDown = health.data && health.data.worker !== "fresh";

  if (detail.status === "paused") {
    return (
      <Notice tone="quiet" title="Paused">
        Nothing new starts until an owner resumes. Anything that was in flight when you paused has finished.
      </Notice>
    );
  }
  if (detail.status === "draft") {
    return workerDown ? (
      <Notice tone="attention" title="Queued, but the worker isn't reporting">
        This mission starts once the worker heartbeat is fresh again. Nothing is lost.
      </Notice>
    ) : (
      <Notice tone="quiet" title="Queued">
        The worker picks this up within a few seconds and starts by planning the search.
      </Notice>
    );
  }
  if (detail.status === "no_match") {
    return (
      <Notice
        tone="quiet"
        title="No prospect passed every must-have"
        actions={
          <Link href="/missions/new" className="text-xs underline">
            New mission
          </Link>
        }
      >
        {lastReason ?? "No candidate within the discovery limit qualified."} Nothing was sent.
      </Notice>
    );
  }
  if (detail.status === "failed") {
    return (
      <Notice tone="bad" title="The mission failed">
        {lastReason ?? "A step failed after its retries."}
      </Notice>
    );
  }
  if (conv?.state === "declined") {
    return (
      <Notice tone="quiet" title="The buyer declined">
        No follow-up is sent and no meeting is booked.
      </Notice>
    );
  }
  if (conv?.state === "suppressed") {
    return (
      <Notice tone="bad" title="The buyer opted out">
        This email, company and person are suppressed across the organization. Nothing more will be sent to them.
      </Notice>
    );
  }
  if (detail.status === "stopped") {
    return (
      <Notice tone="quiet" title="Stopped">
        {lastReason ?? "An owner stopped this mission."}
      </Notice>
    );
  }
  if ((conv?.state === "waiting_reply" || conv?.state === "waiting_slot_acceptance") && detail.status !== "needs_human") {
    return <WaitingPanel detail={detail} now={now} onPolled={onRefresh} />;
  }
  return null;
}
