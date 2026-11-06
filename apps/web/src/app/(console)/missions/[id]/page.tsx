"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { BookingReceiptView } from "@/components/mission/conversation";
import { ConversationThread } from "@/components/mission/conversation";
import { ExceptionDrawer, ExceptionStrip } from "@/components/mission/exceptions";
import { HandoffCard } from "@/components/mission/handoff";
import { MissionHeader } from "@/components/mission/header";
import { DecisionLedger, useLedger } from "@/components/mission/ledger";
import { FoundPeople, OutreachDrafts, ProspectCaseView, RejectedProspects } from "@/components/mission/prospect";
import { lastDecisionReason, nextExpected, StagePanel } from "@/components/mission/stage-panel";
import { ErrorState } from "@/components/outcome/error-state";
import { EvidenceProvider } from "@/components/outcome/evidence";
import { Notice } from "@/components/outcome/panel";
import { CompactRoute, MissionRoute, routePosition } from "@/components/outcome/route";
import { useNow } from "@/components/outcome/worker-health";
import { useWorkspace } from "@/components/outcome/workspace-context";
import { Skeleton } from "@/components/ui/skeleton";
import type { MissionDetail } from "@/lib/contracts";
import { useSession } from "@/lib/session";
import { useResource } from "@/lib/use-resource";

const SETTLED = new Set(["completed", "no_match", "stopped", "failed"]);

function Loading() {
  return (
    <div aria-busy="true" className="flex flex-1 flex-col">
      <div className="border-b border-hairline px-5 py-3">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="mt-2 h-5 w-[60%]" />
        <Skeleton className="mt-2 h-4 w-96" />
      </div>
      <div className="grid flex-1 grid-cols-[13.75rem_minmax(0,1fr)_23.75rem] gap-0">
        <div className="space-y-3 p-5">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-5" />
          ))}
        </div>
        <div className="space-y-4 border-x border-hairline p-5">
          <Skeleton className="h-48" />
          <Skeleton className="h-64" />
        </div>
        <div className="space-y-2 p-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      </div>
    </div>
  );
}

function Centre({ detail, sellerEmail, timeZone, now, refresh, lastReason }: {
  detail: MissionDetail;
  sellerEmail: string;
  timeZone: string;
  now: number;
  refresh: () => void;
  lastReason: string | null;
}) {
  const found = detail.prospects.filter((p) => p.person);
  const chosen = detail.prospects.find((p) => p.fit === "qualified") ?? detail.prospects.find((p) => p.fit !== "rejected") ?? null;
  const rejected = detail.prospects.filter((p) => p.fit === "rejected");
  const researching = !found.length && !SETTLED.has(detail.status) && detail.status !== "draft";

  return (
    <div className="min-w-0 px-6 pb-10">
      <div className="pt-5 empty:hidden">
        <StagePanel detail={detail} now={now} onRefresh={refresh} lastReason={lastReason} />
      </div>
      {detail.handoff && <HandoffCard handoff={detail.handoff} />}
      <FoundPeople prospects={found} />
      <OutreachDrafts prospects={detail.prospects} />
      {!found.length && chosen && <ProspectCaseView prospect={chosen} />}
      {researching && (
        <p className="border-b border-hairline py-5 text-sm text-muted-foreground">
          Researching. Candidates appear here as they are scored against the mission&apos;s must-haves.
        </p>
      )}
      <RejectedProspects prospects={rejected} />
      {detail.conversation && (
        <ConversationThread
          conversation={detail.conversation}
          sellerEmail={sellerEmail}
          timeZone={timeZone}
          campaignId={detail.id}
          onBuyerReply={refresh}
        />
      )}
      {!detail.conversation && detail.handoff && <BookingReceiptView booking={detail.handoff.booking} className="mt-4" />}
    </div>
  );
}

