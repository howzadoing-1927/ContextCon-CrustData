"use client";

import { Check, Minus } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { MonoId } from "@/components/outcome/mono";
import { Notice, Section } from "@/components/outcome/panel";
import { StatusChip, type Tone } from "@/components/outcome/status";
import { Button } from "@/components/ui/button";
import { describeError } from "@/lib/api/errors";
import type { ConnectionStatus, OrganizationView } from "@/lib/contracts";
import { REQUIRED_GOOGLE_SCOPES } from "@/lib/contracts";
import { useSession } from "@/lib/session";
import { useMutation } from "@/lib/use-mutation";

const SCOPE_LABEL: Record<(typeof REQUIRED_GOOGLE_SCOPES)[number], string> = {
  "https://www.googleapis.com/auth/gmail.readonly": "Read the mission thread",
  "https://www.googleapis.com/auth/gmail.send": "Send from the seller mailbox",
  "https://www.googleapis.com/auth/calendar.events": "Create and read back the meeting",
  "https://www.googleapis.com/auth/calendar.freebusy": "Check free/busy before offering slots",
};

const STATUS: Record<ConnectionStatus | "none", { label: string; tone: Tone }> = {
  none: { label: "Not connected", tone: "quiet" },
  pending: { label: "Waiting for consent", tone: "wait" },
  connected: { label: "Connected", tone: "ok" },
  reauth_required: { label: "Needs reauthorization", tone: "attention" },
  revoked: { label: "Revoked", tone: "bad" },
};

export function GoogleSection({
  workspace,
  canEdit,
  onChanged,
}: {
  workspace: OrganizationView;
  canEdit: boolean;
  onChanged: () => void;
}) {
  const { client, mode } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const callback = params.get("google");
  const connection = workspace.connection;
  const status = STATUS[connection?.status ?? "none"];
  const granted = new Set(connection?.granted_scopes ?? []);
  const missing = REQUIRED_GOOGLE_SCOPES.filter((s) => !granted.has(s));
  const healthy = connection?.status === "connected" && missing.length === 0;
  const connect = useMutation("google-connect", (_: void, key: string) => client.google.connect(key));

  async function start() {
    const result = await connect.run();
    if (!result) return;
    if (mode === "FIXTURE") {
      router.replace(result.authorization_url, { scroll: false });
      onChanged();
    } else {
      window.location.assign(result.authorization_url);
    }
  }

  const action = !connection ? "Connect Google" : healthy ? "Reconnect" : "Reauthorize Google";

  return (
    <Section
      id="google"
      title="Google connection"
      description="The seller mailbox sends and reads the thread; the seller calendar is checked and booked. Tokens stay on the server."
      actions={<StatusChip tone={status.tone}>{status.label}</StatusChip>}
    >
      {callback === "fixture-consent" && (
        <Notice tone="fixture" className="mb-4" title="Fixture consent completed">
          No Google screen was shown. The connection below is synthetic and labeled FIXTURE.
        </Notice>
      )}
      {callback === "connected" && (
        <Notice tone="info" className="mb-4" title="Google returned you here">
          Status below is read from the server, not from the redirect.
        </Notice>
      )}
      {callback === "error" && (
        <Notice tone="bad" className="mb-4" title="Google consent didn't complete">
          {params.get("reason") ?? "The consent screen was closed or refused."} Nothing was stored.
        </Notice>
      )}

      <div className="grid grid-cols-[1fr_1.4fr] gap-6">
        <dl className="flex flex-col gap-2 text-xs">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-muted-foreground">Account</dt>
            <dd className="font-mono text-2xs">{connection?.account_email ?? <span className="text-faint">none</span>}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-muted-foreground">Calendar</dt>
            <dd className="font-mono text-2xs">{connection?.calendar_id ?? <span className="text-faint">none</span>}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-muted-foreground">Connection</dt>
            <dd>
              <MonoId value={connection?.connection_id} />
            </dd>
          </div>
        </dl>

        <table className="w-full text-left text-xs">
          <caption className="sr-only">Required Google scopes and whether each is granted</caption>
          <thead className="text-2xs text-faint">
            <tr>
              <th scope="col" className="pb-1.5 font-medium">
                Required scope
              </th>
              <th scope="col" className="pb-1.5 text-right font-medium">
                Granted
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline border-t border-hairline">
            {REQUIRED_GOOGLE_SCOPES.map((scope) => {
              const ok = granted.has(scope);
              return (
                <tr key={scope}>
                  <td className="py-1.5 pr-3">
                    <p>{SCOPE_LABEL[scope]}</p>
                    <p className="font-mono text-[0.6875rem] text-faint">{scope.replace("https://www.googleapis.com/auth/", "")}</p>
                  </td>
                  <td className="py-1.5 text-right">
                    {ok ? (
                      <span className="inline-flex items-center gap-1 text-ok">
                        <Check aria-hidden className="size-3.5" />
                        Yes
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-signal">
                        <Minus aria-hidden className="size-3.5" />
                        Missing
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {connection?.status === "reauth_required" && (
        <Notice tone="attention" className="mt-4" title="Google stopped accepting this connection">
          Missions that need to send, read or book are blocked until an owner reauthorizes. Already-sent mail is unaffected.
        </Notice>
      )}

      {canEdit && (
        <div className="mt-4 flex items-center justify-end gap-3">
          {connect.error != null && <span className="text-2xs text-bad">{describeError(connect.error).title}</span>}
          <Button variant={healthy ? "outline" : "default"} onClick={start} disabled={connect.pending}>
            {connect.pending ? "Opening Google…" : action}
          </Button>
        </div>
      )}
    </Section>
  );
}
