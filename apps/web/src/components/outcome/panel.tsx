import { cn } from "@/lib/utils";

export function Section({
  title,
  actions,
  children,
  className,
  id,
  description,
}: {
  title: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  id?: string;
  description?: React.ReactNode;
}) {
  const headingId = id ? `${id}-heading` : undefined;
  return (
    <section id={id} aria-labelledby={headingId} className={cn("border-b border-hairline py-5 last:border-b-0", className)}>
      <header className="mb-3 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 id={headingId} className="text-sm font-semibold text-foreground">
            {title}
          </h2>
          {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </header>
      {children}
    </section>
  );
}

export function Notice({
  tone = "quiet",
  title,
  children,
  actions,
  className,
  icon,
}: {
  tone?: "quiet" | "attention" | "bad" | "info" | "fixture";
  title: React.ReactNode;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  icon?: React.ReactNode;
}) {
  const toneClass = {
    quiet: "border-hairline bg-raised",
    attention: "border-signal/40 bg-signal/8",
    bad: "border-bad/40 bg-bad/8",
    info: "border-info/35 bg-info/8",
    fixture: "border-fixture/40 bg-fixture/6",
  }[tone];
  return (
    <div role={tone === "bad" || tone === "attention" ? "alert" : "status"} className={cn("flex items-start gap-3 rounded-lg border px-3.5 py-3", toneClass, className)}>
      {icon && <span className="mt-0.5 shrink-0">{icon}</span>}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{title}</p>
        {children && <div className="mt-0.5 text-xs text-muted-foreground">{children}</div>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-hairline px-5 py-8 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-md text-xs text-muted-foreground">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
