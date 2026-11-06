"use client";

import { FileText, Plus } from "lucide-react";
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
import type { CampaignCreate, OrganizationView } from "@/lib/contracts";
import { readiness } from "@/lib/readiness";
import { useSession } from "@/lib/session";
import { useMutation } from "@/lib/use-mutation";
import { cn } from "@/lib/utils";

const MAX = 4000;

function Summary({ workspace, versions }: { workspace: OrganizationView; versions: { profile: number; config: number } }) {
  const buyers = workspace.policy.consented_recipients.filter((r) => r.role === "buyer_test");
  const { limits, working_hours: hours } = workspace.policy;
  const rows: [string, React.ReactNode][] = [
    [
      "Sends to",
      buyers.length ? (
        <span key="to" className="block">
          {buyers.length > 1 && <span className="block text-muted-foreground">Rotates across {buyers.length} test inboxes</span>}
          {buyers.map((b, i) => (
            <span key={b.email} className="block font-mono text-2xs">
              {buyers.length > 1 ? `${i + 1}. ` : ""}
              {b.email}
            </span>
          ))}
        </span>
      ) : (
        <span key="to" className="text-signal">No consented inbox</span>
      ),
    ],
    ["Sends from", <span key="from" className="font-mono text-2xs">{workspace.connection?.account_email ?? "not connected"}</span>],
    ["Seller profile", versions.profile > 0 ? <span key="p" className="tabular">version {versions.profile}</span> : <span key="p" className="text-signal">Not approved</span>],
    ["Policy", versions.config > 0 ? <span key="c" className="tabular">version {versions.config}</span> : <span key="c" className="text-signal">Not saved</span>],
    ["Meeting", `${workspace.policy.duration_minutes} min, ${hours.start}–${hours.end} ${hours.timezone}`],
    [
      "Limits",
      <span key="l" className="tabular">
        Up to {limits.max_conversations} {limits.max_conversations === 1 ? "person" : "people"} · {limits.max_discovered} companies searched ·{" "}
        {limits.max_outbound_messages} emails per person · {limits.max_model_calls} model calls
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

function requestFromBrief(workspace: OrganizationView): string {
  const people = workspace.policy.limits.max_conversations;
  const reach = `Reach up to ${people} ${people === 1 ? "person" : "people"}, one decision maker per company.`;
  const icp = workspace.ideal_customer;
  if (!icp) {
    return `Find companies that would benefit from ${workspace.name}, reach their decision maker, explain the fit, and book a ${workspace.policy.duration_minutes}-minute call. ${reach} Don't assume a problem we can't verify.`;
  }
  const where = icp.regions.length ? ` in ${icp.regions.join(" or ")}` : "";
  const who = icp.buyer_roles.length ? icp.buyer_roles.join(" or ") : "the right decision maker";
  return [
    `Find ${icp.customer_type.charAt(0).toLowerCase()}${icp.customer_type.slice(1)}${where}, reach their ${who}, explain the fit, and book a ${workspace.policy.duration_minutes}-minute call.`,
    icp.criteria.length ? `Good fit: ${icp.criteria.join("; ")}.` : null,
    icp.exclusions.length ? `Skip: ${icp.exclusions.join("; ")}.` : null,
    icp.timeline ? `Timeline: ${icp.timeline}.` : null,
    reach,
    "Don't assume a problem we can't verify.",
  ]
    .filter(Boolean)
    .join(" ");
}

export default function NewMissionPage() {
  const router = useRouter();
  const { client } = useSession();
  const { workspace } = useWorkspace();
  const data = workspace.data;
  const [text, setText] = useState("");
  const [touched, setTouched] = useState(false);
  const [versions, setVersions] = useState<{ profile: number; config: number } | null>(null);
  const [writing, setWriting] = useState(false);
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
  const empty = trimmed.length === 0;
  const blockers = readiness(data).filter((i) => !i.done);
  const buyer = data.policy.consented_recipients.find((r) => r.role === "buyer_test");
  const readyMade = requestFromBrief(data);
  const canLaunch = data.viewer_role === "owner";
  const stale = data.profile_version !== versions.profile || data.policy.config_version !== versions.config;
  const error = create.error;
  const fieldError = touched && empty ? "Describe who to find and what meeting to book." : tooLong ? `Keep it under ${MAX} characters.` : null;
  const serverFieldError = isApiError(error) && error.code === "VALIDATION_FAILED" ? error.message : null;

  async function submit(request = trimmed) {
    setTouched(true);
    if (!request || request.length > MAX || !buyer || !versions) return;
    const result = await create.run({
      request_text: request,
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
          {!writing ? (
            <div className="flex flex-col gap-3">
              <p className="text-sm font-medium">Start a mission</p>
              <section className="rounded-lg border border-hairline bg-shell px-4 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold">Ready-made mission</h2>
                    <p className="mt-0.5 text-2xs text-muted-foreground">
                      Written from your brief and setup. Finds up to {data.policy.limits.max_conversations} real people and shows their real
                      email, but mails only your test inboxes.
                    </p>
                  </div>
                  <Button
                    type="button"
                    className="shrink-0"
                    disabled={create.pending || blockers.length > 0 || !canLaunch}
                    onClick={() => void submit(readyMade)}
                  >
                    {create.pending ? "Launching…" : "Launch this mission"}
                  </Button>
                </div>
                <p className="mt-3 rounded-md border border-hairline bg-background px-3 py-2 text-xs leading-relaxed text-foreground">{readyMade}</p>
                <button
                  type="button"
                  onClick={() => {
                    setText(readyMade);
                    setWriting(true);
                  }}
                  className="mt-2 text-2xs text-muted-foreground underline hover:text-foreground"
                >
                  Edit before launching
                </button>
              </section>
              <section className="flex items-center justify-between gap-4 rounded-lg border border-dashed border-hairline px-4 py-4">
                <div>
                  <h2 className="text-sm font-semibold">Write your own mission</h2>
                  <p className="mt-0.5 text-2xs text-muted-foreground">Describe who to find, what qualifies them, and what meeting to book.</p>
                </div>
                <Button type="button" variant="outline" className="shrink-0" onClick={() => setWriting(true)}>
                  <Plus data-icon="inline-start" />
                  Add a mission
                </Button>
              </section>
            </div>
          ) : (
            <>
              <div className="flex items-end justify-between gap-3">
                <label htmlFor={textId} className="text-sm font-medium">
                  What should the agent accomplish?
                </label>
                <Button type="button" variant="ghost" size="sm" onClick={() => setText(readyMade)} className="shrink-0">
                  <FileText data-icon="inline-start" />
                  {trimmed ? "Replace with the ready-made mission" : "Start from the ready-made mission"}
                </Button>
              </div>
              <Textarea
                id={textId}
                rows={9}
                value={text}
                autoFocus
                onChange={(e) => setText(e.target.value)}
                onBlur={() => setTouched(true)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    void submit();
                  }
                }}
                aria-invalid={Boolean(fieldError || serverFieldError) || undefined}
                aria-describedby={`${textId}-hint`}
                placeholder="Find a mid-market logistics company in India and its sales leader, explain the fit, and book a 15-minute demo. Don't assume a problem we can't verify."
                className="min-h-48 text-sm leading-relaxed placeholder:text-faint"
              />
              <div id={`${textId}-hint`} className="flex items-start justify-between gap-4 text-2xs">
                <p className={cn(fieldError || serverFieldError ? "text-bad" : "text-muted-foreground")}>
                  {fieldError ??
                    serverFieldError ??
                    "Who to find, what qualifies them, and what meeting to book. The agent asks for help instead of\u00a0guessing."}
                </p>
                <span className={cn("shrink-0 tabular", tooLong ? "text-bad" : "text-faint")}>
                  {text.length.toLocaleString("en-US")} / {MAX.toLocaleString("en-US")}
                </span>
              </div>
            </>
          )}

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

          {writing && (
            <div className="flex items-center justify-end gap-3 pt-1">
              <Button type="button" variant="ghost" onClick={() => setWriting(false)}>
                Back
              </Button>
              <span className="text-2xs text-faint">⌘ Enter to launch</span>
              <Button type="submit" size="lg" disabled={create.pending || blockers.length > 0 || !canLaunch || tooLong}>
                {create.pending ? "Launching…" : "Launch mission"}
              </Button>
            </div>
          )}
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
