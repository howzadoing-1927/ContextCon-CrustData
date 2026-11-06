"use client";

import { ChevronRight, Plus, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Field, nativeSelectClass } from "@/components/outcome/field";
import { Notice, Section } from "@/components/outcome/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { describeError, isApiError } from "@/lib/api/errors";
import type { ConsentedRecipient, Limits, OrganizationView, PolicyUpdate, WorkingHours } from "@/lib/contracts";
import { LIMIT_CEILINGS, MAX_BUYER_INBOXES, MAX_PEOPLE, limitsFor } from "@/lib/contracts";
import { useSession } from "@/lib/session";
import { timeZones } from "@/lib/timezones";
import { useMutation } from "@/lib/use-mutation";
import { cn } from "@/lib/utils";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const WEEKDAYS = [
  [1, "Mon"],
  [2, "Tue"],
  [3, "Wed"],
  [4, "Thu"],
  [5, "Fri"],
  [6, "Sat"],
  [7, "Sun"],
] as const;

const LIMIT_LABEL: Record<keyof Limits, string> = {
  max_discovered: "Companies discovered",
  max_enriched: "Companies enriched",
  max_conversations: "People reached",
  max_outbound_messages: "Emails per person",
  max_model_calls: "Model calls",
  max_research_calls: "Research calls",
  max_runtime_seconds: "Runtime (seconds)",
  max_reply_turns: "Reply turns per person",
  no_reply_followups: "Follow-ups without reply",
};

interface Recipient {
  email: string;
  consent_record: string;
}

interface Draft {
  buyers: Recipient[];
  owner: Recipient;
  calendar: string;
  hours: WorkingHours;
  duration: number;
  limits: Limits;
}

function draftFrom(workspace: OrganizationView): Draft {
  const pick = (r: ConsentedRecipient) => ({ email: r.email, consent_record: r.consent_record });
  const buyers = workspace.policy.consented_recipients.filter((r) => r.role === "buyer_test").map(pick);
  const owner = workspace.policy.consented_recipients.find((r) => r.role === "owner_test");
  return {
    buyers: buyers.length ? buyers : [{ email: "", consent_record: "" }],
    owner: owner ? pick(owner) : { email: "", consent_record: "" },
    calendar: workspace.policy.selected_calendar_id ?? workspace.connection?.calendar_id ?? "primary",
    hours: workspace.policy.working_hours,
    duration: workspace.policy.duration_minutes,
    limits: workspace.policy.limits,
  };
}

function toRecipients(draft: Draft, previous: ConsentedRecipient[]): ConsentedRecipient[] {
  const stamp = (role: ConsentedRecipient["role"], r: Recipient): ConsentedRecipient => {
    const email = r.email.trim();
    const before = previous.find((p) => p.role === role && p.email === email);
    const unchanged = before && before.consent_record === r.consent_record.trim();
    return {
      role,
      email,
      consent_record: r.consent_record.trim(),
      consented_at: unchanged ? before.consented_at : new Date().toISOString(),
    };
  };
  const list = draft.buyers.filter((b) => b.email.trim()).map((b) => stamp("buyer_test", b));
  if (draft.owner.email.trim()) list.push(stamp("owner_test", draft.owner));
  return list;
}

