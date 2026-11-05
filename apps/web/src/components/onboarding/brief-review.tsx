"use client";

import { ArrowRight, Globe, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Field, nativeSelectClass } from "@/components/outcome/field";
import { Notice } from "@/components/outcome/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { describeError } from "@/lib/api/errors";
import type { BriefSave, WebsiteAnalysis } from "@/lib/contracts";
import { timeZones } from "@/lib/timezones";
import { useMutation } from "@/lib/use-mutation";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import { type BriefDraft, type BriefKey, briefErrors, draftFromAnalysis, type FieldOrigin, REQUIRED, toBriefSave } from "./brief";
import { ReadingProgress, useReveal } from "./brief-fill";

const WEEKDAYS = [
  [1, "Mon"],
  [2, "Tue"],
  [3, "Wed"],
  [4, "Thu"],
  [5, "Fri"],
  [6, "Sat"],
  [7, "Sun"],
] as const;

/** Order in which fields fill during the reading step. */
const ORDER = [
  "company_name",
  "website_url",
  "founder_name",
  "founder_email",
  "service",
  "description",
  "pricing",
  "capacity",
  "facts",
  "customer_type",
  "regions",
  "buyer_roles",
  "timeline",
  "criteria",
  "exclusions",
  "meeting",
  "hours",
  "escalation",
] as const;
type Slot = (typeof ORDER)[number];
const indexOf = (slot: Slot) => ORDER.indexOf(slot);

const LABELS: Record<BriefKey, string> = {
  company_name: "Company name",
  website_url: "Website",
  founder_name: "Founder name",
  founder_email: "Contact email",
  service: "Service",
  pricing: "Pricing guidance",
  description: "Description",
  capacity: "Capacity",
  customer_type: "Customer type",
  regions: "Regions",
  buyer_roles: "Buyer roles",
  timeline: "Buying timeline",
  criteria: "Fit criteria",
  exclusions: "Exclusions",
  timezone: "Timezone",
  escalation: "Send these topics to the founder",
};

function pathOf(url: string) {
  const { pathname } = new URL(url);
  return pathname === "/" ? "homepage" : pathname;
}

function OriginChip({ origin, empty, edited, required }: { origin: FieldOrigin | undefined; empty: boolean; edited: boolean; required: boolean }) {
  if (!origin) return null;
  const base = "inline-flex items-center gap-1 text-2xs font-normal";
  if (origin.kind === "site") {
    return edited ? (
      <span className={cn(base, "text-muted-foreground")}>Edited by you</span>
    ) : (
      <span className={cn(base, "text-muted-foreground")}>
        <Globe aria-hidden className="size-3" />
        from your website <span className="font-mono text-faint">{pathOf(origin.page)}</span>
      </span>
    );
  }
  if (origin.kind === "founder") return <span className={cn(base, empty ? "text-signal" : "text-muted-foreground")}>{empty ? "You add this" : "Added by you"}</span>;
  if (origin.kind === "default") return <span className={cn(base, "text-faint")}>{edited ? "Edited by you" : "Suggested default"}</span>;
  if (!empty) return <span className={cn(base, "text-muted-foreground")}>Added by you</span>;
  return required ? (
    <span className={cn(base, "text-signal")}>Not found on your site, add it</span>
  ) : (
    <span className={cn(base, "text-faint")}>Not on your site</span>
  );
}

