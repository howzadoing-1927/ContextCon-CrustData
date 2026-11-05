# 09 · 23:00–07:00 runbook, fallbacks, budgets, deployment and video

## Calendar boundaries

All times IST (Asia/Kolkata). Build begins **Thursday 5 Nov 2026, 23:00**. Every time after midnight below is **Friday 6 Nov 2026**. Code freeze, repository and video due **07:00**. Submit by 06:45 if possible. Proposed internal feature freeze 06:00; organizer code freeze remains 07:00. No app code before start; the pre-event period is accounts, research and planning only.

## Hour-by-hour execution

| IST | Developer 1 | Developer 2 | Joint gate, dependency and cut |
|---|---|---|---|
| Before 23:00 Nov 5 | Read docs/account capabilities; prepare authority/criteria on paper; no app code | Check Google console/test users/scopes without app code; read OAuth docs; plan recording | Confirm rules, unknowns, credentials available, exact consent. No generated scaffolds/tests/migrations |
| 23:00–00:00 | First 15 min shared layout/types; then 12-table DB/auth/task/worker skeleton and mission API | Agree Python adapter result/error boundary; OAuth callback/token store wire; register actual URI; Google smoke | 23:15 contract SHA acknowledged; 00:00 G1. If OAuth broken, stop UI polish and pair |
| 00:00–01:00 | Website/paste facts approval; Azure two deployment smoke; live Crustdata mapping, qualification evidence | Finish Gmail send/read/threading/refresh and Calendar freebusy/insert/get; then minimal web sign-in and mission screen | 01:00 G2 live tool receipts; reduce research to 1–3 enrichments; don't optimize throughput |
| 01:00–02:00 | Draft/verifier, action outbox, send dispatcher, reply task transitions and ledger | Integrate real Python adapters and API client; setup/mode badge/mission status/messages | 02:00 merged real email→actor reply persisted. Stop adding endpoints if behind |
| 02:00–03:00 | Interpretation, opt-out, explicit slots/acceptance, booking orchestration, CRM/handoff | Calendar edge cases/read-back UI, evidence drawer and exception UI; pair on booked path | 03:00 G3. Optional mentor asks targeted blocker, not architectural redesign |
| 03:00–04:00 | Tenant/queue/idempotency/unknown-send tests, limits and policy fixes | OAuth/thread/calendar tests, allowlist/opt-out live check, deploy web/API/worker with D1 | G4 safety; remove all stretch if unfinished. One worker only |
| 04:00–05:00 | Fix critical defects, novel mission run, redacted receipts and restart checks | Stabilize deployment, clean test setup, evidence/booking/handoff screen, rehearse 2-minute recording | 05:00 G5 release candidate. Owner email only if core already passes |
| 05:00–06:00 | Support actual run, safety/claim review, repo README/test report/source boundaries | Record raw novel request run and negative case; edit with honest cuts/captions; validate playback | Internal feature freeze 06:00. No broad refactors or dependency upgrades |
| 06:00–06:30 | Final smoke on release SHA, secret scan, repo access, migration/config instructions | Export/upload video, verify permissions/audio/legibility and submission links | Pin commit/build; rerun affected checks after any blocker fix |
| 06:30–07:00 | Check repo reachable by organizer; verify final SHA and instructions; stop unnecessary tasks | Submit video+repo by 06:45, verify uploaded file/link opens | Both read receipt. Keep a 15-min upload/access buffer. No new feature work |

Take staggered short breaks during waiting/provider operations; do not let snacks/activities remove both integrators at a checkpoint. At 03:00 mentor checkpoint is optional and should resolve a concrete provider/schema blocker, not expand scope.

## Blocker deadlines and honest fallbacks