export function PolicySection({
  workspace,
  canEdit,
  onChanged,
}: {
  workspace: OrganizationView;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const { client } = useSession();
  const [draft, setDraft] = useState<Draft>(() => draftFrom(workspace));
  const [baseVersion, setBaseVersion] = useState(workspace.policy.config_version);
  const [saved, setSaved] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const save = useMutation("policy", (input: PolicyUpdate, key: string) => client.workspace.updatePolicy(input, key));
  const zones = useMemo(() => timeZones(draft.hours.timezone), [draft.hours.timezone]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(draftFrom(workspace));

  useEffect(() => {
    if (!dirty) {
      setDraft(draftFrom(workspace));
      setBaseVersion(workspace.policy.config_version);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace]);

  function update(patch: Partial<Draft>) {
    setSaved(false);
    setDraft((d) => ({ ...d, ...patch }));
  }

  function updateBuyer(index: number, patch: Partial<Recipient>) {
    update({ buyers: draft.buyers.map((b, i) => (i === index ? { ...b, ...patch } : b)) });
  }

  const filled = draft.buyers.filter((b) => b.email.trim());
  const lowered = filled.map((b) => b.email.trim().toLowerCase());
  const buyerErrors = draft.buyers.map((b) => {
    const email = b.email.trim();
    if (!email) return null;
    if (!EMAIL.test(email)) return "Enter a full email address.";
    if (!b.consent_record.trim()) return "Record how this inbox's owner consented.";
    if (lowered.indexOf(email.toLowerCase()) !== lowered.lastIndexOf(email.toLowerCase())) return "Listed twice.";
    return null;
  });
  const errors = {
    buyers: filled.length === 0 ? "Add at least one consented test inbox." : null,
    ownerEmail: draft.owner.email && !EMAIL.test(draft.owner.email.trim()) ? "Enter a full email address." : null,
    ownerConsent: draft.owner.email && !draft.owner.consent_record.trim() ? "Record how this person consented." : null,
    sameInbox:
      draft.owner.email && lowered.includes(draft.owner.email.trim().toLowerCase())
        ? "The owner notification inbox must differ from the test inboxes."
        : null,
    hours: draft.hours.start >= draft.hours.end ? "End must be after start." : draft.hours.weekdays.length === 0 ? "Pick at least one day." : null,
  };
  const serverField = isApiError(save.error) && save.error.details.field === "consented_recipients" ? save.error.message : null;
  const conflict = isApiError(save.error) && save.error.code === "CONFLICT";
  const valid = draft.calendar.trim() && !buyerErrors.some(Boolean) && !Object.values(errors).some(Boolean);
  const people = draft.limits.max_conversations;

  async function submit() {
    const result = await save.run({
      expected_config_version: baseVersion,
      simulation: true,
      consented_recipients: toRecipients(draft, workspace.policy.consented_recipients),
      selected_calendar_id: draft.calendar.trim(),
      working_hours: draft.hours,
      duration_minutes: draft.duration,
      limits: draft.limits,
    });
    if (result) {
      setDraft(draftFrom(result));
      setBaseVersion(result.policy.config_version);
      setSaved(true);
      onChanged();
    }
  }

  function discard() {
    save.reset();
    setDraft(draftFrom(workspace));
    setBaseVersion(workspace.policy.config_version);
  }

  return (
    <Section
      id="policy"
      title="Recipients, hours and limits"
      description="Simulation mode: mail goes only to consented test inboxes, never to a researched person."
      actions={
        <span className="text-2xs text-muted-foreground tabular">
          {workspace.policy.config_version > 0 ? `Version ${workspace.policy.config_version}` : "Not saved yet"}
        </span>
      }
    >
      <fieldset disabled={!canEdit} className="flex flex-col gap-6">
        <div>
          <h3 className="text-xs font-medium">Consented test inboxes</h3>
          <p className="mt-0.5 text-2xs text-muted-foreground">
            They play the buyers. Each researched person&apos;s email goes to the next inbox in turn: 1, 2, 3, then back to 1.
          </p>
          <ol className="mt-2 flex flex-col gap-2">
            {draft.buyers.map((buyer, i) => (
              <li key={i} className="grid grid-cols-[1.25rem_1fr_1fr_2rem] items-start gap-3">
                <span className="pt-2 text-2xs text-faint tabular">{i + 1}</span>
                <Field label={<span className="sr-only">Test inbox {i + 1}</span>} error={buyerErrors[i]}>
                  {(props) => (
                    <Input
                      {...props}
                      type="email"
                      autoComplete="off"
                      placeholder="teammate@example.com"
                      value={buyer.email}
                      onChange={(e) => updateBuyer(i, { email: e.target.value })}
                      className="font-mono text-xs"
                    />
                  )}
                </Field>
                <Field label={<span className="sr-only">Consent record for inbox {i + 1}</span>}>
                  {(props) => (
                    <Input
                      {...props}
                      value={buyer.consent_record}
                      placeholder="Consent in kickoff notes, 5 Nov"
                      onChange={(e) => updateBuyer(i, { consent_record: e.target.value })}
                    />
                  )}
                </Field>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Remove test inbox ${i + 1}`}
                  disabled={draft.buyers.length === 1}
                  onClick={() => update({ buyers: draft.buyers.filter((_, j) => j !== i) })}
                >
                  <X />
                </Button>
              </li>
            ))}
          </ol>
          <div className="mt-2 flex items-center justify-between gap-3">
            <p className={cn("text-2xs", errors.buyers || serverField ? "text-bad" : "text-faint")}>
              {errors.buyers ?? serverField ?? `${filled.length} of ${MAX_BUYER_INBOXES} inboxes`}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={draft.buyers.length >= MAX_BUYER_INBOXES}
              onClick={() => update({ buyers: [...draft.buyers, { email: "", consent_record: "" }] })}
            >
              <Plus data-icon="inline-start" />
              Add inbox
            </Button>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
            <Field label="Owner notification inbox (optional)" hint="Receives the handoff note." error={errors.ownerEmail ?? errors.sameInbox}>
              {(props) => (
                <Input
                  {...props}
                  type="email"
                  autoComplete="off"
                  value={draft.owner.email}
                  onChange={(e) => update({ owner: { ...draft.owner, email: e.target.value } })}
                  className="font-mono text-xs"
                />
              )}
            </Field>
            <Field label="Owner consent record" error={errors.ownerConsent}>
              {(props) => (
                <Input
                  {...props}
                  value={draft.owner.consent_record}
                  disabled={!draft.owner.email}
                  onChange={(e) => update({ owner: { ...draft.owner, consent_record: e.target.value } })}
                />
              )}
            </Field>
          </div>
        </div>

        <div>
          <h3 className="text-xs font-medium">Meeting window</h3>
          <div className="mt-2 grid grid-cols-[1fr_7rem_7rem_8rem] gap-3">
            <Field label="Calendar">
              {(props) => (
                <Input {...props} value={draft.calendar} onChange={(e) => update({ calendar: e.target.value })} className="font-mono text-xs" />
              )}
            </Field>
            <Field label="From">
              {(props) => (
                <Input
                  {...props}
                  type="time"
                  value={draft.hours.start}
                  onChange={(e) => update({ hours: { ...draft.hours, start: e.target.value } })}
                  className="tabular"
                />
              )}
            </Field>
            <Field label="To">
              {(props) => (
                <Input
                  {...props}
                  type="time"
                  value={draft.hours.end}
                  onChange={(e) => update({ hours: { ...draft.hours, end: e.target.value } })}
                  className="tabular"
                />
              )}
            </Field>
            <Field label="Duration">
              {(props) => (
                <select
                  {...props}
                  value={draft.duration}
                  onChange={(e) => update({ duration: Number(e.target.value) })}
                  className={nativeSelectClass}
                >
                  {[15, 30, 45].map((m) => (
                    <option key={m} value={m}>
                      {m} minutes
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
          <div className="mt-3 grid grid-cols-[1fr_auto] items-end gap-3">
            <Field label="Hours are in">
              {(props) => (
                <select
                  {...props}
                  value={draft.hours.timezone}
                  onChange={(e) => update({ hours: { ...draft.hours, timezone: e.target.value } })}
                  className={nativeSelectClass}
                >
                  {zones.map((z) => (
                    <option key={z} value={z}>
                      {z}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            <div role="group" aria-label="Working days" className="flex gap-1">
              {WEEKDAYS.map(([day, label]) => {
                const on = draft.hours.weekdays.includes(day);
                return (
                  <button
                    key={day}
                    type="button"
                    aria-pressed={on}
                    onClick={() =>
                      update({
                        hours: {
                          ...draft.hours,
                          weekdays: on ? draft.hours.weekdays.filter((d) => d !== day) : [...draft.hours.weekdays, day].sort(),
                        },
                      })
                    }
                    className={cn(
                      "h-8 w-10 rounded-md border text-xs transition-colors duration-150 disabled:opacity-50",
                      on ? "border-input bg-raised text-foreground" : "border-hairline text-faint hover:text-muted-foreground",
                    )}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
          {errors.hours && <p className="mt-1.5 text-2xs text-bad">{errors.hours}</p>}
        </div>

        <div>
          <h3 className="text-xs font-medium">Mission size</h3>
          <p className="mt-0.5 text-2xs text-muted-foreground">
            Caps how much one mission can spend: research credits, model calls and emails. Every budget below scales with the number of people.
          </p>
          <div className="mt-2 grid grid-cols-[12rem_1fr] items-start gap-4">
            <Field label="People to reach" hint={`Default 10, up to ${MAX_PEOPLE}`}>
              {(props) => (
                <Input
                  {...props}
                  type="number"
                  min={1}
                  max={MAX_PEOPLE}
                  value={people}
                  onChange={(e) => update({ limits: limitsFor(Number(e.target.value)) })}
                  className="tabular"
                />
              )}
            </Field>
            <p className="pt-6 text-2xs text-muted-foreground tabular">
              Up to {draft.limits.max_discovered} companies searched, {draft.limits.max_research_calls} research calls,{" "}
              {draft.limits.max_model_calls} model calls, {draft.limits.max_outbound_messages} emails per person.
            </p>
          </div>
          <button
            type="button"
            aria-expanded={advanced}
            onClick={() => setAdvanced((a) => !a)}
            className="mt-3 flex items-center gap-1 text-2xs text-muted-foreground hover:text-foreground"
          >
            <ChevronRight className={cn("size-3 transition-transform", advanced && "rotate-90")} />
            Advanced budgets
          </button>
          {advanced && (
            <div className="mt-2 grid grid-cols-3 gap-x-4 gap-y-3">
              {(Object.keys(LIMIT_LABEL) as (keyof Limits)[]).map((key) => (
                <Field key={key} label={LIMIT_LABEL[key]} hint={`Ceiling ${LIMIT_CEILINGS[key]}`}>
                  {(props) => (
                    <Input
                      {...props}
                      type="number"
                      min={0}
                      max={LIMIT_CEILINGS[key]}
                      value={draft.limits[key]}
                      onChange={(e) => {
                        const n = Math.max(0, Math.min(LIMIT_CEILINGS[key], Math.floor(Number(e.target.value) || 0)));
                        update({ limits: { ...draft.limits, [key]: n } });
                      }}
                      className="tabular"
                    />
                  )}
                </Field>
              ))}
            </div>
          )}
        </div>
      </fieldset>

      {conflict && (
        <Notice
          tone="attention"
          className="mt-5"
          title="Policy changed while you were editing"
          actions={
            <Button size="sm" variant="outline" onClick={discard}>
              Discard my edits and load v{workspace.policy.config_version}
            </Button>
          }
        >
          Your edits were made against version {baseVersion}. Nothing was saved.
        </Notice>
      )}
      {save.error != null && !conflict && !serverField && (
        <Notice tone="bad" className="mt-5" title={describeError(save.error).title}>
          {describeError(save.error).body}
        </Notice>
      )}

      {canEdit && (
        <div className="mt-5 flex items-center justify-end gap-3">
          <span role="status" className="text-2xs text-muted-foreground">
            {saved && !dirty ? `Saved as version ${workspace.policy.config_version}.` : dirty ? "Unsaved changes" : "No changes"}
          </span>
          {dirty && (
            <Button variant="ghost" onClick={discard}>
              Discard
            </Button>
          )}
          <Button onClick={submit} disabled={!dirty || !valid || save.pending}>
            {save.pending ? "Saving…" : `Save as version ${baseVersion + 1}`}
          </Button>
        </div>
      )}
    </Section>
  );
}
