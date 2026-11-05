# AGENTS.md — Developer 2 only

## Who we are

We are Developer 2. The human is Developer 2, and this agent works only as Developer 2.
Do Developer 2 work: Google OAuth, Gmail, Calendar, Next.js UI, the end-to-end demo, and the video (tickets F1–F7 in document 06).
Do not take Developer 1’s tickets (B1–B8): API, database, worker, models, Crustdata, or migrations.
Read document 06 as your brief. Read document 05 only to see the boundary with D1.

This file binds the Developer 2 agent. Developer 1 does not follow it.
Branch: `feat/google-web`. Worktree or clone is separate from D1.
Contract: `outcome.v1`. No second backend, no second live worker.

## Project folder

The only project folder is `/Users/ankitkumarsingh/Downloads/context-con`.
The old folder name `outcome-ai-implementation-pack` no longer exists. Use this path for the workspace, terminals, and new files.
Create `apps/`, `services/`, tests, and notes inside this folder. Do not create a sibling folder such as `ContextCon-CrustData` or `ContextCon-backend`.

**Merge owner: Developer 2.** You merge into `main`. D1 does not. This overrides document 07, which assigned merging to D1.

## Your files (you write these)

- `apps/web/**` — Next.js UI, Supabase browser sign-in, API client, web lockfile
- `services/adapters/google/**` — Python OAuth, Gmail, Calendar protocol
- Google adapter tests and web tests
- Your own ticket notes (one file per ticket; do not edit D1’s notes)

## D1’s files (you do not edit)

- `services/api/**`, `services/core/**`, `services/worker/**`, `services/models/**`
- `services/adapters/crustdata/**`
- `db/**` and migrations
- Root Python dependency files
- Shared contract schema after it is frozen

A change there is a written request: old behavior, proposed change, reason, routes affected, owner. Both acknowledge before anyone edits. D1 lands that commit on `feat/backend-core`. You merge it to `main` after review.

## What D1 may touch in your domain

| Your path | D1 may | D1 may not |
|---|---|---|
| `services/adapters/google/` | Import and call your functions from the worker | Reimplement OAuth, MIME, Gmail, or Calendar inside the worker |
| Adapter result types | Use the agreed failure shape (`phase`, `retryability`, `may_have_applied`, `provider_status`, redacted detail) | Rename fields to match a raw Google payload |
| `apps/web/` | Read, for integration review | Edit pages, components, or the web lockfile |
| `main` | Push nothing directly. Hand you `feat/backend-core` | Merge, force-push, or resolve schema/lockfile conflicts |

You merge into `main` (or the one agreed integration branch). Before each merge, review any diff that touches Google or the UI. Merge a small checkpoint every 30–60 minutes. After the merge, both sync to that SHA before the next ticket. D1 rebases `feat/backend-core` onto the SHA you merged. You rebase `feat/google-web` the same way. No force-push of `main`.

Schema and Python lockfile conflicts are resolved with D1 before the merge. Web lockfile conflicts are yours. Do not take a blind ours/theirs on either.

## What you may touch in D1’s domain

| D1 path | You may | You stop at |
|---|---|---|
| `POST /api/v1/google/connect`, `GET /api/v1/google/callback`, `GET /api/v1/google/status` | Specify handler behavior and pair while D1 registers the route | A second FastAPI app or your own route file |
| Token store | Specify fields, rotation, and Gmail identity from an authorized profile read | Writing the migration or the encrypt/persist code |
| Worker send, poll, book | Hand over real adapter functions and provider IDs | Orchestration, slot choice, action state, CRM/handoff transaction |
| Root Python deps | Request the Google client library in one small commit D1 lands | Editing `pyproject` / requirements yourself |
| API config | Name the exact callback and web origin | Changing CORS, cookies, or secrets in D1’s config without a joint commit |
| `/api/v1` payloads | Consume them in `apps/web`; update the client when a contract change is acknowledged | Inventing routes (`/send`, `/insert-event`, simulate-reply, mark-complete) |
| `feat/backend-core` | Review, then merge that checkpoint into `main` | Rewriting D1’s backend while merging |

## Sync clock (IST)

- **23:15** — Acknowledge base SHA, directory ownership, enums, adapter result shape, callback `http://localhost:8000/api/v1/google/callback`.
- **00:00** — OAuth callback and granted scopes with D1’s auth and mission API. Broken OAuth stops UI polish; pair.
- **01:00** — Real Gmail send/read and Calendar freebusy/insert/get IDs.
- **02:00** — Merged path: real email to the actor, real reply persisted.
- **03:00** — Explicit accept, one event read-back, CRM/handoff.
- **05:00** — You own recording readiness on the release SHA.

## Side effects

Seller OAuth only. Four scopes: `gmail.readonly`, `gmail.send`, `calendar.events`, `calendar.freebusy`. Inspect the token grant. Secrets and tokens stay server-side. One consented test recipient. Unknown Gmail send returns `may_have_applied=true`. Live Google calls run only in the human-approved local or demo environment. Fixtures are labeled `FIXTURE` and never count as acceptance.
