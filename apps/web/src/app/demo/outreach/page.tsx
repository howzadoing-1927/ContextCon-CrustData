"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ConversationThread } from "@/components/mission/conversation";
import { Notice } from "@/components/outcome/panel";
import { CampaignStatus, ConversationStatus } from "@/components/outcome/status";
import { ModeBadge, ProvenanceStamp } from "@/components/outcome/provenance";
import { BEATS, SELLER, TZ } from "./story";
import { cn } from "@/lib/utils";
import { Suspense } from "react";

function OutreachStory() {
  const params = useSearchParams();
  const pinned = Number(params.get("frame") ?? "");
  const [index, setIndex] = useState(Number.isInteger(pinned) && pinned >= 1 && pinned <= BEATS.length ? pinned - 1 : 0);
  const beat = BEATS[index];
  const conversation =
    params.get("focus") === "end" && beat.conversation.messages.length > 3
      ? {
          ...beat.conversation,
          messages: beat.conversation.messages.slice(-3),
        }
      : beat.conversation;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight" || event.key === " ") {
        event.preventDefault();
        setIndex((i) => Math.min(BEATS.length - 1, i + 1));
      }
      if (event.key === "ArrowLeft") setIndex((i) => Math.max(0, i - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (params.get("play") === "0" || params.get("frame")) return;
    const timer = window.setInterval(() => {
      setIndex((i) => (i + 1) % BEATS.length);
    }, 7000);
    return () => window.clearInterval(timer);
  }, [params]);

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-hairline bg-shell">
        <div className="flex h-12 items-center gap-6 px-5">
          <Link href="/missions" className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            <span aria-hidden className="grid size-5 place-items-center rounded-sm bg-primary text-[0.625rem] font-bold text-primary-foreground">
              O
            </span>
            Outcome AI
          </Link>
          <nav className="flex items-center gap-1 text-xs">
            <span className="relative px-2.5 text-foreground">
              Missions
              <span aria-hidden className="absolute inset-x-2.5 bottom-[-14px] h-0.5 rounded-full bg-foreground" />
            </span>
            <span className="px-2.5 text-muted-foreground">New mission</span>
            <span className="px-2.5 text-muted-foreground">Setup</span>
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <ProvenanceStamp kind="SIMULATED_BUYER" />
            <ModeBadge />
            <div className="text-right leading-tight">
              <p className="text-xs font-medium">Toast Inc</p>
              <p className="text-2xs text-faint">owner</p>
            </div>
          </div>
        </div>
      </header>

      <div className="border-b border-hairline px-6 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <CampaignStatus status={beat.conversation.state === "booked" ? "completed" : beat.conversation.state === "declined" ? "completed" : "waiting_reply"} />
          <ConversationStatus state={beat.conversation.state} />
          <span className="text-2xs text-muted-foreground">Toast Inc · restaurant owners in India</span>
        </div>
        <h1 className="mt-2 max-w-[28ch] text-2xl font-semibold tracking-tight">{beat.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {beat.person}, {beat.company}
          <span className="text-faint"> · {beat.place}</span>
          {beat.email ? <span className="font-mono text-2xs"> · {beat.email}</span> : <span className="text-2xs"> · via burgersinghonline.com</span>}
        </p>
        <ol className="mt-3 flex gap-1.5" aria-label="Story beats">
          {BEATS.map((item, i) => (
            <li key={item.slug}>
              <button
                type="button"
                onClick={() => setIndex(i)}
                className={cn(
                  "h-1.5 w-10 rounded-full",
                  i === index ? "bg-foreground" : "bg-hairline hover:bg-muted-foreground/40",
                )}
                aria-current={i === index}
                aria-label={item.title}
              />
            </li>
          ))}
        </ol>
      </div>

      <main className="mx-auto max-w-3xl px-6 py-6">
        {beat.leftAlone && (
          <Notice tone="quiet" title="The buyer declined" className="mb-4">
            No follow-up is sent and no meeting is booked. The agent leaves this person alone.
          </Notice>
        )}
        <ConversationThread conversation={conversation} sellerEmail={SELLER} timeZone={TZ} />
      </main>
    </div>
  );
}

export default function OutreachDemoPage() {
  return (
    <Suspense>
      <OutreachStory />
    </Suspense>
  );
}
