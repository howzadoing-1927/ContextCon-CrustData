"use client";

import { Check, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const STEP_MS = 170;

/** Reveals `total` fields one at a time once `active`; all at once under reduced motion. */
export function useReveal(total: number, active: boolean): number {
  const [revealed, setRevealed] = useState(0);
  useEffect(() => {
    if (!active) {
      setRevealed(0);
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setRevealed(total);
      return;
    }
    let n = 0;
    const timer = window.setInterval(() => {
      n += 1;
      setRevealed(n);
      if (n >= total) window.clearInterval(timer);
    }, STEP_MS);
    return () => window.clearInterval(timer);
  }, [total, active]);
  return revealed;
}

function pathOf(url: string) {
  const { pathname } = new URL(url);
  return pathname === "/" ? "homepage" : pathname;
}

/** "Reading homepage… /services… /about…" with each page ticked once its fields have filled. */
export function ReadingProgress({
  website,
  pages,
  revealed,
  total,
}: {
  website: string;
  pages: string[] | null;
  revealed: number;
  total: number;
}) {
  const host = new URL(website).hostname;
  const done = pages !== null && revealed >= total;
  const current = pages ? Math.min(pages.length - 1, Math.floor((revealed / total) * pages.length)) : -1;
  const status = !pages
    ? `Opening ${host}…`
    : done
      ? `Read ${pages.length} pages from ${host}. Check each field below; anything we couldn't find is marked.`
      : `Reading ${pathOf(pages[current]!)}…`;

  return (
    <div className="mt-3">
      <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
        {status}
      </p>
      <ul aria-hidden className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-2xs">
        {(pages ?? [website]).map((page, i) => {
          const read = done || (pages !== null && i < current);
          const active = !done && (pages === null || i === current);
          return (
            <li key={page} className={cn("flex items-center gap-1.5", read ? "text-muted-foreground" : active ? "text-foreground" : "text-faint")}>
              {read ? (
                <Check className="size-3 text-ok" strokeWidth={2.5} />
              ) : active ? (
                <LoaderCircle className="size-3 animate-spin motion-reduce:animate-none" />
              ) : (
                <span className="size-3" />
              )}
              {pathOf(page)}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
