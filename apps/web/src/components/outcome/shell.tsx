"use client";

import { LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { isApiError } from "@/lib/api/errors";
import { ErrorState } from "./error-state";
import { FixtureBar } from "./fixture-bar";
import { ModeBadge, ProvenanceStamp } from "./provenance";
import { SystemBanner } from "./system-banner";
import { WorkerHealth } from "./worker-health";
import { useWorkspace } from "./workspace-context";

const NAV = [
  { href: "/missions", label: "Missions", match: (p: string) => p === "/missions" || (p.startsWith("/missions/") && p !== "/missions/new") },
  { href: "/missions/new", label: "New mission", match: (p: string) => p === "/missions/new" },
  { href: "/setup", label: "Setup", match: (p: string) => p.startsWith("/setup") },
];

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { email, mode, signOut, selectOrganization } = useSession();
  const { workspace } = useWorkspace();
  const accessError =
    !workspace.data && isApiError(workspace.error) && (workspace.error.code === "UNAUTHENTICATED" || workspace.error.code === "FORBIDDEN")
      ? workspace.error
      : null;

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-signal focus:px-3 focus:py-1.5 focus:text-signal-foreground">
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-hairline bg-shell">
        <div className="flex h-12 items-center gap-6 px-5 max-md:h-auto max-md:flex-wrap max-md:gap-x-3 max-md:gap-y-0 max-md:px-3 max-md:pt-2">
          <Link href="/missions" className="flex shrink-0 items-center gap-2 text-sm font-semibold tracking-tight whitespace-nowrap">
            <span aria-hidden className="grid size-5 place-items-center rounded-sm bg-primary text-[0.625rem] font-bold text-primary-foreground">
              O
            </span>
            Outcome AI
          </Link>
          <nav aria-label="Primary" className="flex h-full items-stretch gap-1 max-md:order-last max-md:-ml-2.5 max-md:h-10 max-md:w-full">
            {NAV.map((item) => {
              const active = item.match(pathname);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "relative flex items-center px-2.5 text-xs whitespace-nowrap transition-colors duration-150",
                    active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item.label}
                  {active && <span aria-hidden className="absolute inset-x-2.5 bottom-0 h-0.5 rounded-full bg-foreground" />}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex min-w-0 items-center gap-3">
            {mode === "FIXTURE" && <ProvenanceStamp kind="FIXTURE" />}
            <ModeBadge className="max-xl:hidden" />
            <ModeBadge compact className="xl:hidden max-sm:hidden" />
            <WorkerHealth />
            <span aria-hidden className="h-5 w-px bg-hairline max-sm:hidden" />
            <button
              type="button"
              onClick={() => {
                selectOrganization(null);
                router.push("/orgs");
              }}
              className="flex min-w-0 flex-col items-end text-right leading-tight"
              title="Switch organization"
            >
              <span className="max-w-56 truncate text-xs font-medium max-sm:max-w-32">{workspace.data?.name ?? "Organization"}</span>
              <span className="max-w-64 truncate text-2xs text-faint">
                {workspace.data?.viewer_role ?? "…"}
                <span className="max-lg:hidden"> · {email}</span>
              </span>
            </button>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Sign out"
              onClick={async () => {
                await signOut();
                router.replace("/signin");
              }}
            >
              <LogOut />
            </Button>
          </div>
        </div>
      </header>
      <SystemBanner />
      <main id="main" className="flex flex-1 flex-col">
        {accessError ? (
          <div className="px-5">
            <ErrorState error={accessError} />
          </div>
        ) : (
          children
        )}
      </main>
      {mode === "FIXTURE" && <FixtureBar />}
    </div>
  );
}
