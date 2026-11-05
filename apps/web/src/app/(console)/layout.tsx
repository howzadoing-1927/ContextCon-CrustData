"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { ConsoleShell } from "@/components/outcome/shell";
import { WorkspaceProvider } from "@/components/outcome/workspace-context";
import { useSession } from "@/lib/session";

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const { ready, accessToken, organizationId } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!ready) return;
    if (!accessToken) router.replace(`/signin?next=${encodeURIComponent(pathname)}`);
    else if (!organizationId) router.replace(`/orgs?next=${encodeURIComponent(pathname)}`);
  }, [ready, accessToken, organizationId, pathname, router]);

  if (!ready || !accessToken || !organizationId) {
    return (
      <div className="flex min-h-dvh flex-col" aria-busy="true">
        <div className="h-12 border-b border-hairline bg-shell" />
        <div className="mx-auto w-full max-w-5xl space-y-3 p-8">
          <Skeleton className="h-6 w-64" />
          <Skeleton className="h-4 w-96" />
          <Skeleton className="h-32 w-full" />
        </div>
      </div>
    );
  }

  return (
    <WorkspaceProvider>
      <ConsoleShell>{children}</ConsoleShell>
    </WorkspaceProvider>
  );
}
