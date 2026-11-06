"use client";

import { CalendarCheck, ExternalLink } from "lucide-react";
import { useState } from "react";
import { Instant, MonoId } from "@/components/outcome/mono";
import { Section } from "@/components/outcome/panel";
import { ProvenanceStamp } from "@/components/outcome/provenance";
import { ConversationStatus, StatusChip } from "@/components/outcome/status";
import type { BookingReceipt, ConversationView, MessageView, Slot } from "@/lib/contracts";
import { formatSlot } from "@/lib/format";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

const MESSAGE_STATUS = {
  planned: { label: "Planned, not sent", tone: "quiet" },
  sent: { label: "Sent", tone: "ok" },
  received: { label: "Received", tone: "info" },
  unknown: { label: "Send outcome unknown", tone: "attention" },
} as const;

function Message({ message, sellerEmail, buyerEmail, timeZone }: { message: MessageView; sellerEmail: string; buyerEmail: string; timeZone: string }) {
  const { mode } = useSession();
  const inbound = message.direction === "inbound";
  const status = MESSAGE_STATUS[message.status];
  const when = message.received_at ?? message.sent_at;
  return (
    <li id={`msg-${message.id}`} className={cn("scroll-mt-32 py-3", inbound && "pl-6")}>
      <article
        aria-label={`${inbound ? "Reply from the simulated buyer" : "Email from the seller"}: ${message.subject}`}
        className={cn("rounded-lg border px-3.5 py-3", inbound ? "border-simbuyer/25 bg-raised" : "border-hairline")}
      >
        <header className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {inbound ? <ProvenanceStamp kind="SIMULATED_BUYER" /> : null}
          {mode === "FIXTURE" ? <ProvenanceStamp kind="FIXTURE" /> : message.provider_message_id && <ProvenanceStamp kind="LIVE" />}
          <span className="text-2xs text-muted-foreground">
            <span className="font-mono">{inbound ? buyerEmail : sellerEmail}</span>
            <span className="text-faint"> to </span>
            <span className="font-mono">{inbound ? sellerEmail : buyerEmail}</span>
          </span>
          <span className="ml-auto flex items-center gap-2">
            <StatusChip tone={status.tone}>{status.label}</StatusChip>
            <Instant value={when} timeZone={timeZone} />
          </span>
        </header>
        <p className="mt-2 text-sm font-medium">{message.subject}</p>
        <p className="mt-1 max-w-[60ch] text-sm leading-relaxed whitespace-pre-line text-foreground/90">{message.body_text}</p>
        <footer className="mt-2 flex items-center gap-1.5 text-2xs text-faint">
          Gmail id <MonoId value={message.provider_message_id} length={16} />
        </footer>
      </article>
    </li>
  );
}

