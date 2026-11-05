"use client";

import { Plus, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EvidenceList, FactLabel } from "@/components/outcome/evidence";
import { Field, nativeSelectClass } from "@/components/outcome/field";
import { Instant } from "@/components/outcome/mono";
import { Notice, Section } from "@/components/outcome/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { describeError, isApiError } from "@/lib/api/errors";
import type { ApprovedFact, FAQ, OrganizationView, ProfileUpdate } from "@/lib/contracts";
import { useSession } from "@/lib/session";
import { timeZones } from "@/lib/timezones";
import { useMutation } from "@/lib/use-mutation";

interface Draft {
  name: string;
  website_url: string;
  timezone: string;
  approved_facts: ApprovedFact[];
  faq: FAQ[];
  forbidden_promises: string[];
}

function draftFrom(workspace: OrganizationView): Draft {
  return {
    name: workspace.name,
    website_url: workspace.website_url ?? "",
    timezone: workspace.timezone,
    approved_facts: workspace.approved_facts,
    faq: workspace.faq,
    forbidden_promises: workspace.forbidden_promises,
  };
}

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button type="button" variant="ghost" size="icon-xs" aria-label={label} onClick={onClick} className="text-faint hover:text-foreground">
      <X />
    </Button>
  );
}

export function ProfileSection({
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
  const [baseVersion, setBaseVersion] = useState(workspace.profile_version);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [faqFacts, setFaqFacts] = useState<string[]>([]);
  const [promise, setPromise] = useState("");
  const [saved, setSaved] = useState(false);
  const save = useMutation("profile", (input: Omit<ProfileUpdate, "approval_key">, key: string) =>
    client.workspace.updateProfile({ ...input, approval_key: key }, key),
  );

  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(draftFrom(workspace)), [draft, workspace]);
  const zones = useMemo(() => timeZones(draft.timezone), [draft.timezone]);

  // Follow server changes only while the operator hasn't started editing.
  useEffect(() => {
    if (!dirty) {
      setDraft(draftFrom(workspace));
      setBaseVersion(workspace.profile_version);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace]);

  const approvedIds = new Set(draft.approved_facts.map((f) => f.id));
  const proposed = workspace.proposed_facts.filter((f) => !approvedIds.has(f.id));
  const conflict = isApiError(save.error) && save.error.code === "CONFLICT";
  const remoteMoved = workspace.profile_version !== baseVersion;
  const canSubmit = canEdit && draft.name.trim() && draft.website_url.trim() && draft.approved_facts.length > 0;

  function update(patch: Partial<Draft>) {
    setSaved(false);
    setDraft((d) => ({ ...d, ...patch }));
  }

  async function submit() {
    const result = await save.run({ expected_profile_version: baseVersion, ...draft });
    if (result) {
      setDraft(draftFrom(result));
      setBaseVersion(result.profile_version);
      setSaved(true);
      onChanged();
    }
  }

  function discardAndReload() {
    save.reset();
    setDraft(draftFrom(workspace));
    setBaseVersion(workspace.profile_version);
  }

  return (
    <Section
      id="profile"
      title="Seller profile"
      description="Only approved facts may appear in outbound email. Everything else stays out."
      actions={
        <span className="text-2xs text-muted-foreground tabular">
          {workspace.profile_version > 0 ? (
            <>
              Version {workspace.profile_version} · approved <Instant value={workspace.approved_at} timeZone={workspace.timezone} />
            </>
          ) : (
            "Not approved yet"
          )}
        </span>
      }
    >
      <fieldset disabled={!canEdit} className="flex flex-col gap-6">
        <div className="grid grid-cols-[1fr_1fr_14rem] gap-3">
          <Field label="Seller name">
            {(props) => <Input {...props} value={draft.name} onChange={(e) => update({ name: e.target.value })} />}
          </Field>
          <Field label="Website">
            {(props) => (
              <Input
                {...props}
                type="url"
                value={draft.website_url}
                placeholder="https://seller.example/"
                onChange={(e) => update({ website_url: e.target.value })}
                className="font-mono text-xs"
              />
            )}
          </Field>
          <Field label="Seller timezone">
            {(props) => (
              <select {...props} value={draft.timezone} onChange={(e) => update({ timezone: e.target.value })} className={nativeSelectClass}>
                {zones.map((z) => (
                  <option key={z} value={z}>
                    {z}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </div>

        <div>
          <h3 className="text-xs font-medium">Approved facts</h3>
          {draft.approved_facts.length === 0 ? (
            <p className="mt-2 text-xs text-muted-foreground">
              None yet. Approve at least one proposed fact so the agent has something true to say about the seller.
            </p>
          ) : (
            <ul className="mt-1 divide-y divide-hairline">
              {draft.approved_facts.map((fact) => (
                <li key={fact.id} className="flex items-start gap-2 py-2">
                  <FactLabel status="operator_approved" className="mt-px" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm">{fact.text}</p>
                    <EvidenceList ids={fact.evidence_ids} className="mt-1" />
                  </div>
                  {canEdit && (
                    <RemoveButton
                      label={`Remove approved fact: ${fact.text}`}
                      onClick={() =>
                        update({
                          approved_facts: draft.approved_facts.filter((f) => f.id !== fact.id),
                          faq: draft.faq.map((q) => ({ ...q, fact_ids: q.fact_ids.filter((id) => id !== fact.id) })),
                        })
                      }
                    />
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {proposed.length > 0 && (
          <div>
            <h3 className="text-xs font-medium">Proposed from sources</h3>
            <p className="mt-0.5 text-2xs text-muted-foreground">Extracted automatically. Not used anywhere until approved.</p>
            <ul className="mt-1 divide-y divide-hairline">
              {proposed.map((fact) => (
                <li key={fact.id} className="flex items-start gap-2 py-2">
                  <span className="mt-px inline-flex h-5 shrink-0 items-center rounded-sm border border-dashed border-faint px-1.5 text-2xs font-medium text-muted-foreground">
                    Proposed
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-muted-foreground">{fact.text}</p>
                    <EvidenceList ids={fact.evidence_ids} className="mt-1" />
                  </div>
                  {canEdit && (
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      onClick={() =>
                        update({
                          approved_facts: [
                            ...draft.approved_facts,
                            { ...fact, authority: "operator_approved", approved: true },
                          ],
                        })
                      }
                    >
                      Approve
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <h3 className="text-xs font-medium">FAQ</h3>
          <p className="mt-0.5 text-2xs text-muted-foreground">Answers the agent may give, each tied to approved facts.</p>
          {draft.faq.length > 0 && (
            <dl className="mt-1 divide-y divide-hairline">
              {draft.faq.map((item, index) => (
                <div key={`${item.question}-${index}`} className="flex items-start gap-2 py-2">
                  <div className="min-w-0 flex-1">
                    <dt className="text-sm font-medium">{item.question}</dt>
                    <dd className="mt-0.5 text-sm text-muted-foreground">{item.answer}</dd>
                    <dd className="mt-1 text-2xs text-faint">
                      {item.fact_ids.length
                        ? `Backed by ${item.fact_ids.length} approved fact${item.fact_ids.length === 1 ? "" : "s"}`
                        : "Not backed by an approved fact"}
                    </dd>
                  </div>
                  {canEdit && (
                    <RemoveButton
                      label={`Remove FAQ: ${item.question}`}
                      onClick={() => update({ faq: draft.faq.filter((_, i) => i !== index) })}
                    />
                  )}
                </div>
              ))}
            </dl>
          )}
          {canEdit && (
            <div className="mt-3 grid grid-cols-2 gap-3 rounded-lg border border-hairline p-3">
              <Field label="Question">
                {(props) => <Input {...props} value={question} onChange={(e) => setQuestion(e.target.value)} />}
              </Field>
              <Field label="Answer">
                {(props) => <Textarea {...props} rows={2} value={answer} onChange={(e) => setAnswer(e.target.value)} />}
              </Field>
              <fieldset className="col-span-2">
                <legend className="text-xs font-medium">Backed by</legend>
                <div className="mt-1.5 flex flex-col gap-1">
                  {draft.approved_facts.length === 0 && <p className="text-2xs text-faint">Approve a fact first.</p>}
                  {draft.approved_facts.map((fact) => (
                    <label key={fact.id} className="flex items-start gap-2 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        className="mt-0.5 accent-[var(--signal)]"
                        checked={faqFacts.includes(fact.id)}
                        onChange={(e) =>
                          setFaqFacts((ids) => (e.target.checked ? [...ids, fact.id] : ids.filter((id) => id !== fact.id)))
                        }
                      />
                      {fact.text}
                    </label>
                  ))}
                </div>
              </fieldset>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="col-span-2 w-fit"
                disabled={!question.trim() || !answer.trim() || faqFacts.length === 0}
                onClick={() => {
                  update({ faq: [...draft.faq, { question: question.trim(), answer: answer.trim(), fact_ids: faqFacts }] });
                  setQuestion("");
                  setAnswer("");
                  setFaqFacts([]);
                }}
              >
                <Plus data-icon="inline-start" />
                Add to FAQ
              </Button>
            </div>
          )}
        </div>

        <div>
          <h3 className="text-xs font-medium">Forbidden promises</h3>
          <p className="mt-0.5 text-2xs text-muted-foreground">Outbound drafts that commit to any of these are blocked before sending.</p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {draft.forbidden_promises.map((item) => (
              <li key={item} className="inline-flex h-7 items-center gap-1 rounded-md border border-bad/35 pr-0.5 pl-2 text-xs">
                {item}
                {canEdit && (
                  <RemoveButton
                    label={`Remove forbidden promise: ${item}`}
                    onClick={() => update({ forbidden_promises: draft.forbidden_promises.filter((p) => p !== item) })}
                  />
                )}
              </li>
            ))}
            {draft.forbidden_promises.length === 0 && <li className="text-2xs text-faint">None listed.</li>}
          </ul>
          {canEdit && (
            <form
              className="mt-2 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                const value = promise.trim();
                if (value && !draft.forbidden_promises.includes(value)) update({ forbidden_promises: [...draft.forbidden_promises, value] });
                setPromise("");
              }}
            >
              <Input
                aria-label="New forbidden promise"
                placeholder="For example, “Same-day setup”"
                value={promise}
                onChange={(e) => setPromise(e.target.value)}
                className="max-w-sm"
              />
              <Button type="submit" variant="outline" disabled={!promise.trim()}>
                Add
              </Button>
            </form>
          )}
        </div>
      </fieldset>

      {conflict && (
        <Notice
          tone="attention"
          className="mt-5"
          title="Someone approved a newer profile while you were editing"
          actions={
            <Button size="sm" variant="outline" onClick={discardAndReload}>
              Discard my edits and load v{workspace.profile_version}
            </Button>
          }
        >
          Your edits were made against version {baseVersion}. Nothing was saved.
        </Notice>
      )}
      {save.error != null && !conflict && (
        <Notice tone="bad" className="mt-5" title={describeError(save.error).title}>
          {describeError(save.error).body}
        </Notice>
      )}
      {remoteMoved && dirty && !conflict && (
        <Notice tone="attention" className="mt-5" title={`Version ${workspace.profile_version} was approved elsewhere`}>
          Saving will fail until you load it.
        </Notice>
      )}

      {canEdit && (
        <div className="mt-5 flex items-center justify-end gap-3">
          <span role="status" className="text-2xs text-muted-foreground">
            {saved && !dirty ? `Approved as version ${workspace.profile_version}.` : dirty ? "Unsaved changes" : "No changes"}
          </span>
          {dirty && (
            <Button variant="ghost" onClick={discardAndReload}>
              Discard
            </Button>
          )}
          <Button onClick={submit} disabled={!dirty || !canSubmit || save.pending}>
            {save.pending ? "Approving…" : `Approve as version ${baseVersion + 1}`}
          </Button>
        </div>
      )}
    </Section>
  );
}
