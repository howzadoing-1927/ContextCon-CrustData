"use client";

import { Unplug } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useWorkspace } from "./workspace-context";

/** One line under the top bar when something outside the mission blocks progress. */
export function SystemBanner() {
  const { health, workspace } = useWorkspace();
  const pathname = usePathname();
  const data = health.data;
  const connection = workspace.data?.connection;

  let message: React.ReactNode = null;
  if (health.unreachable) {
    message = "Can't reach the Outcome API. What's on screen is the last good state; it updates again when the API is back.";
  } else if (data?.database === "error") {
    message = "The database isn't responding. Missions resume from their last saved step when it recovers.";
  } else if (data && data.worker !== "fresh") {
    message =
      data.worker === "missing"
        ? "No worker is running. Missions won't advance until one starts; nothing is lost."
        : `The worker's last heartbeat was ${data.last_seen_age_seconds ?? "an unknown number of"} seconds ago. Missions may not advance until it recovers.`;
  } else if (connection && (connection.status === "reauth_required" || connection.status === "revoked") && !pathname.startsWith("/setup")) {
    message = (
      <>
        The seller&apos;s Google connection needs reauthorization. Sending, reading and booking are blocked.{" "}
        <Link href="/setup#google" className="underline">
          Reconnect in Setup
        </Link>
      </>
    );
  }

  if (!message) return null;
  return (
    <div role="status" className="flex items-center gap-2.5 border-b border-signal/35 bg-signal/8 px-5 py-2 text-xs">
      <Unplug aria-hidden className="size-3.5 shrink-0 text-signal" />
      <p>{message}</p>
    </div>
  );
}
