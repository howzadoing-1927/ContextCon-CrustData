# 10 · Setup checklist, configuration and unresolved decisions

## Before 23:00: planning/account preparation only

No application files, scaffold, migration, test, infrastructure script or runnable project setup generated before the build start. These Markdown specifications and agent prompts are planning artifacts. Do not paste implementation prompts into an automatically executing agent early. Account console preparation, documentation reading, sketching and credential availability are permitted by the supplied brief. Confirm any organizer-specific interpretation at kickoff. Do not pre-generate the application and merely delay committing it.

### Shared account readiness

- [ ] Both developers can access repository host and their existing Cursor/Codex tool; verify plan/access without assuming model availability.
- [ ] Confirm event start/deadline/submission fields and video rules; assign D1 backend integrator and D2 Google/UI/demo.
- [ ] Confirm Supabase project, region, project URL, Auth method, database connection route and private Storage availability. Record actual Postgres version after start. Do not create app schema early.
- [ ] Choose simple Supabase login path that is already accessible to both developers; email/password or supported login is an implementation choice after start. Do not confuse app sign-in with Google tool consent.
- [ ] Confirm Crustdata API key/MCP access, permitted company/person operations, account docs, canonical ID fields, relationship representation, credits, billing units, rate/concurrency limits and relevant coverage. Prefer supported REST for P0 unless MCP already works; do not integrate both just to tick a box.
- [ ] Confirm Azure resource endpoint and two actual deployment names. Record model/version/context/structured-output support, authentication, quota and region availability from account. Set no speculative version/model defaults.
- [ ] Seller provides website and a short set of actual approved product features, limitations, FAQ/pricing authority, ICP/exclusions and handoff owner. No Vedora product claims are supplied by this pack. Prepare text, not app ingestion code.
- [ ] Choose consenting test seller and buyer accounts; capture exact consent reference. Test recipient list is distinct from Google test-user list. No researched person is contacted.
- [ ] Choose familiar web/API/persistent-worker hosting; confirm background process can stay running. Local fallback documented. Do not prebuild app deployment files.

### Google status from supplied context: facts vs verification

| Item | Reported state | Required action / owner |
|---|---|---|
| Cloud project | Prior context calls it Outcome-Hackathon | D2 verifies correct project; name not a guarantee of access |
| OAuth audience | External / Testing | Keep scope limited to test use; verify actual console state |
| Test users | Three reportedly added | Verify exact accounts needed for authorizing app; do not expose addresses in repo |
| Web application OAuth client | Created previously | Verify client accessible and secret securely stored |
| Callback URIs | Not yet set | Register exact local/deployed callback matching chosen route; do not retain old /auth/google/callback examples if actual route is /api/v1/google/callback |
| Gmail scopes | readonly/send reportedly selected | Verify saved configuration and later token grants/actual send/read |
| Calendar events | Reportedly selected | Verify saved config and later event create/get |
| Calendar freebusy | Addition requested, save unverified | Reopen Data Access, confirm selected, Update/Save as applicable; later token grant and real freebusy query |
| APIs enabled | Prior guidance asked to verify, no definitive live inspection here | Confirm Gmail API + Google Calendar API enabled; scope selection alone insufficient |
| Authorized sender/token | Not yet proved | Actual OAuth and smoke after implementation begins |

Exact scope strings:

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.send`
- `https://www.googleapis.com/auth/calendar.events`
- `https://www.googleapis.com/auth/calendar.freebusy`

Don't replace these with broad full-mail/full-calendar access to make errors disappear. Adding console scopes does not retroactively update tokens; request required scopes in authorization and re-consent when needed. Scope grant proof is runtime, not a screenshot alone. Refresh tokens for External Testing with these non-profile scopes have a documented seven-day expiry condition; plan reauthorization rather than production availability claims ([Google OAuth overview](https://developers.google.com/identity/protocols/oauth2)). Restrictions from Workspace administration may still apply. Public rollout/verification/security assessment is outside tonight's P0 and must not be advertised as solved.

### Design decisions to close before/at 23:15

| Decision | Proposed default | Owner and evidence needed |
|---|---|---|
| API origin/callback | local port 8000, path /api/v1/google/callback; deployed stable HTTPS API host | D2 exact host/client registration |
| Browser API routing | browser calls API with Supabase token and explicit org header | D1/D2 CORS and Auth contract smoke |
| Google seller calendar | verified connected seller primary calendar | D2 actual calendar/freebusy permissions |
| Actor timezone | explicit Asia/Kolkata for first test | Operator approval, not inferred from inbox |
| Meeting rules | 15 min, weekday 09:00–17:00, 5-min buffer | Operator can configure, validate future slots |
| Test-send window | overnight sends allowed only to consenting test inbox | Operator explicit policy; meeting hours remain daytime |
| CRM/handoff | internal persistent dashboard first, owner email optional | Both confirm judging narrative |
| Prospect breadth | 10 discovered/3 enriched/1 conversation | Lower if actual quota/coverage needs |
| Seller ingestion | one safe homepage fetch + paste/approve facts | D1 SSRF and source boundaries |
| Crustdata transport | REST adapter if verified; MCP alternative only if account working | D1 auth/schema smoke |
| Azure API path | one supported SDK/API family verified for both deployments | D1 deployment smoke; no mixed conventions |
| Hosting | familiar separate API and persistent worker process services | Both confirm uptime/access; local fallback |

