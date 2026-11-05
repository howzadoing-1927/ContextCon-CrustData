"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useWorkspace } from "./workspace-context";

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

export function WorkerHealth() {
  const { health } = useWorkspace();
  const data = health.data;
  const label = health.unreachable
    ? "API unreachable"
    : !data
      ? "Worker: checking"
      : data.database === "error"
        ? "Database error"
        : data.worker === "fresh"
          ? `Worker live · ${data.last_seen_age_seconds ?? "?"} s`
          : data.worker === "stale"
            ? `Worker stale · ${data.last_seen_age_seconds ?? "?"} s`
            : data.worker === "missing"
              ? "Worker not running"
              : "Worker unknown";
  const healthy = data?.worker === "fresh" && data.database === "ok" && !health.unreachable;
  return (
    <span
      role="status"
      title="Worker heartbeat from /health/ready, checked every 10 s"
      className={cn("inline-flex items-center gap-1.5 text-2xs tabular", healthy ? "text-muted-foreground" : "font-medium text-signal")}
    >
      <span aria-hidden className={cn("size-1.5 rounded-full", healthy ? "bg-ok" : data ? "bg-signal" : "bg-faint")} />
      {label}
    </span>
  );
}
