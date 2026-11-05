"use client";

import { AlertTriangle, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { EvidenceList } from "@/components/outcome/evidence";
import { Instant } from "@/components/outcome/mono";
import { Notice } from "@/components/outcome/panel";
import { useWorkspace } from "@/components/outcome/workspace-context";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { describeError, isApiError } from "@/lib/api/errors";
import type { DecisionView, MissionDetail, ResolutionType, ResolveInput } from "@/lib/contracts";
import { REQUIRED_GOOGLE_SCOPES } from "@/lib/contracts";
import { formatSlot, humanize } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useMutation } from "@/lib/use-mutation";
import { cn } from "@/lib/utils";

const RESOLUTION: Record<ResolutionType, { label: string; help: string; submit: string }> = {
  clarify_time: {
    label: "Ask the buyer to pick a time",
    help: "The worker emails the test inbox again and asks them to choose one of the times below. You can't accept a time on the buyer's behalf.",
    submit: "Send the clarification",
  },
  supply_fact: {
    label: "Answer with an approved fact",
    help: "The worker may only use facts an owner approved in Setup.",
    submit: "Use this fact",
  },
  confirm_identity: {
    label: "Confirm the person's identity",
    help: "Only if you have checked that this person currently holds this role at this company.",
    submit: "Confirm identity",
  },
  reauthorize_complete: {
    label: "Google is reconnected",
    help: "Resolves only when the server reports the seller connection as connected with all four scopes.",
    submit: "Resume with the new connection",
  },
  stop: {
    label: "Stop the mission",
    help: "Ends the mission. Nothing else is sent and nothing is booked.",
    submit: "Stop mission",
  },
};

function firstSentence(text: string) {
  const match = text.match(/^.+?[.!?](\s|$)/);
  return match ? match[0].trim() : text;
}

export function allowedResolutions(decision: DecisionView): ResolutionType[] {
  const raw = decision.proposed_action?.resolution_types;
  const list = Array.isArray(raw) ? (raw.filter((t) => typeof t === "string" && t in RESOLUTION) as ResolutionType[]) : [];
  return list.length ? list : ["stop"];
}

export function ExceptionStrip({ exceptions, onOpen }: { exceptions: DecisionView[]; onOpen: () => void }) {
  if (!exceptions.length) return null;
  const first = exceptions[0];
  return (
    <div role="alert" className="flex items-center gap-3 border-b border-signal/40 bg-signal/10 px-5 py-2.5">
      <AlertTriangle aria-hidden className="size-4 shrink-0 text-signal" />
      <p className="min-w-0 flex-1 truncate text-sm">
        <span className="font-semibold text-signal">Needs you{exceptions.length > 1 ? ` (${exceptions.length})` : ""}: </span>
        <span className="font-medium">{humanize(first.kind)}.</span> <span className="text-muted-foreground">{firstSentence(first.reason)}</span>
      </p>
      <Button size="sm" onClick={onOpen} className="bg-signal text-signal-foreground hover:bg-signal/85">
        Review and resolve
      </Button>
    </div>
  );
}