function BriefSection({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  const id = title.toLowerCase().replace(/\W+/g, "-");
  return (
    <section aria-labelledby={id} className="grid grid-cols-[14rem_1fr] gap-x-10 gap-y-4 border-t border-hairline py-7 max-md:grid-cols-1">
      <div>
        <h2 id={id} className="text-sm font-semibold">
          {title}
        </h2>
        <p className="mt-1 text-xs text-pretty text-muted-foreground">{description}</p>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-5 max-sm:grid-cols-1">{children}</div>
    </section>
  );
}

export function BriefView({
  website,
  analysis,
  profileVersion,
  onStartOver,
  onSaved,
}: {
  website: string;
  analysis: WebsiteAnalysis | null;
  profileVersion: number;
  onStartOver: () => void;
  onSaved: () => void;
}) {
  const { client } = useSession();
  const seeded = useMemo(() => (analysis ? draftFromAnalysis(analysis) : null), [analysis]);
  const [draft, setDraft] = useState<BriefDraft | null>(null);
  const [approvedFacts, setApprovedFacts] = useState<Set<string>>(new Set());
  const [approved, setApproved] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [focusRequest, setFocusRequest] = useState(0);
  const revealed = useReveal(ORDER.length, analysis !== null);
  const filled = analysis !== null && revealed >= ORDER.length;
  const save = useMutation("brief", (input: BriefSave, key: string) => client.workspace.saveBrief(input, key));
  const zones = useMemo(() => timeZones(draft?.timezone), [draft?.timezone]);

  useEffect(() => {
    setDraft(seeded?.draft ?? null);
    setApprovedFacts(new Set());
    setApproved(false);
    setAttempted(false);
  }, [seeded]);

  useEffect(() => {
    if (focusRequest) document.querySelector<HTMLElement>('main [aria-invalid="true"]')?.focus();
  }, [focusRequest]);

  const errors = useMemo(() => (draft ? briefErrors(draft) : {}), [draft]);
  const shown = (slot: Slot) => draft !== null && indexOf(slot) < revealed;
  const update = (patch: Partial<BriefDraft>) => setDraft((d) => (d ? { ...d, ...patch } : d));
  const isDemo = new URL(website).hostname === "demo-seller.example";
  const evidencePage = (id: string) => analysis?.evidence.find((e) => e.id === id)?.source_url ?? null;
  const missingRequired = draft ? REQUIRED.filter((k) => !draft[k].trim()) : [];
  const problems = Object.keys(errors).length + (approved ? 0 : 1);

  const text = (key: BriefKey, opts: { slot?: Slot; multiline?: boolean; hint?: string; placeholder?: string; type?: string; wide?: boolean } = {}) => {
    const slot = opts.slot ?? (key as Slot);
    const required = REQUIRED.includes(key);
    const value = draft?.[key] ?? "";
    return (
      <Field
        key={key}
        className={cn((opts.wide || opts.multiline) && "col-span-2 max-sm:col-span-1")}
        label={
          <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
            <span>
              {LABELS[key]}
              {!required && <span className="font-normal text-faint"> · optional</span>}
            </span>
            {shown(slot) && (
              <OriginChip origin={seeded?.origins[key]} empty={!value.trim()} edited={value !== (seeded?.draft[key] ?? "")} required={required} />
            )}
          </span>
        }
        hint={shown(slot) ? opts.hint : undefined}
        error={attempted ? errors[key] : undefined}
      >
        {(props) =>
          shown(slot) ? (
            <div className="row-arrive rounded-lg">
              {opts.multiline ? (
                <Textarea
                  {...props}
                  value={value}
                  readOnly={!filled}
                  placeholder={opts.placeholder}
                  onChange={(e) => update({ [key]: e.target.value })}
                  className="min-h-20"
                />
              ) : (
                <Input
                  {...props}
                  type={opts.type ?? "text"}
                  value={value}
                  readOnly={!filled}
                  placeholder={opts.placeholder}
                  onChange={(e) => update({ [key]: e.target.value })}
                />
              )}
            </div>
          ) : (
            <Skeleton className={opts.multiline ? "h-20 w-full" : "h-8 w-full"} />
          )
        }
      </Field>
    );
  };

  async function submit() {
    setAttempted(true);
    if (!draft || !analysis || problems > 0) {
      setFocusRequest((n) => n + 1);
      return;
    }
    const result = await save.run(toBriefSave(draft, analysis, [...approvedFacts], profileVersion));
    if (result) onSaved();
  }

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-5 pt-8 pb-16 max-sm:px-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight">Your brief</h1>
          <ReadingProgress website={website} pages={analysis?.pages_read ?? null} revealed={revealed} total={ORDER.length} />
        </div>
        <Button variant="ghost" size="sm" onClick={onStartOver} className="shrink-0">
          <RotateCcw data-icon="inline-start" />
          Different website
        </Button>
      </div>

      {filled && analysis?.source === "firecrawl" && (
        <Notice tone="info" title={`Read from ${new URL(website).hostname}`} className="mt-5">
          Every value came from the pages listed above. Check each one; claims stay proposed until you tick them. Founder details and pricing are
          never guessed.
        </Notice>
      )}
      {filled && analysis?.source === "fixture" && (
        <Notice tone="fixture" title={isDemo ? "Fixture brief for the demo company" : `Sample brief, not read from ${new URL(website).hostname}`} className="mt-5">
          {isDemo
            ? "These values are synthetic so you can try the flow."
            : "The website reader isn't configured, so these claims are fixture samples. Replace them with what's true for your company."}{" "}
          Founder details and pricing are never filled in for you.
        </Notice>
      )}

      <form
        className="mt-6"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <BriefSection title="Your company" description="Who the prospect is talking to. Founder details come from you, never from the site.">
          {text("company_name")}
          {text("website_url", { type: "url" })}
          {text("founder_name", { placeholder: "Your full name" })}
          {text("founder_email", { type: "email", placeholder: "you@company.com", hint: "Escalations and meeting invites go here." })}
        </BriefSection>

        <BriefSection
          title="What you sell"
          description="The description is approved with this brief. Other claims stay proposed until you tick them."
        >
          {text("service")}
          {text("capacity", { placeholder: "e.g. 10 new clients a month" })}
          {text("description", { multiline: true })}
          {text("pricing", { wide: true, hint: "Leave empty and pricing questions go to the founder.", placeholder: "e.g. from £2,000 a month" })}
          <fieldset className="col-span-2 max-sm:col-span-1">
            <legend className="text-xs font-medium">Claims found on your site</legend>
            {shown("facts") && analysis ? (
              <ul className="row-arrive mt-2 divide-y divide-hairline rounded-lg border border-hairline">
                {analysis.proposed_facts.map((fact) => {
                  const page = fact.evidence_ids.map(evidencePage).find(Boolean);
                  const on = approvedFacts.has(fact.id);
                  return (
                    <li key={fact.id}>
                      <label className="flex cursor-pointer items-start gap-3 px-3 py-2.5">
                        <input
                          type="checkbox"
                          checked={on}
                          disabled={!filled}
                          onChange={() =>
                            setApprovedFacts((prev) => {
                              const next = new Set(prev);
                              if (on) next.delete(fact.id);
                              else next.add(fact.id);
                              return next;
                            })
                          }
                          className="mt-0.5 size-4 shrink-0 accent-foreground"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm">{fact.text}</span>
                          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-2xs text-muted-foreground">
                            <span className={on ? "text-foreground" : undefined}>{on ? "Approved for outreach" : "Proposed"}</span>
                            {page && (
                              <span className="inline-flex items-center gap-1">
                                <Globe aria-hidden className="size-3" />
                                <span className="font-mono text-faint">{pathOf(page)}</span>
                              </span>
                            )}
                          </span>
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <Skeleton className="mt-2 h-28 w-full" />
            )}
            {shown("facts") && <p className="mt-1.5 text-2xs text-muted-foreground">Unticked claims are never used in emails.</p>}
          </fieldset>
        </BriefSection>

        <BriefSection title="Your ideal customer" description="Used to find companies and to prefill new missions.">
          {text("customer_type", { wide: true })}
          {text("regions", { hint: "Separate with commas." })}
          {text("buyer_roles", { hint: "Separate with commas." })}
          {text("timeline", { wide: true, placeholder: "e.g. Buying this quarter" })}
          {text("criteria", { multiline: true, hint: "One per line." })}
          {text("exclusions", { multiline: true, hint: "One per line. Companies matching these are skipped." })}
        </BriefSection>

        <BriefSection title="Meetings" description="When prospects can book you. A meeting is only booked after the prospect agrees to it.">
          <Field label="Meeting length">
            {(props) =>
              shown("meeting") && draft ? (
                <select {...props} value={draft.duration} disabled={!filled} onChange={(e) => update({ duration: Number(e.target.value) })} className={nativeSelectClass}>
                  {[15, 30, 45].map((m) => (
                    <option key={m} value={m}>
                      {m} minutes
                    </option>
                  ))}
                </select>
              ) : (
                <Skeleton className="h-8 w-full" />
              )
            }
          </Field>
          <Field
            label={
              <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                {LABELS.timezone}
                {shown("meeting") && <OriginChip origin={seeded?.origins.timezone} empty={false} edited={draft?.timezone !== seeded?.draft.timezone} required />}
              </span>
            }
          >
            {(props) =>
              shown("meeting") && draft ? (
                <select {...props} value={draft.timezone} disabled={!filled} onChange={(e) => update({ timezone: e.target.value })} className={nativeSelectClass}>
                  {zones.map((z) => (
                    <option key={z} value={z}>
                      {z}
                    </option>
                  ))}
                </select>
              ) : (
                <Skeleton className="h-8 w-full" />
              )
            }
          </Field>
          <div className="col-span-2 flex flex-wrap items-end gap-x-4 gap-y-3 max-sm:col-span-1">
            {shown("hours") && draft ? (
              <>
                <div role="group" aria-label="Working days" className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium">Working days</span>
                  <div className="flex gap-1">
                    {WEEKDAYS.map(([day, label]) => {
                      const on = draft.weekdays.includes(day);
                      return (
                        <button
                          key={day}
                          type="button"
                          aria-pressed={on}
                          disabled={!filled}
                          onClick={() => update({ weekdays: on ? draft.weekdays.filter((d) => d !== day) : [...draft.weekdays, day].sort() })}
                          className={cn(
                            "h-8 w-10 rounded-md border text-xs transition-colors duration-150 disabled:opacity-75",
                            on ? "border-input bg-raised text-foreground" : "border-hairline text-faint hover:text-muted-foreground",
                          )}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                  {attempted && errors.weekdays && <p className="text-2xs text-bad">{errors.weekdays}</p>}
                </div>
                <Field label="From" className="w-28">
                  {(props) => <Input {...props} type="time" value={draft.start} readOnly={!filled} onChange={(e) => update({ start: e.target.value })} className="tabular" />}
                </Field>
                <Field label="Until" className="w-28" error={attempted ? errors.end : undefined}>
                  {(props) => <Input {...props} type="time" value={draft.end} readOnly={!filled} onChange={(e) => update({ end: e.target.value })} className="tabular" />}
                </Field>
              </>
            ) : (
              <Skeleton className="h-14 w-full" />
            )}
          </div>
          {text("escalation", {
            multiline: true,
            hint: "One per line. If a prospect asks about these, the rep stops and hands the thread to you.",
          })}
        </BriefSection>

        <div className="border-t border-hairline pt-6">
          {attempted && problems > 0 && (
            <Notice tone="attention" title={problems === 1 ? "One thing needs you before you continue" : `${problems} things need you before you continue`} className="mb-4">
              {[
                ...missingRequired.map((k) => LABELS[k]),
                ...(errors.founder_email && draft?.founder_email.trim() ? ["A valid contact email"] : []),
                ...(errors.weekdays ? ["Working days"] : []),
                ...(errors.end ? ["Meeting hours"] : []),
                ...(approved ? [] : ["Approval"]),
              ].join(", ")}
              .
            </Notice>
          )}
          {save.error != null && (
            <Notice tone="bad" title={describeError(save.error).title} className="mb-4">
              {describeError(save.error).body}
            </Notice>
          )}
          <label className={cn("flex items-start gap-3 text-sm", !filled && "opacity-60")}>
            <input
              id="brief-approval"
              type="checkbox"
              checked={approved}
              disabled={!filled}
              aria-invalid={attempted && !approved ? true : undefined}
              onChange={(e) => setApproved(e.target.checked)}
              className="mt-0.5 size-4 shrink-0 accent-foreground"
            />
            <span>I approve these details. Meetings need the prospect&apos;s explicit agreement.</span>
          </label>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button type="submit" size="lg" className="h-10 px-4" disabled={!filled || save.pending}>
              {save.pending ? "Saving brief…" : "Approve and continue"}
              <ArrowRight data-icon="inline-end" />
            </Button>
            <span className="text-xs text-muted-foreground">Next: connect Google and add your test inbox.</span>
          </div>
        </div>
      </form>
    </main>
  );
}
