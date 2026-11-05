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
        <div className="flex h-12 items-center gap-6 px-5">
          <Link href="/missions" className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            <span aria-hidden className="grid size-5 place-items-center rounded-sm bg-signal text-[0.625rem] font-bold text-signal-foreground">
              O
            </span>
            Outcome AI
          </Link>
          <nav aria-label="Primary" className="flex h-full items-stretch gap-1">
            {NAV.map((item) => {
              const active = item.match(pathname);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "relative flex items-center px-2.5 text-xs transition-colors duration-150",
                    active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item.label}
                  {active && <span aria-hidden className="absolute inset-x-2.5 bottom-0 h-0.5 rounded-full bg-signal" />}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {mode === "FIXTURE" && <ProvenanceStamp kind="FIXTURE" />}
            <ModeBadge />
            <WorkerHealth />
            <span aria-hidden className="h-5 w-px bg-hairline" />
            <button
              type="button"
              onClick={() => {
                selectOrganization(null);
                router.push("/orgs");
              }}
              className="flex flex-col items-end text-right leading-tight"
              title="Switch organization"
            >
              <span className="text-xs font-medium">{workspace.data?.name ?? "Organization"}</span>
              <span className="text-2xs text-faint">
                {workspace.data?.viewer_role ?? "…"} · {email}
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
