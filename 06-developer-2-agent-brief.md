# 06 · Developer 2 — UI, Google integrations, end-to-end demo

## Your ownership and priorities

Own `apps/web/`, `services/adapters/google/`, Google adapter tests, integration/demo documentation and web dependencies. Google adapter code is Python, because the persistent worker is Python. D1 owns FastAPI route registration, database writes/transactions, token storage abstractions, backend dependency files and orchestration; you own OAuth URL/exchange/token-refresh and Gmail/Calendar protocol behavior behind those interfaces. Pair briefly to wire routes rather than creating a second backend.

Do Google OAuth and a send/read/calendar smoke test before styling UI. Callback/scopes and runtime token grants are the biggest early blockers. Have D1 supply a credential-store interface and task/action result types at 23:15. Use a fake store only in labeled local unit tests, never the live demo.

## Ordered implementation tickets (after 23:00 only)

| Ticket | Approx. effort | Deliverable | Done when |
|---|---|---|---|
| F1 Google boundary and setup | 30 min | Confirm callback URLs and four scopes; wire OAuth initiation/callback contract | Authenticated seller connects; callback replay/foreign state rejected |
| F2 Real Google smoke | 45 min | Gmail MIME/send/thread-read, token refresh, Calendar freebusy/insert/get | Test email and reply plus disposable event actually appear; IDs retained |
| F3 UI skeleton | 40 min | Supabase sign-in, workspace setup, mission form/detail, API client | Authenticated browser launches a persisted mission |
| F4 Conversation/ledger UI | 40 min | Poll status, messages, evidence drawers, fact/hypothesis labels, exceptions | Real worker changes visible; raw provider HTML never rendered |
| F5 Scheduling integration | 40 min | Slot/freebusy/event adapter edge cases; explicit actor-reply protocol | Accepted slot creates one verified real event; no hardcoded booking |
| F6 Completion and release | 45 min | CRM/handoff card, owner notice if time, deploy web/API wiring | Browser shows actual event, summary, open questions and next steps |
| F7 Rehearse/record | 75–90 min | Novel request, negative case, two-minute storyboard, final artifacts | Video and repo submitted before 07:00 |

D2 is not also responsible for making backend orchestration while D1 is absent. If backend slips, use the agreed labeled contract fixtures for UI development while pairing on the one real integration path. Fixtures never count as provider acceptance.

## Exact OAuth responsibilities

- Use server authorization-code flow; client secret and tokens never enter Next.js browser code. Request offline access; retain existing refresh token when a refresh/reauthorization response omits a new one. Don't overwrite it with null.
- Store expiring random single-use state hashed in pending connection, bound to org, initiator and safe return path. Validate and consume atomically. Callback has no Supabase bearer header; valid stored state establishes the initiated flow. Bind browser initiation/session securely and reject wrong-session callbacks as feasible for the chosen cookie architecture. Do not rely on unverified query tenant/user fields.
- Redirect URI must exactly match registered value and actual scheme/host/path. Proposed local URI: `http://localhost:8000/api/v1/google/callback`. Deployed URI: `https://<chosen-api-host>/api/v1/google/callback`. These are proposed, not already registered. Use a stable HTTPS deployment hostname for recording; re-consent with the right callback.
- Request exactly Gmail readonly/send and Calendar events/freebusy scopes listed in 10. Console selection is not proof the resulting token has them; inspect returned/granted scopes and test each operation.
- Seller account is the connected sender/calendar owner. Actor can reply manually in Gmail and need not connect its inbox to the app. Do not add a second OAuth connection unless automated buyer simulation is stretch and separately authorized. The existing three test users merely allow OAuth for those accounts.
- Encrypt tokens using a server-only maintained crypto library/key. D1 owns persistence; you specify fields/rotation and account identity from an authorized Gmail profile read if supported by granted scope. Never trust an email supplied by the browser as connected identity.
- Serialize refresh per connection to avoid token races; one refresh retry for expired access token; invalid_grant→reauth_required. No embedded service account or organizer credentials as workaround.

Google's server flow and testing refresh-token behavior are documented in [OAuth web-server guide](https://developers.google.com/identity/protocols/oauth2/web-server) and [OAuth overview](https://developers.google.com/identity/protocols/oauth2). Read full account-compatible docs during implementation; do not treat this planning checklist as a replacement SDK reference.

## Gmail correctness

