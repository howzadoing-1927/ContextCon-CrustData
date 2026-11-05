"use client";

import { createContext, useContext } from "react";
import type { HealthReady, OrganizationView } from "@/lib/contracts";
import { isApiError } from "@/lib/api/errors";
import { useSession } from "@/lib/session";
import { type Resource, useResource } from "@/lib/use-resource";

interface WorkspaceContextValue {
  workspace: Resource<OrganizationView>;
  health: { data: HealthReady | null; fetchedAt: number | null; unreachable: boolean };
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { client, organizationId, accessToken } = useSession();
  const key = accessToken && organizationId ? `workspace:${organizationId}` : null;
  const workspace = useResource(key, () => client.workspace.get(), { pollMs: 15000 });
  const health = useResource(key ? "health" : null, () => client.health.ready(), { pollMs: 10000 });

  const healthData: HealthReady | null =
    health.data ??
    (isApiError(health.error) && health.error.details && "worker" in health.error.details
      ? (health.error.details as unknown as HealthReady)
      : null);

  return (
    <WorkspaceContext.Provider
      value={{
        workspace,
        health: {
          data: healthData,
          fetchedAt: health.fetchedAt ?? (health.error ? Date.now() : null),
          unreachable: isApiError(health.error) && health.error.code === "NETWORK",
        },
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return value;
}