| Blocker | Investigation deadline/action | Fallback and claim boundary |
|---|---|---|
| Google redirect mismatch | By 00:00 compare exact scheme/host/path/client/registration; stable local or deployed URI; no wildcard guesses | Run local full stack with a registered callback and record honestly. No working Gmail/Calendar means complete live P0 not met |
| freebusy scope not saved/granted | D2 confirms console save + actual token grant + real query | Re-consent. Cannot replace checks with assumed availability and claim live scheduling |
| Google access denied/test user/admin policy | Check correct project/client/account and External Testing eligibility | Use an already-consenting eligible team test account. Don't publish app or broaden scopes as a casual workaround |
| Crustdata no canonical person/relationship | D1 inspects actual schema/docs; try another valid segment within mission or clarify with operator | No_match/needs_evidence; a preverified cached candidate can show UI only as CACHED and doesn't fulfill novel live research |
| Crustdata schema/auth/credit uncertainty | By 01:00 ask walkthrough/mentor with exact sanitized error and account docs | Narrow adapter to supported operations. No invented endpoint or identity from generic web search |
| Azure unsupported structured outputs | Smoke actual two deployments and endpoint/SDK path | Local schema validation + one JSON repair; explicit degraded label; unavailable models block actual LLM requirement |
| Worker hosting sleeps/serverless limit | By 03:30 use chosen always-running process deployment | Keep API+worker local on one dev machine, web locally accessible; record topology. No fake background durability |
| Website blocks fetching | Bounded fetch stops; no unsafe crawler workaround | Pasted seller source text and operator facts; label source and approval |
| Live provider latency exceeds 2 min | Measure, reduce breadth, preconnect setup, 5-sec inbox polling, direct tracked thread reads | Disclosed time-compressed video of real run; report actual duration |
| Gmail unknown send | Freeze, search/read sender evidence, bounded reconciliation | Human exception, not repeat send to make video look clean |
| Event conflict/unknown | GET fixed ID/fingerprint; requery availability; no new booking ID | Explain exception. If event known created keep it, don't claim handoff finished until persisted |
| Deployment broken at 05:00 | Stop platform switching; pair 20 min on logs/config | Stable local demo + reproducible instructions, disclose hosting gap; repo/video still due |
| Core workflow incomplete at 05:00 | Cut notifications, multi-prospect, upload parsing and polish | Show true completed stages and blockers. Don't label partial as completed SDR |

Fallbacks preserve honesty, not necessarily full acceptance. Dashboard handoff is already P0, so dropping optional owner email does not break core acceptance. Dropping real Crustdata, model, email or calendar execution does.

## Budgets, quotas and spend discipline

The prior chat mentions “over $1,500 worth of Crustdata credits.” **Dollar value, API credits, per-member allocations and pooled balances are not interchangeable.** Verify actual balance, billing unit, endpoint price, whether enrichment is asynchronous, rate limits and account entitlements at walkthrough. Do not convert $1,500 to 1,500 requests/credits. Credit abundance does not justify scope expansion.

Proposed P0 per campaign: discover 10, enrich 3, 1 conversation, 6 outbound messages total, 4 inbound reply turns, 20 model calls including retries/repairs, 10 Crustdata calls including retries, 10-minute autonomous active-run deadline excluding intentional waiting only if explicitly configured. Waiting_reply may last longer, but no silent indefinite polling: cap recording wait at 2 minutes and general P0 wait at 30 minutes, then pause/needs_human. Define these wall-clock semantics in code and ledger.

Proposed whole-night local safety caps: 30 campaign runs; 150 Crustdata calls; 300 model calls; 60 outbound messages across test accounts; 15 actual test bookings. These are ceilings to configure, not throughput goals or provider quotas. Keep only one active conversation P0, reserve capacity for final run. Tiered review at 50%/80% of local cap; stop at 100% or lower provider limit. Reconciliation reads also count toward relevant API quotas. If these caps exceed actual provider entitlements, lower them.

Allocate confirmed Crustdata budget by percentage: 10% schema/account smoke, 40% development+fault investigation, 25% rehearsals, 15% final novel run, 10% reserve. Azure token budget: 10% smoke, 45% development/evaluations, 25% rehearsal, 10% final, 10% reserve. Actual dollar ceiling remains owner-set `TBD` until balances/prices confirmed. Agent must not auto-upgrade plans or purchase credits. Record usage counters, tokens and optional estimates; unknown spend remains unknown.

Operational throttles: default one concurrent Crustdata request, two concurrent model reads/calls max but serialize a conversation, one Gmail send in flight per connected account, one booking in flight per selected calendar. Respect Retry-After and provider 429s; don't rotate accounts to evade limits. Gmail API quota is separate from mailbox sending/deliverability limits. Verify both for actual account; no published numerical quota is assumed in this pack. Avoid repeated full inbox list scans; poll only tracked threads.

