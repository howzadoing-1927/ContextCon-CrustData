import { ModeBadge } from "@/components/outcome/provenance";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="flex h-12 items-center justify-between border-b border-hairline bg-shell px-5">
        <span className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span aria-hidden className="grid size-5 place-items-center rounded-sm bg-signal text-[0.625rem] font-bold text-signal-foreground">
            O
          </span>
          Outcome AI
        </span>
        <ModeBadge />
      </header>
      <main className="flex flex-1 items-start justify-center px-5 pt-[12vh] pb-16">{children}</main>
    </div>
  );
}
