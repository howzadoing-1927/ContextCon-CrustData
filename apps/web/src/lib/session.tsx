"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { OutcomeClient, type Session } from "@/lib/api/client";
import { createHttpTransport } from "@/lib/api/transport";
import { env, supabaseConfigured } from "@/lib/env";
import { createFixtureTransport, FIXTURE_ORG_ID } from "@/lib/fixtures/transport";

const ORG_KEY = "outcome.org";
const FIXTURE_SESSION_KEY = "outcome.fixture.session";

interface SessionState {
  ready: boolean;
  email: string | null;
  accessToken: string | null;
  organizationId: string | null;
}

interface SessionContextValue extends SessionState {
  client: OutcomeClient;
  mode: "LIVE" | "FIXTURE";
  supabase: SupabaseClient | null;
  signInWithPassword: (email: string, password: string) => Promise<string | null>;
  startFixtureSession: () => void;
  signOut: () => Promise<void>;
  selectOrganization: (id: string | null) => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const supabase = useMemo(
    () => (env.apiMode === "live" && supabaseConfigured ? createBrowserClient(env.supabaseUrl, env.supabaseAnonKey) : null),
    [],
  );
  const [state, setState] = useState<SessionState>({ ready: false, email: null, accessToken: null, organizationId: null });
  const sessionRef = useRef<Session | null>(null);
  sessionRef.current = state.accessToken ? { accessToken: state.accessToken, organizationId: state.organizationId } : null;

  const client = useMemo(() => {
    const transport = env.apiMode === "live" ? createHttpTransport(env.apiBaseUrl) : createFixtureTransport();
    return new OutcomeClient(transport, () => sessionRef.current);
  }, []);

  useEffect(() => {
    let organizationId = window.localStorage.getItem(ORG_KEY);
    if (env.apiMode === "fixture") {
      // Lets headless tools (design scans, screenshots) open console pages without clicking through sign-in.
      if (new URLSearchParams(window.location.search).has("fixture_session")) {
        window.sessionStorage.setItem(FIXTURE_SESSION_KEY, "fixture-session");
        organizationId ??= FIXTURE_ORG_ID;
        window.localStorage.setItem(ORG_KEY, organizationId);
      }
      const token = window.sessionStorage.getItem(FIXTURE_SESSION_KEY);
      setState({ ready: true, email: token ? "fixture.operator@demo-seller.example" : null, accessToken: token, organizationId });
      return;
    }
    if (!supabase) {
      setState({ ready: true, email: null, accessToken: null, organizationId });
      return;
    }
    supabase.auth.getSession().then(({ data }) => {
      setState({
        ready: true,
        email: data.session?.user.email ?? null,
        accessToken: data.session?.access_token ?? null,
        organizationId,
      });
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setState((prev) => ({ ...prev, email: session?.user.email ?? null, accessToken: session?.access_token ?? null }));
    });
    return () => listener.subscription.unsubscribe();
  }, [supabase]);

  const signInWithPassword = useCallback(
    async (email: string, password: string) => {
      if (!supabase) return "Supabase isn't configured for this build.";
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      return error ? error.message : null;
    },
    [supabase],
  );

  const startFixtureSession = useCallback(() => {
    const token = "fixture-session";
    window.sessionStorage.setItem(FIXTURE_SESSION_KEY, token);
    setState((prev) => ({ ...prev, email: "fixture.operator@demo-seller.example", accessToken: token }));
  }, []);

  const signOut = useCallback(async () => {
    window.sessionStorage.removeItem(FIXTURE_SESSION_KEY);
    window.localStorage.removeItem(ORG_KEY);
    if (supabase) await supabase.auth.signOut();
    setState({ ready: true, email: null, accessToken: null, organizationId: null });
  }, [supabase]);

  const selectOrganization = useCallback((id: string | null) => {
    if (id) window.localStorage.setItem(ORG_KEY, id);
    else window.localStorage.removeItem(ORG_KEY);
    setState((prev) => ({ ...prev, organizationId: id }));
  }, []);

  const value: SessionContextValue = {
    ...state,
    client,
    mode: client.provenance,
    supabase,
    signInWithPassword,
    startFixtureSession,
    signOut,
    selectOrganization,
  };

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