Construct RFC-compliant plain-text MIME and base64url `raw`; server pins From/To and persists Message-ID. Use returned Gmail message ID and thread ID. Reply uses same Gmail threadId, matching subject and correct In-Reply-To/References headers per [thread guide](https://developers.google.com/workspace/gmail/api/guides/threads). Keep Gmail internal IDs distinct from RFC Message-ID.

Poll only tracked sender threads for active conversations on a worker schedule, default every 5 seconds in recording, slower otherwise. Gmail thread IDs are mailbox-scoped: use IDs from the connected seller mailbox, not the buyer's UI. Thread response may contain already-seen outbound and inbound messages. Deduplicate provider message IDs, inspect sender against exact buyer allowlist, ignore own mail, detect automated messages/bounces, normalize MIME text with bounded size, and order messages using provider data with stable ID tie-breaks. Newest relevant buyer message plus current state drives the next turn. Do not rely on subject or unread flags; readonly scope cannot mark read, so DB deduplication is essential.

Unknown network send outcomes produce typed `may_have_applied=true`, not a generic exception that worker retries. Gmail send endpoint does not establish a local idempotency guarantee ([messages.send](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send)). Reconciliation returns positive evidence or unresolved, never an immediate “not sent” from absent search result.

## Calendar correctness

Selected calendar is server-bound, initially `primary` only if verified for connected seller. Query free/busy for bounded upcoming working hours, verify per-calendar errors, compute candidate slots excluding busy periods with a small buffer (default 5 minutes). Test a known busy slot and an open slot; lack of a response is failure, not free time. Explicitly include timezone/offset. DST/timezone ambiguity must clarify. Calendar create includes fixed event ID/fingerprint, test-only attendees and simulation label; read-back verifies start/end/calendar/attendees. Do not promise video-conference links. D1 owns slot selection and action state; you implement provider mapping/typed results. See [freebusy.query](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query) and [events.insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert).

## UI acceptance details

- One consistent mode badge: “Live tools · simulated buyer.” Per-step provenance: LIVE / CACHED / FIXTURE. Never use “live” for a replayed provider response.
- Clearly separate real researched company/person from “test inbox playing buyer.” Real person email isn't a selectable send destination.
- Show observed facts, approved seller facts and hypotheses in separate labels. Each fact opens evidence excerpt, provider/source reference, retrieval time and underlying as-of if available.
- Show stage, last action, last heartbeat and next expected event. Waiting for a buyer is not a spinner implying ongoing model work. Worker stale/dependency unavailable gets useful status.
- Display exceptions with concise reason and permitted resolution. No “approve all” or “force send” button. Pause/stop feedback distinguishes pending and in-flight effects.
- Completed card derives from API state/receipt, not local animation. Event link optional; never fabricate it. Never label invited attendee “accepted.”
- Unauthorized routes, empty states, no-match, reauthorization and failed provider requests must render without crashing. Clean readable layout matters more than charts.

## Copy-paste primary Cursor Agent prompt

> You are Developer 2's implementation agent for Outcome AI. No application code/scaffolding/tests before 23:00 Asia/Kolkata on 5 November 2026; before then only planning Markdown. Start implementation only when the developer starts it at or after that time. Read README and 01–04, 06–11. Own apps/web, services/adapters/google and Google/web tests; do not edit D1's API/worker/models/DB/migrations/Python dependency files without a coordinated request. Build Google adapters in Python and agree interfaces with D1 at the first checkpoint. First verify OAuth callbacks/scopes, seller account send/read/freebusy/create/read-back with real consented test accounts. Then build a small Next.js interface with Supabase Auth and exact /api/v1 payloads. Secrets/tokens remain server-only; validate OAuth state and exact callback, inspect granted scopes, encrypt token storage through D1's store. Gmail readonly polling uses tracked seller threads and provider-ID dedupe; no mark-as-read assumption. MIME construction pins one consented test To and no Cc/Bcc, rejects raw model headers, handles threading correctly. Never send or invite a researched person. Ambiguous send returns may_have_applied and blocks blind retry. Calendar uses live checks, explicit accepted slot, deterministic event ID/fingerprint and read-back; never imply freebusy+insert is atomic or Meet exists. UI shows real researched identity separately from simulated buyer, facts versus hypotheses, ledger evidence and honest LIVE/CACHED/FIXTURE labels. Work in your assigned worktree/branch. Use only labeled fixtures for UI development, never acceptance. Deliver one real campaign→email→reply→calendar→CRM/handoff integration before polish. Return changed paths, actual tests/results, provider operations actually run, contract changes needed and next checkpoint. Do not fabricate successes or expand stretch scope.

## Cursor background/cloud prompt wrapper

> Apply the D2 role prompt above to ticket [F-number], starting from commit [base SHA] on branch [branch]. You may change only [allowed paths]. Deliver a reviewable branch/PR; do not merge or deploy. Use fixture adapters and no live Google credentials in this remote environment. State explicitly which tests ran here and which live tests must run locally. Do not create another production worker or trigger real sends/calendar writes. If the environment cannot install/run required checks, report the blocker rather than claiming verification.

Use cloud/background mode only if already working with repo access and a usable environment. Current Cursor official docs call this Cloud Agents; exact menus and plan availability may differ from installed “Background Agent” terminology ([official guide](https://cursor.com/docs/cloud-agent)). For OAuth/live side effects, prefer the primary local Agent session controlled by D2.

## Codex alternative and recording handoff

Paste the same D2 primary prompt into an isolated Codex worktree chat and give it ticket/base SHA/allowed paths. Codex is an alternative, not an additional writer on the same checkout. Use account-available models; do not assume availability or UI commands. Keep primary integration and actor Gmail session accessible locally.

By 05:00 D2 owns recording readiness: stable deployed URL, seller setup preconnected, clean test inbox, calendar open to correct date, unfamiliar mission chosen by the other developer, scenario not hardcoded, secrets hidden, provider IDs and ledger visible. Buyer actor sends a genuine reply manually; no direct DB/API injection. Preserve raw capture as well as edited final and state any time cuts.
