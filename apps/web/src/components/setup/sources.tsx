"use client";

import { FileText, Globe } from "lucide-react";
import { useState } from "react";
import { EvidenceList } from "@/components/outcome/evidence";
import { Field } from "@/components/outcome/field";
import { Instant } from "@/components/outcome/mono";
import { Notice, Section } from "@/components/outcome/panel";
import { StatusChip } from "@/components/outcome/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { describeError, isApiError } from "@/lib/api/errors";
import type { OrganizationView, SourceInput, SourceView } from "@/lib/contracts";
import { useSession } from "@/lib/session";
import { useMutation } from "@/lib/use-mutation";
import { cn } from "@/lib/utils";

function SourceRow({ source, timeZone }: { source: SourceView; timeZone: string }) {
  const Icon = source.kind === "website" ? Globe : FileText;
  return (
    <li className="grid grid-cols-[1rem_1fr_auto] items-start gap-x-3 py-3">
      <Icon aria-hidden className="mt-0.5 size-4 text-muted-foreground" />
      <div className="min-w-0">
        <p className={cn("truncate text-sm", source.kind === "website" && "font-mono text-xs leading-5")}>{source.label}</p>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-muted-foreground">
          {source.status === "ready" && (
            <span>
              Retrieved <Instant value={source.retrieved_at} timeZone={timeZone} />
            </span>
          )}
          {source.status === "ingesting" && <span>Reading and extracting claims. Proposed facts appear below when done.</span>}
          {source.status === "failed" && <span className="text-bad">{source.error ?? "Could not read this source."}</span>}
          {source.evidence_ids.length > 0 && <EvidenceList ids={source.evidence_ids} />}
        </div>
      </div>
      {source.status === "ready" && <StatusChip tone="ok">Ready</StatusChip>}
      {source.status === "ingesting" && <StatusChip tone="info">Ingesting</StatusChip>}
      {source.status === "failed" && <StatusChip tone="bad">Failed</StatusChip>}
    </li>
  );
}

export function SourcesSection({
  workspace,
  canEdit,
  onChanged,
}: {
  workspace: OrganizationView;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const { client } = useSession();
  const [kind, setKind] = useState<SourceInput["kind"]>("website");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const add = useMutation("source", (input: SourceInput, key: string) => client.workspace.addSource(input, key));

  const fieldError = isApiError(add.error) && add.error.details.field === "url" ? add.error.message : null;
  const valid = kind === "website" ? url.trim().length > 0 : title.trim().length > 0 && text.trim().length > 0;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid) return;
    const input: SourceInput = kind === "website" ? { kind, url: url.trim() } : { kind, title: title.trim(), text: text.trim() };
    const result = await add.run(input);
    if (result) {
      setUrl("");
      setTitle("");
      setText("");
      onChanged();
    }
  }

  return (
    <Section
      id="sources"
      title="Seller sources"
      description="Where the seller's claims come from. Extracted claims stay proposed until an owner approves them."
    >
      {workspace.sources.length > 0 ? (
        <ul className="divide-y divide-hairline border-y border-hairline">
          {workspace.sources.map((source) => (
            <SourceRow key={source.id} source={source} timeZone={workspace.timezone} />
          ))}
        </ul>
      ) : (
        <p className="border-y border-hairline py-3 text-xs text-muted-foreground">
          No sources yet. Add the seller&apos;s public website, or paste notes the seller has approved.
        </p>
      )}

      {canEdit && (
        <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
          <div role="group" aria-label="Source type" className="inline-flex w-fit rounded-lg border border-hairline p-0.5">
            {(["website", "pasted_text"] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={kind === value}
                onClick={() => {
                  setKind(value);
                  add.reset();
                }}
                className={cn(
                  "h-7 rounded-md px-2.5 text-xs transition-colors duration-150",
                  kind === value ? "bg-raised text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {value === "website" ? "Website URL" : "Pasted text"}
              </button>
            ))}
          </div>

          {kind === "website" ? (
            <div className="flex items-start gap-2">
              <Field
                label="Public HTTPS URL"
                hint="Fetched by the server. Private, local and metadata addresses are refused."
                error={fieldError}
                className="flex-1"
              >
                {(props) => (
                  <Input
                    {...props}
                    type="url"
                    inputMode="url"
                    placeholder="https://seller.example/"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    className="font-mono text-xs"
                  />
                )}
              </Field>
              <Button type="submit" variant="outline" disabled={!valid || add.pending} className="mt-[1.375rem]">
                {add.pending ? "Adding…" : "Add source"}
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <Field label="Title" hint="Shown as the source label, for example “Pricing notes, approved 5 Nov”.">
                {(props) => <Input {...props} value={title} onChange={(e) => setTitle(e.target.value)} />}
              </Field>
              <Field label="Text">
                {(props) => <Textarea {...props} rows={5} value={text} onChange={(e) => setText(e.target.value)} />}
              </Field>
              <Button type="submit" variant="outline" disabled={!valid || add.pending} className="w-fit">
                {add.pending ? "Adding…" : "Add source"}
              </Button>
            </div>
          )}

          {add.error != null && !fieldError && (
            <Notice tone="bad" title={describeError(add.error).title}>
              {describeError(add.error).body}
            </Notice>
          )}
        </form>
      )}
    </Section>
  );
}