## Deployment plan and responsibilities

Choose hosts already familiar and available; architecture is separate Next.js web, FastAPI API and persistent Python worker, not a specific hosting vendor promise. D2 deploys web and Google callback wiring; D1 deploys API+worker+DB migrations. A single platform can host two distinct API/worker process services if it supports persistent workers. Supabase is remote Auth/Postgres/private Storage. One worker replica P0. Disable sleep for worker or use the documented local fallback. Do not put the worker into short-lived web functions.

After 23:00 pin package versions from a successful install and commit lockfiles. Capture Python, Node, Next.js, FastAPI, OpenAI SDK, Google client libraries and Postgres server versions. Do not upgrade major versions during final hour. Set secrets in host settings; web exposes only Supabase public URL/key and public API URL. Supabase service role, database password, Google secret/refresh tokens, Azure and Crustdata keys are API/worker-only.

Deployment order: DB migration and policies → API health/auth → worker claim/heartbeat with effects disabled → web API wiring → Google actual callback registration and consent → effect allowlist/caps → enable single worker → live smoke. Configure exact CORS origins, trusted proxy/HTTPS settings, cookie SameSite/Secure behavior if used, API route base and OAuth callback consistently. Avoid logging authorization query strings. Use health readiness/worker heartbeat and correlation IDs to diagnose.

Rollback: pin previous known-good image/commit; pause campaigns and disable new effects before rollback. Never roll DB backward destructively to match old app. Forward-fix/additive migrations preferred. Reconcile executing/unknown actions before resuming. If unable to deploy reliably, freeze the local setup and document it rather than changing hosts repeatedly.

## Two-minute video storyboard (120 seconds)

| Seconds | Screen/action | Spoken point and proof |
|---|---|---|
| 0–10 | Outcome mission screen, mode badge | “Outcome performs appointment setting. Tools are real; our consenting teammate plays the buyer.” |
| 10–25 | Type unfamiliar material ICP request and launch | Show approved seller facts already configured; new request isn't a prerecorded result |
| 25–42 | Research/qualification and source drawer | Real Crustdata company/person canonical references, relationship evidence and why selected; hypotheses labeled |
| 42–58 | Gmail send receipt and actual actor inbox | Email goes to test buyer, not researched person; show receipt/thread without personal secrets |
| 58–77 | Actor replies freely, worker ingests | Reply interpretation and decision source; buyer participation is transparent |
| 77–98 | Offer/accept slot, live freebusy and event | Show explicit acceptance, fixed event reference, actual Calendar event; no invented attendee acceptance |
| 98–113 | CRM/handoff and ledger | Finished deliverable: event, buyer-stated test needs, next steps, evidence; actual IDs |
| 113–120 | Brief opt-out/ambiguous-date test and final state | Show exception/stop behavior, repository reference; say any cuts and actual runtime |

If this sequence cannot fit uncut, record full raw run then disclose cuts with timeline captions. Never hide human DB edits or replace a provider operation with animation. The negative case may be a clearly labeled second real test, not part of the same happy-path campaign. Keep text large, cursor movements minimal, voice clear. Do not expose client secrets, tokens, raw personal profiles, inbox history or unrelated events. Ask actor to avoid personal data.

## Submission checklist

Repository has product summary, simulation boundary, architecture, start instructions, environment variable names with no values, migration order, chosen dependency/API versions, honest test report/live boundaries, known gaps, source docs and video link. Include actual service entrypoints only once implemented, not guessed instructions. Pin release SHA in README/report. Secret scan staged/history content; if exposed, rotate and follow a safe remediation process before public sharing. Confirm organizer access to private repo or use required visibility, no last-minute access surprise.

Video plays from final uploaded URL with required permissions and duration, audio readable, mode disclosure present, source/ID evidence visible, any time compression disclosed. Both developers verify repo/video links in a fresh browser session without relying on owner login. Submit both before 07:00; save submission confirmation. Stop idle polling/research afterward and preserve safe final evidence. Organizer-specific submission fields, licensing and repo visibility remain to confirm.
