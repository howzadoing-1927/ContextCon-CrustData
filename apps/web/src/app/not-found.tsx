import { SearchX } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-lg flex-col items-start justify-center gap-3 px-5">
      <SearchX aria-hidden className="size-5 text-signal" />
      <h1 className="text-lg font-semibold">This page doesn&apos;t exist</h1>
      <p className="text-sm text-muted-foreground">The address may be mistyped, or the page moved.</p>
      <Link href="/missions" className={buttonVariants({ className: "mt-2" })}>
        Go to missions
      </Link>
    </main>
  );
}
