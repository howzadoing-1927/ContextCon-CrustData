"use client";

import { ChevronRight } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { ErrorState } from "@/components/outcome/error-state";
import { EmptyState } from "@/components/outcome/panel";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/lib/session";
import { useResource } from "@/lib/use-resource";

function OrgPicker() {
  const { ready, accessToken, email, client, selectOrganization, signOut } = useSession();
  const router = useRouter();
  const nextParam = useSearchParams().get("next");
  const next = nextParam && nextParam.startsWith("/") && !nextParam.startsWith("//") ? nextParam : "/missions";
  const memberships = useResource(accessToken ? `memberships:${accessToken.slice(-8)}` : null, () => client.memberships.list());

  useEffect(() => {
    if (ready && !accessToken) router.replace("/signin");
  }, [ready, accessToken, router]);

  const items = memberships.data?.items ?? [];

  return (
    <div className="w-full max-w-md">
      <h1 className="text-xl font-semibold tracking-tight">Choose an organization</h1>
      <p className="mt-1.5 text-sm text-muted-foreground">
        Signed in as <span className="text-foreground">{email ?? "…"}</span>. Each organization keeps its own setup, missions and evidence.
      </p>

      <div className="mt-6">
        {memberships.loading ? (
          <div className="space-y-2" aria-busy="true">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : memberships.error ? (
          <ErrorState error={memberships.error} onRetry={memberships.refresh} />
        ) : items.length === 0 ? (
          <EmptyState title="You aren't a member of any organization">
            An owner has to add you before you can see setup or missions. Signing in alone doesn&apos;t grant access.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-hairline overflow-hidden rounded-lg border border-hairline bg-raised">
            {items.map((m) => (
              <li key={m.organization_id}>
                <button
                  type="button"
                  onClick={() => {
                    selectOrganization(m.organization_id);
                    router.replace(next);
                  }}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-accent focus-visible:bg-accent"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{m.organization_name}</span>
                    <span className="block text-2xs text-faint">
                      {m.role === "owner" ? "Owner: can change setup, launch and resolve" : "Member: read-only for setup and controls"}
                    </span>
                  </span>
                  <ChevronRight aria-hidden className="size-4 text-faint" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Button
        variant="ghost"
        size="sm"
        className="mt-6 text-muted-foreground"
        onClick={async () => {
          await signOut();
          router.replace("/signin");
        }}
      >
        Sign out
      </Button>
    </div>
  );
}

export default function OrgsPage() {
  return (
    <Suspense>
      <OrgPicker />
    </Suspense>
  );
}
