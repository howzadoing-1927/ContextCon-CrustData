"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import { ErrorState } from "@/components/outcome/error-state";
import { Notice } from "@/components/outcome/panel";
import { ModeBadge } from "@/components/outcome/provenance";
import { useWorkspace } from "@/components/outcome/workspace-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { describeError, isApiError } from "@/lib/api/errors";
import type { CampaignCreate, IdealCustomer, OrganizationView } from "@/lib/contracts";
import { readiness } from "@/lib/readiness";
import { useSession } from "@/lib/session";
import { useMutation } from "@/lib/use-mutation";
import { cn } from "@/lib/utils";

const MAX = 4000;

function Summary({ workspace, versions }: { workspace: OrganizationView; versions: { profile: number; config: number } }) {
  const buyer = workspace.policy.consented_recipients.find((r) => r.role === "buyer_test");
  const { limits, working_hours: hours } = workspace.policy;
  const rows: [string, React.ReactNode][] = [
    ["Sends to", buyer ? <span className="font-mono text-2xs">{buyer.email}</span> : <span className="text-signal">No consented inbox</span>],
    ["Sends from", <span key="from" className="font-mono text-2xs">{workspace.connection?.account_email ?? "not connected"}</span>],
    ["Seller profile", versions.profile > 0 ? <span key="p" className="tabular">version {versions.profile}</span> : <span key="p" className="text-signal">Not approved</span>],
    ["Policy", versions.config > 0 ? <span key="c" className="tabular">version {versions.config}</span> : <span key="c" className="text-signal">Not saved</span>],
    ["Meeting", `${workspace.policy.duration_minutes} min, ${hours.start}–${hours.end} ${hours.timezone}`],
    [
      "Limits",
      <span key="l" className="tabular">
        {limits.max_discovered} discovered · {limits.max_enriched} enriched · {limits.max_outbound_messages} emails · {limits.max_model_calls} model calls ·{" "}
        {Math.round(limits.max_runtime_seconds / 60)} min
      </span>,
    ],
  ];
  return (
    <dl className="divide-y divide-hairline text-xs">
      {rows.map(([label, value]) => (
        <div key={label} className="grid grid-cols-[6.5rem_1fr] gap-3 py-2">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="min-w-0 break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function icpComplete(icp: IdealCustomer | null | undefined): icp is IdealCustomer {
  return Boolean(icp?.customer_type.trim() && icp.buyer_roles.some((role) => role.trim()) && icp.criteria.some((c) => c.trim()));
}

function requestFromBrief(workspace: OrganizationView, notes: string): string {
  const icp = workspace.ideal_customer!;
  const where = icp.regions.length ? ` in ${icp.regions.join(" or ")}` : "";
  const who = icp.buyer_roles.length ? icp.buyer_roles.join(" or ") : "the right decision maker";
  const targeting = [
    `Find ${icp.customer_type.charAt(0).toLowerCase()}${icp.customer_type.slice(1)}${where}, reach their ${who}, explain the fit, and book a ${workspace.policy.duration_minutes}-minute call.`,
    icp.criteria.length ? `Good fit: ${icp.criteria.join("; ")}.` : null,
    icp.exclusions.length ? `Skip: ${icp.exclusions.join("; ")}.` : null,
    "Don't assume a problem we can't verify.",
  ]
    .filter(Boolean)
    .join(" ");
  const extra = notes.trim();
  return extra ? `${targeting} Notes: ${extra}` : targeting;
}

function IcpLock({ icp }: { icp: IdealCustomer }) {
  const rows: [string, string][] = [
    ["Customer", icp.customer_type],
    ["Roles", icp.buyer_roles.join(", ")],
    ["Places", icp.regions.length ? icp.regions.join(", ") : "No place focus"],
    ["Fit", icp.criteria.join("; ")],
  ];
  if (icp.exclusions.length) rows.push(["Skip", icp.exclusions.join("; ")]);
  return (
    <div className="rounded-lg border border-hairline px-3.5 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-medium">Who we will find</h2>
        <Link href="/setup" className="text-2xs text-info underline">
          Edit brief
        </Link>
      </div>
      <p className="mt-0.5 text-2xs text-muted-foreground">From your brief. Notes below cannot change this.</p>
      <dl className="mt-2 divide-y divide-hairline text-xs">
        {rows.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[5.5rem_1fr] gap-3 py-1.5">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="min-w-0 text-pretty break-words">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default function NewMissionPage() {
  const router = useRouter();
  const { client } = useSession();
  const { workspace } = useWorkspace();
  const data = workspace.data;
  const [text, setText] = useState("");
  const [versions, setVersions] = useState<{ profile: number; config: number } | null>(null);
  const textId = useId();
  const create = useMutation("campaign", (input: CampaignCreate, key: string) => client.campaigns.create(input, key));

  useEffect(() => {
    if (data && !versions) setVersions({ profile: data.profile_version, config: data.policy.config_version });
  }, [data, versions]);

  if (workspace.loading && !data) {
    return (
      <div className="mx-auto w-full max-w-5xl px-5 py-8" aria-busy="true">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-6 h-64" />
      </div>
    );
  }
  if (!data || !versions) {
    return (
      <div className="mx-auto w-full max-w-5xl px-5 py-8">
        <ErrorState error={workspace.error} onRetry={workspace.refresh} />
      </div>
    );
  }

  const trimmed = text.trim();
  const tooLong = text.length > MAX;
  const blockers = readiness(data).filter((i) => !i.done);
  const buyer = data.policy.consented_recipients.find((r) => r.role === "buyer_test");
  const canLaunch = data.viewer_role === "owner";
  const hasIcp = icpComplete(data.ideal_customer);
  const stale = data.profile_version !== versions.profile || data.policy.config_version !== versions.config;
  const error = create.error;
  const fieldError = tooLong ? `Keep it under ${MAX} characters.` : null;
  const serverFieldError = isApiError(error) && error.code === "VALIDATION_FAILED" ? error.message : null;

  async function submit() {
    if (!hasIcp || tooLong || !buyer || !versions) return;
    const result = await create.run({
      request_text: requestFromBrief(data!, trimmed),
      mode: "simulation",
      buyer_test_email: buyer.email,
      profile_version: versions.profile,
      config_version: versions.config,
      limits: data!.policy.limits,
    });
    if (result) router.push(`/missions/${result.id}`);
  }

  function adoptLatest() {
    create.reset();
    setVersions({ profile: data!.profile_version, config: data!.policy.config_version });
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-5 py-8">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold tracking-tight">New mission</h1>
        <ModeBadge />
      </div>

      <div className="mt-6 grid grid-cols-[minmax(0,1fr)_22rem] gap-8 max-[1100px]:grid-cols-1">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          className="flex flex-col gap-3"
        >
          {hasIcp ? (
            <IcpLock icp={data.ideal_customer} />
          ) : (
            <Notice
              tone="attention"
              title="Tell us who you sell to first"
              actions={
                <Link href="/setup" className="text-xs text-signal underline">
                  Open setup
                </Link>
              }
            >
              Research uses the founder brief, not a guessed market. Add customer type, buyer roles, and fit criteria, then come back.
            </Notice>
          )}
          <div className="flex flex-col gap-1.5">
            <label htmlFor={textId} className="text-sm font-medium">
              Anything else for this run? <span className="font-normal text-faint">· optional</span>
            </label>
            <Textarea
              id={textId}
              rows={5}
              value={text}
              autoFocus={hasIcp}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  void submit();
                }
              }}
              aria-invalid={Boolean(fieldError || serverFieldError) || undefined}
              aria-describedby={`${textId}-hint`}
              placeholder="e.g. This week only. Do not change who we sell to."
              className="min-h-32 text-sm leading-relaxed placeholder:text-faint"
            />
            <div id={`${textId}-hint`} className="flex items-start justify-between gap-4 text-2xs">
              <p className={cn(fieldError || serverFieldError ? "text-bad" : "text-muted-foreground")}>
                {fieldError ??
                  serverFieldError ??
                  "Timing or extra context. This cannot change customer type, roles, or places from the brief."}
              </p>
              <span className={cn("shrink-0 tabular", tooLong ? "text-bad" : "text-faint")}>
                {text.length.toLocaleString("en-US")} / {MAX.toLocaleString("en-US")}
              </span>
            </div>
          </div>

          {blockers.length > 0 && (
            <Notice
              tone="attention"
              title="Setup isn't finished"
              actions={
                <Link href={`/setup#${blockers[0].id}`} className="text-xs text-signal underline">
                  Open setup
                </Link>
              }
            >
              Still to do: {blockers.map((b) => (b.id === "google" ? b.label : b.label.toLowerCase())).join(", ")}.
            </Notice>
          )}
          {!canLaunch && (
            <Notice tone="info" title="Only owners can launch missions">
              You can draft here, but an owner of {data.name} has to launch it.
            </Notice>
          )}
          {stale && !(isApiError(error) && error.code === "CONFLICT") && (
            <Notice
              tone="info"
              title="Setup changed since you opened this form"
              actions={
                <Button size="sm" variant="outline" type="button" onClick={adoptLatest}>
                  Use latest
                </Button>
              }
            >
              The mission would launch against profile v{versions.profile} and policy v{versions.config}, which are no longer current.
            </Notice>
          )}
          {error != null && !serverFieldError && (
            <Notice
              tone={isApiError(error) && error.code === "CONFLICT" ? "attention" : "bad"}
              title={describeError(error).title}
              actions={
                isApiError(error) && error.code === "CONFLICT" ? (
                  <Button size="sm" variant="outline" type="button" onClick={adoptLatest}>
                    Use latest setup
                  </Button>
                ) : isApiError(error) && (error.code === "RECIPIENT_NOT_ALLOWED" || error.code === "DOMAIN_INVALID") ? (
                  <Link href="/setup" className="text-xs underline">
                    Open setup
                  </Link>
                ) : undefined
              }
            >
              {describeError(error).body}
              {isApiError(error) && error.correlationId && (
                <span className="mt-1 block font-mono text-2xs text-faint">Correlation {error.correlationId}</span>
              )}
            </Notice>
          )}

          <div className="flex items-center justify-end gap-3 pt-1">
            <span className="text-2xs text-faint">⌘ Enter to launch</span>
            <Button type="submit" size="lg" disabled={create.pending || blockers.length > 0 || !canLaunch || !hasIcp || tooLong}>
              {create.pending ? "Launching…" : "Launch mission"}
            </Button>
          </div>
        </form>

        <aside aria-label="What this mission will use" className="self-start rounded-lg border border-hairline bg-shell px-4 py-3">
          <h2 className="text-sm font-semibold">Runs with</h2>
          <p className="mt-0.5 text-2xs text-muted-foreground">
            Real research and Google calls. The buyer is a consented test inbox, never the person researched.
          </p>
          <div className="mt-2">
            <Summary workspace={data} versions={versions} />
          </div>
        </aside>
      </div>
    </div>
  );
}
