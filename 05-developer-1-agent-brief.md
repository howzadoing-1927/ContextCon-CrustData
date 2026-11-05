# 05 · Developer 1 — backend, research, orchestration, models and database

## Your ownership and first priority

You are the backend integrator, not a third floating developer. Own `services/api/`, `services/core/`, `services/worker/`, `services/models/`, `services/adapters/crustdata/`, `db/`, authoritative API contracts, Python dependencies and backend tests. D2 owns `services/adapters/google/` even though it is Python. Do not implement competing Google helpers or frontend components. Decide integration conflicts together; do not silently change shared payloads.

Your first deliverable is a thin persistent path that accepts a mission, writes a task, transitions state and returns it to UI. Then replace labeled contract fixtures with real research/model/Google adapter calls. Do not finish every backend module before joining D2's branch. One real prospect and booking is the target, not maximum research volume.

## Ordered implementation tickets (after 23:00 only)

| Ticket | Approx. effort | Deliverable | Done when |
|---|---|---|---|
| B1 Contract baseline | 15 min | Repository layout, versioned types/OpenAPI skeleton, shared enum values, future config names | D2 can call health and parse CampaignView; no unagreed route rename |
| B2 Persistent foundation | 45 min | Twelve-table migration, memberships, app JWT checks, private evidence bucket, task/action primitives | Launch persists; worker restart reclaims task; foreign tenant denied |
| B3 Mission/profile path | 30 min | Website/paste source, approval snapshot, normalize_mission model call | New request produces validated plan; unsupported seller facts cannot launch |
| B4 Crustdata vertical slice | 45 min | Verified account request mapping, canonical company/person refs, evidence snapshots and dedupe | One live company/person relationship mapped with provenance; missing fields explicit |
| B5 Qualification/draft | 35 min | Rules, draft and semantic verifier, Decision Ledger | Unknown must-have blocked; grounded draft ready for D2 adapter |
| B6 Durable conversation | 50 min | Send action dispatcher, inbox handler, slot/booking tasks, suppression and caps | Real reply generates safe next action; no fixture in acceptance run |
| B7 Finish and hardening | 45 min | Event receipt→CRM/handoff transaction; ambiguity/retry/lease handling | Repeated accepted message creates one booking; handoff survives restart |
| B8 Release support | Remainder | Live acceptance, fixes, redacted evidence, deployment health | Mandatory gates in 08 pass on release commit |

Estimates are planning allocations, not additive commitments; parallel human review and D2 integration overlap. If behind, cut research breadth and dashboard polish, not persistent state or side-effect safety.

## Copy-paste primary Cursor Agent prompt

> You are Developer 1's implementation agent for Outcome AI. FIRST check the actual current time: no application code, scaffolding, migrations, tests, scripts or dependency setup may be written before 23:00 Asia/Kolkata on 5 November 2026. Before that, only review and improve planning Markdown; do not start coding on a timer. After the developer explicitly starts implementation at or after that boundary, read README and documents 01–04, 07–11. Latest pack supersedes prior four-person/27-table plans. Build the minimal real vertical slice for two developers. Own only services/api, services/core, services/worker, services/models, services/adapters/crustdata, db, backend tests and approved shared contracts/Python dependencies. Developer 2 owns apps/web and services/adapters/google. Work only in your assigned branch/worktree; never edit the other's checkout or deploy a second live worker. Use the exact /api/v1 contracts and twelve application tables. Implement coarse persistent leased Postgres tasks with fencing, append-only reason/source decisions and durable actions. Supabase JWT membership checks plus tenant-scoped queries and tested RLS are mandatory. Implement two configurable Azure deployments with account-verified API/SDK/schema support, no invented model names. Use actual Crustdata canonical company/person identity and evidence, verifying endpoint/filter/ID/credit details against authenticated docs; do not guess. Models propose JSON; code enforces policy and executes tools. Simulation permits only exact consented test destinations; researched email addresses cannot become To/Cc/Bcc, Reply-To or attendees. Gmail ambiguous send must quarantine and reconcile, never blindly retry. Calendar uses fixed booking key/event ID and read-back. P0 completes one campaign/conversation/booking/internal CRM/handoff. Implement B1 then B2 and publish a small integrated checkpoint before expanding. Use labeled fixtures only for isolated development; remove them from the live acceptance path. Never claim tests/provider actions ran unless they did. Return changed files, migration/contract version, actual tests with results, known limitations and next integration step after each ticket. Ask only for unresolved business authority or unavailable credentials; make routine implementation choices within the pack. Do not add stretch features or refactor unrelated files.

## Incremental prompts to send after reviewing each checkpoint

**B1/B2 — foundation**

> Implement only the persistent mission/task/auth skeleton from sections 02–03. Establish contract v1.0 and validate the twelve-table relationships, including messages.connection_id, action uniqueness and composite tenant FKs. Do not wait for Google adapters: define the exact shared protocol and a fixture-only test adapter. Add meaningful tests for foreign-tenant access, duplicate launch, worker crash/reclaim and stale lease completion. Return a migration plan, test results and example real API response. Do not claim live tool acceptance yet.

**B3–B5 — research/model slice**

> On the integrated baseline, implement approved seller facts, safe bounded website/paste ingestion, mission normalization, Crustdata canonical identity/evidence, deterministic qualification, draft/semantic verification and ledger. Verify actual provider request/response mapping first; maintain a source/field/version note. Missing person ID or employment support prevents outreach, not invented identity. A hypothesis is never a fact. Use two configured Azure deployments and validate schemas locally. Finish with one live research receipt and no outbound effect until D2 integration passes recipient safety.

**B6/B7 — effect integration**

> Integrate Developer 2's real Python Google adapters into the worker. Persist immutable action before Gmail send, handle ambiguous results and thread-matched new inbound IDs, implement stop/suppression first, then two-slot offer/explicit acceptance/live recheck/idempotent calendar creation/read-back. Complete CRM/handoff from actual event receipt. Prove replay and crash cases do not blindly duplicate sends/events. Work against the current shared branch baseline; coordinate any contract change with D2 before editing.

**Final hardening**

> Freeze scope. Run required gates in 08 against the exact release commit/environment. Focus fixes on tenant leakage, unauthorized recipient paths, duplicate/ambiguous effects, missing evidence and state durability. Report all failures and remaining limitations plainly. Do not replace failing live adapters with fixtures or mark no_match/needs_human as complete. Prepare safe provider-ID/decision evidence for D2's video without secrets or real personal emails.

## Codex alternative

Use the same role prompt and ticket prompts in a Codex local worktree chat. Select an available capable coding model already accessible to the account; do not spend the night migrating tools or chasing an unverified model name. Give the chat the repository, branch/base commit, allowed paths and current ticket. If using cloud execution, it must have the repository, dependency environment and fixture inputs; live keys stay only in approved environment. A cloud agent without Google OAuth callback connectivity cannot own the full live acceptance test. Let local human-controlled integration run it. Native worktree creation/control is preferable to asking an agent to edit another worktree.

## Handoff record after every ticket

Write a short development note after 23:00: ticket ID, base and head commits, owned paths changed, contract/migration versions, exact checks run and results, provider calls actually performed, safe environment variable names added, unresolved issues, merge order and next task. Never paste secret values. Flag possible credential exposure immediately and rotate via approved account controls. D1 alone applies migrations to shared demo DB; agents may test on isolated databases after permission/configuration is clear.
