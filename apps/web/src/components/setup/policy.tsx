"use client";

import { useEffect, useMemo, useState } from "react";
import { Field, nativeSelectClass } from "@/components/outcome/field";
import { Notice, Section } from "@/components/outcome/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { describeError, isApiError } from "@/lib/api/errors";
import type { ConsentedRecipient, Limits, OrganizationView, PolicyUpdate, WorkingHours } from "@/lib/contracts";
import { DEFAULT_LIMITS } from "@/lib/contracts";
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
  max_conversations: "Conversations",
  max_outbound_messages: "Outbound emails",
  max_model_calls: "Model calls",
  max_research_calls: "Research calls",
  max_runtime_seconds: "Runtime (seconds)",
  max_reply_turns: "Reply turns",
  no_reply_followups: "Follow-ups without reply",
};

interface Recipient {
  email: string;
  consent_record: string;
}

interface Draft {
  buyer: Recipient;
  owner: Recipient;
  calendar: string;
  hours: WorkingHours;
  duration: number;
  limits: Limits;
}

function draftFrom(workspace: OrganizationView): Draft {
  const find = (role: ConsentedRecipient["role"]) => workspace.policy.consented_recipients.find((r) => r.role === role);
  const buyer = find("buyer_test");
  const owner = find("owner_test");
  return {
    buyer: { email: buyer?.email ?? "", consent_record: buyer?.consent_record ?? "" },
    owner: { email: owner?.email ?? "", consent_record: owner?.consent_record ?? "" },
    calendar: workspace.policy.selected_calendar_id ?? workspace.connection?.calendar_id ?? "primary",
    hours: workspace.policy.working_hours,
    duration: workspace.policy.duration_minutes,
    limits: workspace.policy.limits,
  };
}

function toRecipients(draft: Draft, previous: ConsentedRecipient[]): ConsentedRecipient[] {
  const stamp = (role: ConsentedRecipient["role"], r: Recipient): ConsentedRecipient => {
    const before = previous.find((p) => p.role === role);
    const unchanged = before && before.email === r.email.trim() && before.consent_record === r.consent_record.trim();
    return {
      role,
      email: r.email.trim(),
      consent_record: r.consent_record.trim(),
      consented_at: unchanged ? before.consented_at : new Date().toISOString(),
    };
  };
  const list = [stamp("buyer_test", draft.buyer)];
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

  const errors = {
    buyerEmail: draft.buyer.email && !EMAIL.test(draft.buyer.email.trim()) ? "Enter a full email address." : null,
    buyerConsent: draft.buyer.email && !draft.buyer.consent_record.trim() ? "Record how this person consented." : null,
    ownerEmail: draft.owner.email && !EMAIL.test(draft.owner.email.trim()) ? "Enter a full email address." : null,
    ownerConsent: draft.owner.email && !draft.owner.consent_record.trim() ? "Record how this person consented." : null,
    sameInbox:
      draft.owner.email && draft.owner.email.trim().toLowerCase() === draft.buyer.email.trim().toLowerCase()
        ? "The owner notification inbox must differ from the buyer test inbox."
        : null,
    hours: draft.hours.start >= draft.hours.end ? "End must be after start." : draft.hours.weekdays.length === 0 ? "Pick at least one day." : null,
  };
  const serverField = isApiError(save.error) && save.error.details.field === "consented_recipients" ? save.error.message : null;
  const conflict = isApiError(save.error) && save.error.code === "CONFLICT";
  const valid =
    EMAIL.test(draft.buyer.email.trim()) &&
    draft.buyer.consent_record.trim() &&
    draft.calendar.trim() &&
    !Object.values(errors).some(Boolean);

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
          <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-3">
            <Field
              label="Buyer test inbox"
              hint="Plays the buyer. Exactly one. A teammate's inbox that agreed to receive this."
              error={errors.buyerEmail ?? serverField}
            >
              {(props) => (
                <Input
                  {...props}
                  type="email"
                  autoComplete="off"
                  value={draft.buyer.email}
                  onChange={(e) => update({ buyer: { ...draft.buyer, email: e.target.value } })}
                  className="font-mono text-xs"
                />
              )}
            </Field>
            <Field label="Buyer consent record" hint="Where and when consent was given." error={errors.buyerConsent}>
              {(props) => (
                <Input
                  {...props}
                  value={draft.buyer.consent_record}
                  placeholder="Consent in kickoff notes, 5 Nov"
                  onChange={(e) => update({ buyer: { ...draft.buyer, consent_record: e.target.value } })}
                />
              )}
            </Field>
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
          <h3 className="text-xs font-medium">Per-mission limits</h3>
          <p className="mt-0.5 text-2xs text-muted-foreground">You can lower these. Raising a ceiling needs a reviewed contract change.</p>
          <div className="mt-2 grid grid-cols-3 gap-x-4 gap-y-3">
            {(Object.keys(LIMIT_LABEL) as (keyof Limits)[]).map((key) => (
              <Field key={key} label={LIMIT_LABEL[key]} hint={`Ceiling ${DEFAULT_LIMITS[key]}`}>
                {(props) => (
                  <Input
                    {...props}
                    type="number"
                    min={0}
                    max={DEFAULT_LIMITS[key]}
                    value={draft.limits[key]}
                    onChange={(e) => {
                      const n = Math.max(0, Math.min(DEFAULT_LIMITS[key], Math.floor(Number(e.target.value) || 0)));
                      update({ limits: { ...draft.limits, [key]: n } });
                    }}
                    className="tabular"
                  />
                )}
              </Field>
            ))}
          </div>
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
