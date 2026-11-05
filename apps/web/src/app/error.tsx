"use client";

import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main role="alert" className="mx-auto flex min-h-dvh max-w-lg flex-col items-start justify-center gap-3 px-5">
      <AlertTriangle aria-hidden className="size-5 text-signal" />
      <h1 className="text-lg font-semibold">This screen hit an error</h1>
      <p className="text-sm text-muted-foreground">
        Nothing was sent or changed by this error. Missions keep running on the server.
      </p>
      <p className="font-mono text-2xs text-faint">{error.digest ?? error.message}</p>
      <Button onClick={reset} className="mt-2">
        Try again
      </Button>
    </main>
  );
}
