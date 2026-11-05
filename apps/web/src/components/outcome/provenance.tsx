import { FlaskConical, History, Radio, VenetianMask } from "lucide-react";
import type { ExecutionLabel } from "@/lib/contracts";
import { cn } from "@/lib/utils";

const META: Record<ExecutionLabel, { label: string; className: string; Icon: typeof Radio; title: string }> = {
  LIVE: {
    label: "Live",
    className: "bg-live text-[oklch(0.2_0.04_158)] border-live",
    Icon: Radio,
    title: "Executed against the real provider",
  },
  CACHED: {
    label: "Cached",
    className: "text-cached border-cached/70",
    Icon: History,
    title: "Replayed from a stored provider response",
  },
  FIXTURE: {
    label: "Fixture",
    className: "text-fixture border-dashed border-fixture/80",
    Icon: FlaskConical,
    title: "Local fixture data. Never counts as live execution",
  },
  SIMULATED_BUYER: {
    label: "Simulated buyer",
    className: "text-simbuyer border-simbuyer/70",
    Icon: VenetianMask,
    title: "A consenting teammate's test inbox is playing the buyer",
  },
};

export function ProvenanceStamp({ kind, className }: { kind: ExecutionLabel; className?: string }) {
  const meta = META[kind];
  return (
    <span
      title={meta.title}
      className={cn(
        "inline-flex h-5 shrink-0 items-center gap-1 border px-1.5 text-[0.6875rem] leading-none font-semibold tracking-[0.06em] uppercase",
        meta.className,
        className,
      )}
    >
      <meta.Icon aria-hidden className="size-3" strokeWidth={2.25} />
      {meta.label}
    </span>
  );
}

export function ModeBadge({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-sm whitespace-nowrap border border-hairline bg-raised px-2 text-2xs font-medium text-foreground",
        className,
      )}
    >
      <Radio aria-hidden className="size-3 text-live" />
      {compact ? <span className="sr-only">Live tools,</span> : "Live tools"}
      {!compact && (
        <span aria-hidden className="text-faint">
          ·
        </span>
      )}
      <VenetianMask aria-hidden className="size-3 text-simbuyer" />
      {compact ? "Simulated buyer" : "simulated buyer"}
    </span>
  );
}