function ResolutionForm({
  decision,
  detail,
  canResolve,
  onResolved,
}: {
  decision: DecisionView;
  detail: MissionDetail;
  canResolve: boolean;
  onResolved: (message: string) => void;
}) {
  const { client } = useSession();
  const { workspace } = useWorkspace();
  const ws = workspace.data;
  const allowed = allowedResolutions(decision);
  const [type, setType] = useState<ResolutionType>(allowed[0]);
  const [note, setNote] = useState("");
  const [factId, setFactId] = useState<string>("");
  const [slotIds, setSlotIds] = useState<string[]>(() => detail.conversation?.offered_slots.map((s) => s.id) ?? []);
  const [identityChecked, setIdentityChecked] = useState(false);
  const noteId = useId();
  const expectedVersion = detail.conversation?.version ?? null;
  const resolve = useMutation(`resolve-${decision.id}`, (input: ResolveInput, key: string) => client.decisions.resolve(decision.id, input, key));

  useEffect(() => {
    resolve.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type]);

  const connection = ws?.connection ?? null;
  const granted = new Set(connection?.granted_scopes ?? []);
  const reconnected = connection?.status === "connected" && REQUIRED_GOOGLE_SCOPES.every((s) => granted.has(s));
  const fact = ws?.approved_facts.find((f) => f.id === factId);
  const slots = detail.conversation?.offered_slots ?? [];

  const typeReady =
    type === "clarify_time"
      ? slotIds.length > 0
      : type === "supply_fact"
        ? Boolean(fact)
        : type === "confirm_identity"
          ? identityChecked
          : type === "reauthorize_complete"
            ? reconnected
            : true;
  const ready = canResolve && typeReady && note.trim().length >= 3;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!ready) return;
    const value: Record<string, unknown> =
      type === "clarify_time"
        ? { reoffer_slot_ids: slotIds }
        : type === "supply_fact"
          ? { fact_id: factId }
          : type === "confirm_identity"
            ? { confirmed: true }
            : type === "reauthorize_complete"
              ? { connection_id: connection?.connection_id ?? null }
              : {};
    const result = await resolve.run({
      resolution_type: type,
      expected_conversation_version: expectedVersion,
      note: note.trim(),
      value,
      evidence_ids: type === "supply_fact" && fact ? fact.evidence_ids : [],
    });
    if (result) onResolved(type === "stop" ? "Mission stopped." : `Resolved: ${RESOLUTION[type].label.toLowerCase()}. The worker continues.`);
  }

  const conflict = isApiError(resolve.error) && resolve.error.code === "CONFLICT";

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <fieldset>
        <legend className="text-xs font-medium">Resolution</legend>
        <div className="mt-2 flex flex-col gap-1.5">
          {allowed.map((t) => (
            <label
              key={t}
              className={cn(
                "flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2 transition-colors duration-150",
                type === t ? "border-input bg-raised" : "border-hairline hover:border-input",
              )}
            >
              <input
                type="radio"
                name={`resolution-${decision.id}`}
                value={t}
                checked={type === t}
                onChange={() => setType(t)}
                className="mt-1 accent-[var(--signal)]"
              />
              <span>
                <span className={cn("block text-sm font-medium", t === "stop" && "text-bad")}>{RESOLUTION[t].label}</span>
                <span className="block text-2xs text-muted-foreground">{RESOLUTION[t].help}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {type === "clarify_time" && (
        <fieldset>
          <legend className="text-xs font-medium">Times to offer again</legend>
          {slots.length === 0 ? (
            <p className="mt-1 text-2xs text-faint">No times were offered in this conversation.</p>
          ) : (
            <div className="mt-1.5 flex flex-col gap-1">
              {slots.map((slot) => (
                <label key={slot.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={slotIds.includes(slot.id)}
                    onChange={(e) => setSlotIds((ids) => (e.target.checked ? [...ids, slot.id] : ids.filter((id) => id !== slot.id)))}
                    className="accent-[var(--signal)]"
                  />
                  <span className="tabular">{formatSlot(slot.start, slot.end, slot.timezone)}</span>
                </label>
              ))}
            </div>
          )}
        </fieldset>
      )}

      {type === "supply_fact" && (
        <fieldset>
          <legend className="text-xs font-medium">Approved fact</legend>
          <div className="mt-1.5 flex flex-col gap-1">
            {(ws?.approved_facts ?? []).map((f) => (
              <label key={f.id} className="flex items-start gap-2 text-sm">
                <input
                  type="radio"
                  name={`fact-${decision.id}`}
                  checked={factId === f.id}
                  onChange={() => setFactId(f.id)}
                  className="mt-1 accent-[var(--signal)]"
                />
                {f.text}
              </label>
            ))}
            {!ws?.approved_facts.length && (
              <p className="text-2xs text-faint">
                No approved facts. <Link href="/setup#profile" className="underline">Approve one in Setup</Link>.
              </p>
            )}
          </div>
        </fieldset>
      )}

      {type === "confirm_identity" && (
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={identityChecked} onChange={(e) => setIdentityChecked(e.target.checked)} className="mt-1 accent-[var(--signal)]" />
          I checked this person&apos;s current title and employer myself.
        </label>
      )}

      {type === "reauthorize_complete" && (
        <Notice
          tone={reconnected ? "info" : "attention"}
          title={reconnected ? "Server reports Google connected with all four scopes" : `Google is ${connection?.status.replace("_", " ") ?? "not connected"}`}
          actions={
            !reconnected && (
              <Link href="/setup#google" className="text-xs underline">
                Reconnect in Setup
              </Link>
            )
          }
        >
          {reconnected ? "You can resume." : "Reconnect first. This button stays disabled until the server confirms the new connection."}
        </Notice>
      )}

      <div className="flex flex-col gap-1.5">
        <label htmlFor={noteId} className="text-xs font-medium">
          Note for the ledger
        </label>
        <Textarea id={noteId} rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why you chose this" />
        <p className="text-2xs text-muted-foreground">Required. Recorded with your resolution against conversation version {expectedVersion ?? "none"}.</p>
      </div>

      {conflict && (
        <Notice tone="attention" title="The conversation moved on">
          {resolve.error instanceof Error ? resolve.error.message : ""} Close this and review the latest state before resolving.
        </Notice>
      )}
      {resolve.error != null && !conflict && (
        <Notice tone="bad" title={describeError(resolve.error).title}>
          {describeError(resolve.error).body}
        </Notice>
      )}
      {!canResolve && <p className="text-2xs text-muted-foreground">Only owners can resolve exceptions.</p>}

      <Button type="submit" variant={type === "stop" ? "destructive" : "default"} disabled={!ready || resolve.pending} className="self-end">
        {resolve.pending ? "Recording…" : RESOLUTION[type].submit}
      </Button>
    </form>
  );
}

export function ExceptionDrawer({
  open,
  onOpenChange,
  detail,
  canResolve,
  timeZone,
  onResolved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  detail: MissionDetail;
  canResolve: boolean;
  timeZone: string;
  onResolved: (message: string) => void;
}) {
  const [index, setIndex] = useState(0);
  const exceptions = detail.open_exceptions;
  const decision = exceptions[Math.min(index, exceptions.length - 1)];

  return (
    <Sheet open={open && Boolean(decision)} onOpenChange={onOpenChange}>
      <SheetContent side="right" showCloseButton={false} className="w-[34rem] gap-0 border-hairline sm:max-w-[34rem]">
        {decision && (
          <>
            <SheetHeader className="border-b border-hairline px-5 py-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <SheetTitle className="text-base font-semibold">{humanize(decision.kind)}</SheetTitle>
                  <SheetDescription className="text-2xs">
                    Blocked <Instant value={decision.created_at} timeZone={timeZone} />
                  </SheetDescription>
                </div>
                <Button variant="ghost" size="icon-sm" aria-label="Close" onClick={() => onOpenChange(false)}>
                  <X />
                </Button>
              </div>
              {exceptions.length > 1 && (
                <div role="tablist" aria-label="Open exceptions" className="mt-3 flex gap-1">
                  {exceptions.map((e, i) => (
                    <button
                      key={e.id}
                      type="button"
                      role="tab"
                      aria-selected={i === index}
                      onClick={() => setIndex(i)}
                      className={cn("h-7 rounded-md px-2 text-xs", i === index ? "bg-raised text-foreground" : "text-muted-foreground")}
                    >
                      {humanize(e.kind)}
                    </button>
                  ))}
                </div>
              )}
            </SheetHeader>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              <p className="text-sm leading-relaxed">{decision.reason}</p>
              {decision.evidence_ids.length > 0 && <EvidenceList ids={decision.evidence_ids} className="mt-2" />}
              {decision.policy.checks.some((c) => !c.pass) && (
                <ul className="mt-3 flex flex-col gap-1 border-l border-hairline pl-3">
                  {decision.policy.checks
                    .filter((c) => !c.pass)
                    .map((c) => (
                      <li key={c.name} className="text-xs">
                        <span className="font-mono text-[0.6875rem] text-bad">{c.name}</span>{" "}
                        <span className="text-muted-foreground">{c.reason}</span>
                      </li>
                    ))}
                </ul>
              )}
              <div className="mt-5 border-t border-hairline pt-4">
                <ResolutionForm key={decision.id} decision={decision} detail={detail} canResolve={canResolve} onResolved={onResolved} />
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