export function SlotsOffered({ slots, booking, timeZone }: { slots: Slot[]; booking: BookingReceipt | null; timeZone: string }) {
  if (!slots.length) return null;
  return (
    <div className="mt-2 rounded-lg border border-hairline px-3.5 py-3">
      <div className="flex items-baseline justify-between gap-3 max-sm:flex-col max-sm:gap-0.5">
        <h3 className="text-xs font-medium">Times offered</h3>
        <p className="text-2xs text-muted-foreground">An offer, not a reservation. Free/busy is checked again before booking.</p>
      </div>
      <ul className="mt-2 divide-y divide-hairline">
        {slots.map((slot) => {
          const chosen = booking?.start === slot.start && booking.end === slot.end;
          return (
            <li key={slot.id} className="flex items-center gap-3 py-1.5 text-sm max-sm:flex-wrap max-sm:gap-y-1">
              <span className={cn("tabular max-sm:basis-full", chosen ? "font-medium text-foreground" : "text-muted-foreground")}>
                {formatSlot(slot.start, slot.end, slot.timezone)}
              </span>
              <span className="font-mono text-2xs text-faint">{formatSlot(slot.start, slot.end, "UTC")}</span>
              <span className="ml-auto flex items-center gap-2">
                <span className="text-2xs text-faint">
                  free/busy <Instant value={slot.freebusy_checked_at} timeZone={timeZone} />
                </span>
                {chosen ? <StatusChip tone="ok">Booked</StatusChip> : <StatusChip tone="quiet">Offered</StatusChip>}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function BookingReceiptView({ booking, className }: { booking: BookingReceipt; className?: string }) {
  const { mode } = useSession();
  return (
    <div className={cn("rounded-lg border border-ok/30 px-3.5 py-3", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <CalendarCheck aria-hidden className="size-4 text-ok" />
        <h3 className="text-sm font-medium">Calendar event created and read back</h3>
        <ProvenanceStamp kind={mode === "FIXTURE" ? "FIXTURE" : "LIVE"} className="ml-auto" />
      </div>
      <dl className="mt-2 grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1.5 text-xs">
        <dt className="text-muted-foreground">Seller time</dt>
        <dd className="tabular">{formatSlot(booking.start, booking.end, booking.timezone)}</dd>
        <dt className="text-muted-foreground">UTC</dt>
        <dd className="font-mono text-2xs">{formatSlot(booking.start, booking.end, "UTC")}</dd>
        <dt className="text-muted-foreground">Event id</dt>
        <dd>
          <MonoId value={booking.event_id} length={20} />
        </dd>
        <dt className="text-muted-foreground">Calendar</dt>
        <dd className="font-mono text-2xs">{booking.calendar_id}</dd>
        <dt className="text-muted-foreground">Read back</dt>
        <dd>
          <Instant value={booking.verified_at} timeZone={booking.timezone} />
        </dd>
        <dt className="text-muted-foreground">Attendee</dt>
        <dd className="text-signal">Invitation sent · acceptance not verified</dd>
      </dl>
      {booking.html_link && (
        <a href={booking.html_link} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-info underline">
          Open in Google Calendar
          <ExternalLink aria-hidden className="size-3" />
        </a>
      )}
    </div>
  );
}

function BuyerReplyBox({ campaignId, onSent }: { campaignId: string; onSent: () => void }) {
  const { client } = useSession();
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function send() {
    const body = text.trim();
    if (!body || pending) return;
    setPending(true);
    setError(null);
    try {
      await client.campaigns.buyerReply(campaignId, body);
      setText("");
      onSent();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not record the reply.");
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="mt-3 rounded-lg border border-simbuyer/30 bg-raised px-3.5 py-3">
      <label htmlFor="buyer-reply" className="text-xs font-medium">
        Reply as the test buyer
      </label>
      <p className="mt-0.5 text-2xs text-muted-foreground">
        Type what you would send from the test inbox. The worker will read this and answer.
      </p>
      <textarea
        id="buyer-reply"
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="e.g. How long is onboarding? or Thursday 10:00 works for me."
        className="mt-2 w-full resize-y rounded-md border border-hairline bg-background px-2.5 py-2 text-sm"
      />
      {error ? <p className="mt-1 text-2xs text-bad">{error}</p> : null}
      <button
        type="button"
        disabled={pending || !text.trim()}
        onClick={() => void send()}
        className="mt-2 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground disabled:opacity-50"
      >
        {pending ? "Sending…" : "Send reply"}
      </button>
    </div>
  );
}

export function ConversationThread({
  conversation,
  sellerEmail,
  timeZone,
  campaignId,
  onBuyerReply,
}: {
  conversation: ConversationView;
  sellerEmail: string;
  timeZone: string;
  campaignId?: string;
  onBuyerReply?: () => void;
}) {
  const waiting = conversation.state === "waiting_reply" || conversation.state === "waiting_slot_acceptance";
  return (
    <Section
      id="conversation"
      title="Conversation"
      description={
        <>
          Thread <MonoId value={conversation.provider_thread_id} length={16} /> · version {conversation.version} · test inbox
          playing the buyer
        </>
      }
      actions={<ConversationStatus state={conversation.state} />}
    >
      {conversation.messages.length === 0 ? (
        <p className="text-xs text-muted-foreground">No messages yet. The first email is drafted and verified before anything is sent.</p>
      ) : (
        <ol className="-my-3">
          {conversation.messages.map((m) => (
            <Message key={m.id} message={m} sellerEmail={sellerEmail} buyerEmail={conversation.buyer_test_email} timeZone={timeZone} />
          ))}
        </ol>
      )}
      <SlotsOffered slots={conversation.offered_slots} booking={conversation.booking} timeZone={timeZone} />
      {conversation.booking && <BookingReceiptView booking={conversation.booking} className="mt-2" />}
      {waiting && campaignId && onBuyerReply ? <BuyerReplyBox campaignId={campaignId} onSent={onBuyerReply} /> : null}
    </Section>
  );
}
