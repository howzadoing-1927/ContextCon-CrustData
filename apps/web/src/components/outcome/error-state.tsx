"use client";

import { AlertTriangle, Lock, SearchX, Unplug } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button, buttonVariants } from "@/components/ui/button";
import { describeError, isApiError } from "@/lib/api/errors";
import { useSession } from "@/lib/session";
import { MonoId } from "./mono";

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { signOut } = useSession();
  const router = useRouter();
  const { title, body } = describeError(error);
  const code = isApiError(error) ? error.code : null;
  const Icon = code === "UNAUTHENTICATED" || code === "FORBIDDEN" ? Lock : code === "NOT_FOUND" ? SearchX : code === "NETWORK" || code === "DEPENDENCY_UNAVAILABLE" ? Unplug : AlertTriangle;

  return (
    <div role="alert" className="mx-auto flex max-w-lg flex-col items-start gap-3 py-16">
      <Icon aria-hidden className="size-5 text-signal" />
      <h1 className="text-lg font-semibold">{title}</h1>
      <p className="text-sm text-muted-foreground">{body}</p>
      {isApiError(error) && (
        <p className="flex items-center gap-2 text-2xs text-faint">
          HTTP {error.status || "n/a"} · {error.code}
          {error.correlationId && (
            <>
              · correlation <MonoId value={error.correlationId} />
            </>
          )}
        </p>
      )}
      <div className="mt-2 flex gap-2">
        {code === "UNAUTHENTICATED" ? (
          <Button
            onClick={async () => {
              await signOut();
              router.replace("/");
            }}
          >
            Start again
          </Button>
        ) : code === "FORBIDDEN" ? (
          <Button
            onClick={async () => {
              await signOut();
              router.replace("/");
            }}
          >
            Start again
          </Button>
        ) : code === "NOT_FOUND" ? (
          <Link href="/missions" className={buttonVariants({ variant: "default" })}>
            Back to missions
          </Link>
        ) : (
          onRetry && <Button onClick={onRetry}>Retry</Button>
        )}
      </div>
    </div>
  );
}
