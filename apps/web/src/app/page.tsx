"use client";

import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BriefView } from "@/components/onboarding/brief-review";
import { FixtureBar } from "@/components/outcome/fixture-bar";
import { ModeBadge, ProvenanceStamp } from "@/components/outcome/provenance";
import { Notice } from "@/components/outcome/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { describeError } from "@/lib/api/errors";
import type { WebsiteAnalysis } from "@/lib/contracts";
import { BRIEF_STORAGE_KEY, normalizeWebsite } from "@/lib/fixtures/onboarding";
import { useMutation } from "@/lib/use-mutation";
import { useSession } from "@/lib/session";

const DEMO_WEBSITE = "demo-seller.example";

const STEPS = [
  ["We read your site", "Homepage, services, about and customer pages. Every value keeps the page it came from."],
  ["You check the brief", "Fix anything we got wrong and fill in what your site doesn't say. Claims stay proposed until you approve them."],
  ["Then you connect Google", "Nothing is sent until setup is finished and a prospect agrees to meet."],
] as const;

export default function LandingPage() {
  const { ready, mode, accessToken, organizationId, enterFixture, client } = useSession();
  const router = useRouter();
  const [website, setWebsite] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<WebsiteAnalysis | null>(null);
  const [profileVersion, setProfileVersion] = useState(0);
  const checked = useRef(false);
  const analyze = useMutation("website-analysis", (url: string, key: string) => client.workspace.analyzeWebsite(url, key));
  const live = mode === "LIVE";

  useEffect(() => {
    if (!ready || checked.current) return;
    checked.current = true;
    if (accessToken && organizationId && window.localStorage.getItem(BRIEF_STORAGE_KEY)) router.replace("/missions");
  }, [ready, accessToken, organizationId, router]);

  async function start(raw: string) {
    const url = normalizeWebsite(raw);
    if (!url) {
      setInputError("Enter your company website, like yourcompany.com.");
      return;
    }
    setInputError(null);
    enterFixture();
    setTarget(url);
    setAnalysis(null);
    try {
      setProfileVersion((await client.workspace.get()).data.profile_version);
    } catch {
      setProfileVersion(0);
    }
    const result = await analyze.run(url);
    if (result) setAnalysis(result);
    else setTarget(null);
  }

  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <header className="sticky top-0 z-40 flex h-12 items-center justify-between gap-3 border-b border-hairline bg-shell px-5 max-sm:px-3">
        <span className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span aria-hidden className="grid size-5 place-items-center rounded-sm bg-primary text-[0.625rem] font-bold text-primary-foreground">
            O
          </span>
          Outcome AI
        </span>
        <div className="flex items-center gap-3">
          {!live && <ProvenanceStamp kind="FIXTURE" />}
          <ModeBadge compact className="max-sm:hidden" />
        </div>
      </header>

      {target ? (
        <BriefView
          website={target}
          analysis={analysis}
          profileVersion={profileVersion}
          onStartOver={() => {
            setTarget(null);
            setAnalysis(null);
          }}
          onSaved={() => router.push("/setup")}
        />
      ) : (
        <main className="mx-auto w-full max-w-xl flex-1 px-5 pt-[14vh] pb-16 max-sm:pt-12">
          <h1 className="text-2xl font-semibold tracking-tight text-balance">Your sales rep starts with your website</h1>
          <p className="mt-2 text-sm text-pretty text-muted-foreground">
            Enter your company website. We read it and fill in your brief: what you sell, who you sell to and how meetings work. You check every
            line before anything runs.
          </p>

          <form
            className="mt-6"
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              void start(website);
            }}
          >
            <label htmlFor="website" className="sr-only">
              Company website
            </label>
            <div className="flex gap-2 max-sm:flex-col">
              <Input
                id="website"
                name="website"
                type="url"
                inputMode="url"
                autoComplete="url"
                autoFocus
                spellCheck={false}
                placeholder="yourcompany.com"
                value={website}
                disabled={live || analyze.pending}
                aria-invalid={inputError ? true : undefined}
                aria-describedby={inputError ? "website-error" : undefined}
                onChange={(e) => {
                  setWebsite(e.target.value);
                  if (inputError) setInputError(null);
                }}
                className="h-10 flex-1 text-base md:text-sm"
              />
              <Button type="submit" size="lg" className="h-10 px-4" disabled={live || analyze.pending}>
                Read my website
                <ArrowRight data-icon="inline-end" />
              </Button>
            </div>
            {inputError && (
              <p id="website-error" className="mt-1.5 text-2xs text-bad">
                {inputError}
              </p>
            )}
          </form>

          <p className="mt-3 text-xs text-muted-foreground">
            No website handy?{" "}
            <button
              type="button"
              disabled={live}
              onClick={() => {
                setWebsite(DEMO_WEBSITE);
                void start(DEMO_WEBSITE);
              }}
              className="font-medium text-foreground underline decoration-hairline underline-offset-4 hover:decoration-foreground disabled:opacity-50"
            >
              Use the demo company
            </button>
          </p>

          {analyze.error != null && (
            <Notice tone="bad" title={describeError(analyze.error).title} className="mt-5">
              {describeError(analyze.error).body}
            </Notice>
          )}
          {live && (
            <Notice tone="info" title="The website reader isn't available on the live API yet" className="mt-5">
              It&apos;s pending contract request 10 in the frontend notes. Use the fixture build to try this flow.
            </Notice>
          )}

          <ol className="mt-12 space-y-4 border-t border-hairline pt-6">
            {STEPS.map(([title, body], i) => (
              <li key={title} className="grid grid-cols-[1.5rem_1fr] gap-x-2">
                <span className="font-mono text-xs text-faint tabular">{i + 1}</span>
                <div>
                  <p className="text-sm font-medium">{title}</p>
                  <p className="mt-0.5 text-xs text-pretty text-muted-foreground">{body}</p>
                </div>
              </li>
            ))}
          </ol>

          {!live && (
            <p className="mt-8 text-2xs text-pretty text-muted-foreground">
              The website reader isn&apos;t connected yet, so this build fills in a sample brief. Every value is labeled FIXTURE.
            </p>
          )}
        </main>
      )}

      {!live && <FixtureBar />}
    </div>
  );
}
