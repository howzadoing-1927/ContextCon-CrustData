"use client";

import { FlaskConical } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Notice } from "@/components/outcome/panel";
import { ProvenanceStamp } from "@/components/outcome/provenance";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { supabaseConfigured } from "@/lib/env";
import { useSession } from "@/lib/session";

function safeNext(value: string | null): string {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/missions";
}

function SignInForm() {
  const { ready, accessToken, mode, signInWithPassword, startFixtureSession } = useSession();
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (ready && accessToken) router.replace(`/orgs?next=${encodeURIComponent(next)}`);
  }, [ready, accessToken, next, router]);

  const liveDisabled = mode === "FIXTURE" || !supabaseConfigured;

  return (
    <div className="w-full max-w-sm">
      <h1 className="text-xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-1.5 text-sm text-muted-foreground">
        Set up your seller&apos;s authority once, launch a mission, and step in only when the worker is blocked.
      </p>

      {mode === "FIXTURE" && (
        <div className="mt-6 rounded-lg border border-fixture/40 bg-fixture/6 p-4">
          <div className="flex items-center gap-2">
            <ProvenanceStamp kind="FIXTURE" />
            <span className="text-xs text-muted-foreground">No backend or Supabase needed</span>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            This build serves synthetic data. The session below isn&apos;t a real identity.
          </p>
          <Button className="mt-3 w-full" onClick={startFixtureSession}>
            <FlaskConical data-icon="inline-start" />
            Continue with fixture session
          </Button>
        </div>
      )}

      <form
        className="mt-6 flex flex-col gap-4"
        onSubmit={async (event) => {
          event.preventDefault();
          setPending(true);
          setError(null);
          const message = await signInWithPassword(email.trim(), password);
          setPending(false);
          if (message) setError(message);
        }}
      >
        <fieldset disabled={liveDisabled || pending} className="flex flex-col gap-4 disabled:opacity-60">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Work email</Label>
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <Button type="submit" variant={mode === "FIXTURE" ? "outline" : "default"}>
            {pending ? "Signing in…" : "Sign in with Supabase"}
          </Button>
        </fieldset>
        {mode === "LIVE" && !supabaseConfigured && (
          <Notice tone="attention" title="Supabase isn't configured">
            Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY for this build.
          </Notice>
        )}
        {mode === "FIXTURE" && <p className="text-2xs text-faint">Supabase sign-in is available when the app runs in live mode.</p>}
        {error && (
          <Notice tone="bad" title="Couldn't sign in">
            {error}
          </Notice>
        )}
      </form>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense>
      <SignInForm />
    </Suspense>
  );
}
