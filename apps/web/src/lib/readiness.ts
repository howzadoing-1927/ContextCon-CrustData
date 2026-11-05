import type { OrganizationView } from "@/lib/contracts";
import { REQUIRED_GOOGLE_SCOPES } from "@/lib/contracts";

export interface ReadinessItem {
  id: "sources" | "profile" | "google" | "policy";
  label: string;
  done: boolean;
  detail: string;
}

export function readiness(workspace: OrganizationView): ReadinessItem[] {
  const granted = new Set(workspace.connection?.granted_scopes ?? []);
  const scopesOk = REQUIRED_GOOGLE_SCOPES.every((s) => granted.has(s));
  const buyer = workspace.policy.consented_recipients.find((r) => r.role === "buyer_test");
  const ready = workspace.sources.filter((s) => s.status === "ready").length;
  return [
    {
      id: "sources",
      label: "Seller sources",
      done: ready > 0,
      detail: ready ? `${ready} ready` : "Add a website or notes",
    },
    {
      id: "profile",
      label: "Profile approved",
      done: workspace.profile_version > 0 && workspace.approved_facts.length > 0,
      detail:
        workspace.profile_version > 0
          ? `v${workspace.profile_version} · ${workspace.approved_facts.length} facts`
          : "Approve at least one fact",
    },
    {
      id: "google",
      label: "Google connected",
      done: workspace.connection?.status === "connected" && scopesOk,
      detail: !workspace.connection
        ? "Not connected"
        : workspace.connection.status === "connected"
          ? scopesOk
            ? "All four scopes"
            : "Scopes missing"
          : workspace.connection.status.replace("_", " "),
    },
    {
      id: "policy",
      label: "Test inbox consented",
      done: Boolean(buyer && workspace.policy.config_version > 0 && workspace.policy.selected_calendar_id),
      detail: buyer ? buyer.email : "Add the buyer test inbox",
    },
  ];
}
