"use client";

import { Check } from "lucide-react";
import Link from "next/link";
import { Suspense, useEffect } from "react";
import { ErrorState } from "@/components/outcome/error-state";
import { EvidenceProvider } from "@/components/outcome/evidence";
import { Notice } from "@/components/outcome/panel";
import { useWorkspace } from "@/components/outcome/workspace-context";
import { GoogleSection } from "@/components/setup/google";
import { PolicySection } from "@/components/setup/policy";
import { ProfileSection } from "@/components/setup/profile";
import { SourcesSection } from "@/components/setup/sources";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { readiness } from "@/lib/readiness";
import { cn } from "@/lib/utils";

function SetupContent() {
  const { workspace } = useWorkspace();
  const data = workspace.data;
  const ingesting = data?.sources.some((s) => s.status === "ingesting") ?? false;

  const { refresh: refetch } = workspace;
  useEffect(() => {
    if (!ingesting) return;
    const timer = setInterval(() => void refetch(), 1500);
    return () => clearInterval(timer);
  }, [ingesting, refetch]);

  if (workspace.loading && !data) {
    return (
      <div className="grid grid-cols-[14rem_1fr] gap-10" aria-busy="true">
        <Skeleton className="h-48" />
        <div className="space-y-4">
          <Skeleton className="h-40" />
          <Skeleton className="h-72" />
        </div>
      </div>
    );
  }
  if (!data) return <ErrorState error={workspace.error} onRetry={workspace.refresh} />;

  const canEdit = data.viewer_role === "owner";
  const items = readiness(data);
  const done = items.filter((i) => i.done).length;
  const refresh = () => void workspace.refresh();

  return (
    <div className="grid grid-cols-[14rem_minmax(0,1fr)] gap-10 max-[1100px]:grid-cols-1 max-[1100px]:gap-6">
      <aside className="max-[1100px]:static sticky top-20 self-start">
        <p className="text-xs font-medium">
          Ready to launch <span className="text-muted-foreground tabular">{done}/4</span>
        </p>
        <ol className="mt-3 flex flex-col gap-0.5 max-[1100px]:grid max-[1100px]:grid-cols-4 max-[1100px]:gap-2">
          {items.map((item) => (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                className="group flex items-start gap-2.5 rounded-md px-2 py-1.5 transition-colors duration-150 hover:bg-raised"
              >
                <span
                  aria-hidden
                  className={cn(
                    "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border",
                    item.done ? "border-ok bg-ok/15 text-ok" : "border-faint",
                  )}
                >
                  {item.done && <Check className="size-2.5" strokeWidth={3} />}
                </span>
                <span className="min-w-0">
                  <span className={cn("block text-xs", item.done ? "text-muted-foreground" : "text-foreground")}>
                    {item.label}
                    <span className="sr-only">{item.done ? ", done" : ", to do"}</span>
                  </span>
                  <span className="block truncate text-2xs text-faint">{item.detail}</span>
                </span>
              </a>
            </li>
          ))}
        </ol>
        {done === 4 && (
          <Link href="/missions/new" className={cn(buttonVariants({ size: "sm" }), "mt-4 w-full")}>
            Write a mission
          </Link>
        )}
      </aside>

      <div className="min-w-0">
        {!canEdit && (
          <Notice tone="info" className="mb-2" title="You're a member of this organization">
            Only owners can change setup. You can see everything an owner sees.
          </Notice>
        )}
        <EvidenceProvider evidence={data.evidence}>
          <SourcesSection workspace={data} canEdit={canEdit} onChanged={refresh} />
          <ProfileSection workspace={data} canEdit={canEdit} onChanged={refresh} />
          <GoogleSection workspace={data} canEdit={canEdit} onChanged={refresh} />
          <PolicySection workspace={data} canEdit={canEdit} onChanged={refresh} />
        </EvidenceProvider>
      </div>
    </div>
  );
}

export default function SetupPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8">
      <h1 className="text-xl font-semibold tracking-tight">Setup</h1>
      <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
        What the agent may say, which mailbox and calendar it uses, and who it may email. Missions can launch once all four are done.
      </p>
      <div className="mt-8">
        <Suspense>
          <SetupContent />
        </Suspense>
      </div>
    </div>
  );
}
