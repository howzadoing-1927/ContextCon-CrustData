"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { formatInstant, shortId } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Machine identifier: truncated, full value on hover, copyable. */
export function MonoId({
  value,
  length = 8,
  className,
  copy = true,
}: {
  value: string | null | undefined;
  length?: number;
  className?: string;
  copy?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  if (!value) return <span className={cn("font-mono text-2xs text-faint", className)}>none</span>;
  return (
    <span className={cn("group/id inline-flex min-w-0 items-center gap-1 font-mono text-2xs text-muted-foreground", className)}>
      <span title={value} className="truncate">
        {shortId(value, length)}
      </span>
      {copy && (
        <button
          type="button"
          aria-label={`Copy ${value}`}
          onClick={() => {
            void navigator.clipboard?.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          }}
          className="rounded-sm p-0.5 text-faint opacity-60 transition-opacity duration-150 group-hover/id:opacity-100 hover:text-foreground focus-visible:opacity-100"
        >
          {copied ? <Check className="size-3 text-ok" /> : <Copy className="size-3" />}
        </button>
      )}
    </span>
  );
}

/** RFC3339 instant shown in a zone, with UTC on hover. */
export function Instant({
  value,
  timeZone = "UTC",
  className,
}: {
  value: string | null | undefined;
  timeZone?: string;
  className?: string;
}) {
  if (!value) return <span className={cn("font-mono text-2xs text-faint", className)}>unknown</span>;
  return (
    <time dateTime={value} title={`${value} (UTC)`} className={cn("font-mono text-2xs text-muted-foreground", className)}>
      {formatInstant(value, timeZone)}
    </time>
  );
}

export function KeyValue({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex min-w-0 items-baseline justify-between gap-3 py-1", className)}>
      <dt className="shrink-0 text-2xs text-faint">{label}</dt>
      <dd className="min-w-0 truncate text-right text-xs">{children}</dd>
    </div>
  );
}
