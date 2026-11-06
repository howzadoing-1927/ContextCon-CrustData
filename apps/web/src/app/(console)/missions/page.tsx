"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { ErrorState } from "@/components/outcome/error-state";
import { EmptyState } from "@/components/outcome/panel";
import { CampaignStatus } from "@/components/outcome/status";
import { useNow } from "@/components/outcome/worker-health";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { CampaignView } from "@/lib/contracts";
import { humanize, relativeAge } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useResource } from "@/lib/use-resource";

function Row({ campaign, now }: { campaign: CampaignView; now: number }) {
  return (
    <tr className="group relative border-b border-hairline transition-colors duration-150 hover:bg-raised">
      <td className="py-3 pr-4 pl-5 align-top">
        <CampaignStatus status={campaign.status} />
      </td>
      <td className="py-3 pr-6 align-top">
        <Link
          href={`/missions/${campaign.id}`}
          className="line-clamp-2 text-sm text-foreground after:absolute after:inset-0 focus-visible:outline-none"
        >
          {campaign.request_text}
        </Link>
        <p className="mt-1 text-2xs text-faint">Stage: {humanize(campaign.stage)}</p>
      </td>
      <td className="py-3 pr-6 text-right align-top font-mono text-2xs text-muted-foreground tabular">
        {campaign.usage.outbound_attempts} sent · {campaign.usage.model_calls} model
      </td>
      <td className="py-3 pr-5 text-right align-top text-2xs text-muted-foreground tabular whitespace-nowrap">
        <time dateTime={campaign.updated_at} title={campaign.updated_at}>
          {relativeAge(Date.parse(campaign.updated_at), now)}
        </time>
      </td>
    </tr>
  );
}

export default function MissionsPage() {
  const { client, organizationId } = useSession();
  const missions = useResource(`missions:${organizationId}`, () => client.campaigns.list(null, 50), { pollMs: 5000 });
  const now = useNow(5000);
  const items = missions.data?.items ?? [];
  const attention = items.filter((c) => c.status === "needs_human").length;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Missions</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {missions.loading
              ? "Loading…"
              : missions.error && !missions.data
                ? "Unavailable"
                : `${items.length} mission${items.length === 1 ? "" : "s"}${attention ? ` · ${attention} need${attention === 1 ? "s" : ""} you` : ""}`}
          </p>
        </div>
        <Link href="/missions/new" className={buttonVariants()}>
          <Plus data-icon="inline-start" />
          New mission
        </Link>
      </div>

      <div className="mt-6">
        {missions.loading ? (
          <div className="space-y-2" aria-busy="true">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : missions.error && !missions.data ? (
          <ErrorState error={missions.error} onRetry={missions.refresh} />
        ) : items.length === 0 ? (
          <EmptyState
            title="No missions yet"
            action={
              <Link href="/missions/new" className={buttonVariants()}>
                Add a mission
              </Link>
            }
          >
            A mission is a plain-language request, such as “find a logistics company&apos;s sales leader in India and book a 15-minute demo.” The worker
            researches, emails the consented test inbox, reads the reply and books. You step in only for exceptions.
          </EmptyState>
        ) : (
          <div className="overflow-hidden rounded-lg border border-hairline">
            <table className="w-full table-fixed border-collapse text-left">
              <caption className="sr-only">Missions in this organization, newest first</caption>
              <colgroup>
                <col className="w-48" />
                <col />
                <col className="w-44" />
                <col className="w-28" />
              </colgroup>
              <thead className="bg-shell text-2xs text-faint">
                <tr className="border-b border-hairline">
                  <th scope="col" className="py-2 pr-4 pl-5 font-medium">
                    Status
                  </th>
                  <th scope="col" className="py-2 pr-6 font-medium">
                    Request
                  </th>
                  <th scope="col" className="py-2 pr-6 text-right font-medium">
                    Usage
                  </th>
                  <th scope="col" className="py-2 pr-5 text-right font-medium">
                    Updated
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((campaign) => (
                  <Row key={campaign.id} campaign={campaign} now={now} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