## After 23:00: implementation readiness checklist

- [ ] Create repo/scaffold only now; copy pack into docs. Agree contract SHA, branch ownership and isolated worktrees.
- [ ] Install dependencies and pin actual versions/lockfiles. Generate executable schemas/OpenAPI from section 03, not a parallel incompatible design.
- [ ] Apply twelve-table migration and nonrecursive RLS policies; create private bucket; membership seed via trusted server/admin path.
- [ ] Configure Supabase Auth redirect/login as needed; test expired/foreign JWT, wrong org, direct RLS and private Storage.
- [ ] Set backend/worker secrets, separate browser-safe values; no secret under NEXT_PUBLIC prefix.
- [ ] Add exact Google callback registration; complete seller OAuth with all required granted scopes; token encryption and refresh path verified.
- [ ] Exercise Gmail send/read, Calendar freebusy/create/get using consented test accounts. Keep real provider IDs privately.
- [ ] Capture Crustdata authentic response and map canonical refs/relationship/missing fields. Snapshot actual request schema/version reference.
- [ ] Smoke two Azure deployments and local schema validation, inspect usage/metadata. Update model capability register.
- [ ] Test one task claim/reclaim, lease fencing, action uniqueness, unknown effect quarantine and worker restart.
- [ ] Build UI against frozen types; label fixtures and exclude them from live acceptance.
- [ ] Deploy API/worker/web in order; verify exact origins, one live worker, readiness and heartbeat.
- [ ] Run G1–G6 and save redacted results against final commit.

## Configuration register (names are our design, values remain private/TBD)

| Variable/group | Where | Meaning / verification |
|---|---|---|
| NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY | Web/browser | Public project credentials only; RLS required. If project uses a newer public publishable key format, name/document it consistently; don't put service role here |
| NEXT_PUBLIC_API_BASE_URL | Web/browser | Exact API origin/base; no secret |
| SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY | API/worker only | Server access; bypass implications tested |
| DATABASE_URL | API/worker only | Correct connection/pooling mode; don't assume session features work with transaction pooling |
| STORAGE_BUCKET | API/worker | Private evidence bucket, org path prefix |
| GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI | API; refresh worker as needed | Exact OAuth client/callback; secret private |
| TOKEN_ENCRYPTION_KEY, TOKEN_ENCRYPTION_KEY_VERSION | API/worker secret store | Maintained library with authenticated encryption; stable across restarts |
| AZURE_OPENAI_ENDPOINT | Worker | Actual account endpoint; SDK family matches |
| AZURE_OPENAI_DECISION_DEPLOYMENT, AZURE_OPENAI_FAST_DEPLOYMENT | Worker | Two actual deployment names |
| AZURE_OPENAI_API_KEY or chosen managed auth settings | Worker | Use one account-supported auth method |
| AZURE_OPENAI_API_VERSION | Worker if chosen API requires it | Populate verified version, not an assumed latest; v1-style path may differ |
| CRUSTDATA_API_KEY, CRUSTDATA_BASE_URL | Worker | Actual account auth/base URL; transport mapping verified |
| API_PUBLIC_ORIGIN, WEB_PUBLIC_ORIGIN, ALLOWED_CORS_ORIGINS | API | Exact trusted origins, callback and safe redirects |
| SIMULATION_ONLY=true, LIVE_EFFECTS_ENABLED | API/worker | Hard global simulation restriction; effects initially disabled until setup verified |
| WORKER_ID, TASK_LEASE_SECONDS, PROVIDER_TIMEOUT_SECONDS | Worker | Unique worker and measured timeouts; lease fencing mandatory |
| LOCAL_NIGHT_*_CAP, CAMPAIGN_DEFAULT_*_CAP | API/worker | Explicit application counters, lower than actual quota |

Do not place consented recipients solely in environment if UI/DB policy can silently diverge. Database owner policy is primary scoped authority; optional deployment allowlist is an additional restrictive check (intersection, never union). Secrets must be excluded from logs, screenshots, PRs, fixture files and model inputs. No actual environment file is delivered in this planning pack.

## Unresolved-item register at pack handoff

U1 event rules/submission visibility; U2 exact Google callback hosts and saved freebusy scope; U3 runtime Google grants/account restrictions; U4 Crustdata authenticated endpoint/filter/schema/ID/relationship/credit details; U5 Azure deployment names/versions/SDK/API capability and quotas; U6 seller-approved Vedora or alternative business facts; U7 confirmed actor consent/email/timezone; U8 deployment hosts/budgets; U9 exact Supabase project/Auth/key/pooling configuration. Owners: D2 U2/U3/U7, D1 U4/U5/U6/U9, both U1/U8. Any unresolved item that governs authority or safety blocks that effect; other routine engineering choices can use defaults and be recorded.