export default function MissionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { client, organizationId } = useSession();
  const { workspace } = useWorkspace();
  const [pollMs, setPollMs] = useState(2000);
  const mission = useResource(`mission:${organizationId}:${id}`, () => client.campaigns.get(id), { pollMs });
  const detail = mission.data;
  const now = useNow(1000);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [resolvedMessage, setResolvedMessage] = useState<string | null>(null);
  const signal = detail ? `${detail.last_decision_id}:${detail.version}:${detail.open_exceptions.length}` : "";
  const ledger = useLedger(id, signal);

  useEffect(() => {
    if (detail) setPollMs(SETTLED.has(detail.status) ? 15000 : 2000);
  }, [detail]);

  const hasExceptions = Boolean(detail?.open_exceptions.length);
  useEffect(() => {
    if (hasExceptions && window.location.hash === "#resolve") setDrawerOpen(true);
  }, [hasExceptions]);

  useEffect(() => {
    if (detail?.status) document.title = `${detail.status === "needs_human" ? "Needs you · " : ""}Mission · Outcome AI`;
  }, [detail?.status]);

  if (mission.loading && !detail) return <Loading />;
  if (!detail) {
    return (
      <div className="px-5">
        <ErrorState error={mission.error} onRetry={mission.refresh} />
      </div>
    );
  }

  const ws = workspace.data;
  const timeZone = ws?.timezone ?? "UTC";
  const canControl = ws?.viewer_role === "owner";
  const position = routePosition(detail.status, detail.conversation);
  const refresh = () => void mission.refresh();

  return (
    <EvidenceProvider evidence={detail.evidence}>
      <div className="flex flex-1 flex-col">
        <div className="flex items-center px-5 pt-3">
          <Link href="/missions" className="inline-flex items-center gap-1 text-2xs text-muted-foreground hover:text-foreground">
            <ArrowLeft aria-hidden className="size-3" />
            Missions
          </Link>
        </div>
        <MissionHeader
          detail={detail}
          limits={ws?.policy.limits ?? null}
          canControl={canControl}
          fetchedAt={mission.fetchedAt}
          stale={mission.error != null}
          now={now}
          onChanged={refresh}
        />
        <ExceptionStrip exceptions={detail.open_exceptions} onOpen={() => setDrawerOpen(true)} />
        {resolvedMessage && (
          <div className="px-5 pt-3">
            <Notice tone="info" title={resolvedMessage} actions={<button type="button" className="text-2xs underline" onClick={() => setResolvedMessage(null)}>Dismiss</button>} />
          </div>
        )}

        <div className="grid flex-1 grid-cols-[13.75rem_minmax(0,1fr)_23.75rem] max-xl:grid-cols-[13.75rem_minmax(0,1fr)] max-lg:grid-cols-1">
          <aside aria-label="Mission route" className="max-lg:hidden">
            <div className="sticky top-12 px-5 pt-5 pb-8">
              <MissionRoute position={position} />
              <div className="mt-4 border-t border-hairline pt-3">
                <p className="text-2xs text-faint">Next expected</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{nextExpected(detail)}</p>
              </div>
            </div>
          </aside>
          <div className="hidden border-b border-hairline px-5 py-3 max-lg:block">
            <CompactRoute position={position} />
            <p className="mt-1.5 text-2xs text-muted-foreground">Next: {nextExpected(detail)}</p>
          </div>

          <div className="min-w-0 border-l border-hairline max-lg:border-l-0">
            <Centre
              detail={detail}
              sellerEmail={ws?.connection?.account_email ?? "seller mailbox"}
              timeZone={timeZone}
              now={now}
              refresh={refresh}
              lastReason={lastDecisionReason(detail, ledger.items)}
            />
          </div>

          <aside
            aria-label="Decision ledger"
            className="border-l border-hairline bg-shell max-xl:col-span-2 max-xl:border-t max-xl:border-l-0 max-lg:col-span-1"
          >
            <div className="sticky top-12 max-h-[calc(100dvh-5.25rem)] overflow-y-auto max-xl:static max-xl:max-h-none">
              <DecisionLedger ledger={ledger} timeZone={timeZone} />
            </div>
          </aside>
        </div>
      </div>

      <ExceptionDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        detail={detail}
        canResolve={canControl}
        timeZone={timeZone}
        onResolved={(message) => {
          setDrawerOpen(false);
          setResolvedMessage(message);
          refresh();
          void ledger.retry();
        }}
      />
    </EvidenceProvider>
  );
}
