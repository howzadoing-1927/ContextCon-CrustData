# D1 → D2 contract checkpoint (B1 + B2)

- Contract: `outcome.v1`, planning baseline 1.0, prefix `/api/v1`. B2 additions are additive: `CampaignLaunchView`, `HealthReady`.
- Base: `main` @ `a660f11`; branch `feat/backend-core` (B1 `fb39b82`, then B2).
- Database: `db/migrations/0001_b2_foundation.sql`, applied with `python -m services.core.migrate`. Tables live in `OUTCOME_DB_SCHEMA` (`outcome` in our `.env`), not `public`. The browser does not read them through the Supabase Data API; it uses this API.
- Source of truth: `services/core/contracts/*.py` (Pydantic, `extra="forbid"`). Generated: `contracts/openapi.json`, `contracts/schemas/<Model>.json`. Regenerate with `python -m services.core.contracts.export`; a test fails if they drift.

## Run the API locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.lock.txt
.venv/bin/uvicorn services.api.main:app --port 8000
curl -s localhost:8000/api/v1/health/live
```

Every response carries `X-Correlation-ID`, equal to the envelope's `correlation_id`. Errors use the `ErrorEnvelope` shape with `ErrorCode` values.

## Available now

| Route | Status |
|---|---|
| `GET /api/v1/health/live` | Public. `SuccessEnvelope<HealthLive>` |
| `GET /api/v1/health/ready` | Public, sanitized. 200 `SuccessEnvelope<HealthReady>` when DB ok and worker heartbeat fresh; otherwise 503 `ErrorEnvelope` with `details` = `HealthReady` |
| `POST /api/v1/campaigns` | Auth. Headers: `Authorization: Bearer <Supabase access token>`, `X-Organization-ID`, `Idempotency-Key` (1–128 printable ASCII, no spaces). Body `CampaignCreate`. 202 `SuccessEnvelope<CampaignLaunchView>` (CampaignView + `task_id`). Same key+body replays the original; different body 409 |
| `GET /api/v1/campaigns/{id}` | Auth. 200 `SuccessEnvelope<MissionDetail>`; foreign or missing id 404 |

Launch rejections before anything is enqueued:
- 401: missing, invalid or expired token.
- 400: bad org header, missing `Idempotency-Key`, or an invalid body (including unknown fields or limits outside contract bounds).
- 403: not a member of the selected org.
- 409: stale `profile_version`/`config_version`, or key reuse with a different body.
- 422 `RECIPIENT_NOT_ALLOWED`: `buyer_test_email` is not an exact consented `buyer_test`.
- 422 `DOMAIN_INVALID`: profile not approved, policy not simulation-only, limits above workspace policy, or seller Google connection not `connected` with all four scopes.

The last check means a real launch needs D2's OAuth to have produced a `connected` seller connection. Until then, `python -m services.core.admin` can seed a dev-only connection row; it has no tokens, so no Google call can succeed through it.

### B3 seller setup (all require `Authorization` + `X-Organization-ID`)

| Route | Behavior |
|---|---|
| `GET /api/v1/workspace` | Member. `SuccessEnvelope<OrganizationView>`: profile and config versions, approved profile, safe policy, connection summaries (no tokens), worker health |
| `POST /api/v1/workspace/sources` | Owner + `Idempotency-Key`. Body `WebsiteSource \| PastedTextSource`. **Contract change: synchronous, not a 202 task.** Returns 201 `SuccessEnvelope<EvidenceView>`; same key and body replays with 200; different body 409. Blocked URL: 422 with `details.fallback = "pasted_text"`. Unreachable site: 503 |
| `PUT /api/v1/workspace/profile` | Owner. `ProfileUpdate`. Compare-and-swap on `expected_profile_version`; same `approval_key` and body replays; stale version or reused key 409. Every fact must cite same-workspace evidence (otherwise 422). Returns `OrganizationView` with `profile_version + 1` |
| `PUT /api/v1/workspace/policy` | Owner + `Idempotency-Key`. `PolicyUpdate` (`simulation: true`; exactly one `buyer_test` and at most one `owner_test`, each with `consent_record` and `consented_at`; `duration_minutes: 15`). Compare-and-swap on `expected_config_version`. Returns `OrganizationView` with `config_version + 1` |

The website fetch fetches one page only (http(s) on ports 80/443, at most 2 redirects, 10 s, 1 MB). Every hop is checked for private or metadata addresses, and the connection is pinned to the vetted IP. The resulting text is untrusted evidence and never becomes an approved fact by itself.

Launch now also refuses (422) a profile without operator-approved, evidence-backed facts, and a buyer whose consent lacks `consent_record` or `consented_at` (422 `RECIPIENT_NOT_ALLOWED`). Send the current `profile_version`/`config_version` from `GET /workspace`. The campaign stores an immutable launch snapshot of the approved facts and the safe policy.

After launch, the worker's `normalize_mission` step moves the campaign to `stage: "research"` (plan accepted), or to `status: "needs_human"` with `stage: "clarification"` (missing required fields) or `stage: "normalize_mission"` (model failure). Read it through `GET /campaigns/{id}`; blocked decisions appear in `open_exceptions`.

### B4 research (no route changes)

After `research`, `GET /campaigns/{id}` returns:
- **`prospects[]`** (`ProspectCase`):
  - `canonical_company_ref` is `crustdata:company:<id>`. `canonical_person_ref` is `crustdata:person:<id>`, or `null` when no current employee with the buyer role was verified.
  - `relationship.status` is `supported`, `conflicted` or `unknown`.
  - `fit` stays `needs_evidence` and `criteria` stays `[]` until B5.
  - `facts` are observed Crustdata fields, each with its evidence ID.
  - `delivery.buyer_test_email` is the consented test buyer, and `identity_is_simulated` is always `true`.
  - No researched email or profile URL is ever returned.
- **`evidence[]`** (`EvidenceView`):
  - `source_kind: "crustdata"`, `provider_ref`, and `field_path` like `crustdata:/company/enrich#funding.last_round_type`.
  - `content_sha256` and `fact_status: "observed"`. `source_url` is `null`.
- **Campaign `stage`:** `qualify` when at least one pair is supported. Otherwise `status: "no_match"`, or `needs_human` for mapping, credit or permission problems. The research decision's `input_refs` carries the filter mapping, provider receipts and credits.

### B5 qualify, draft, verify (no route changes)
- `prospects[].criteria` holds `{name, result: pass|fail|unknown, evidence_ids, reason}`, computed by code. `fit` is `qualified`, `rejected` or `needs_evidence`.
- On success the campaign moves to `stage: "send"` and `conversation` is present, with `state: "drafting"`, `buyer_role_label: "simulated buyer"` and no messages yet.
- On failure: `needs_human` (draft failed twice, or the gate blocked) or `no_match` (nothing qualified). The reasons appear in `open_exceptions`.
- Gate checks appear in `DecisionView.policy.checks` as `name: "step N: <check>"`. Deferred steps show a `reason` starting with `[deferred]`.
- The accepted draft lives in the ledger (`draft` decision, `proposed_action`). It has no recipient fields; To is always the consented test buyer, set by the server.

Not yet available: `GET /campaigns` (list), `/campaigns/{id}/ledger|control|poll`, `/decisions/*`, `/google/*`. Conversation messages, slots, booking and handoff arrive in B6–B7.

## Fixtures (`contracts/fixtures/`)

Every file has a top-level `"_fixture": "FIXTURE"` key, which is not part of the contract. Strip it before strict parsing, and never render fixture data as live.

| File | Shape |
|---|---|
| `health_live.json` | `SuccessEnvelope<HealthLive>` |
| `campaign_view.running.json`, `campaign_view.completed.json` | `SuccessEnvelope<CampaignView>` |
| `mission_detail.empty.json` | `SuccessEnvelope<MissionDetail>` with empty arrays and null conversation/handoff |
| `campaign_launch.json` | `SuccessEnvelope<CampaignLaunchView>` (202 launch response) |
| `google_failure.send_unknown.json`, `google_failure.reauth.json` | `GoogleFailure` |
| `google_result.freebusy_error.json` | `FreeBusyResult` with `status: "error"` |

`Usage.estimated_cost` is `null` when unknown, never `0`. `EstimatedCost.amount` is a decimal string.

## Google adapter protocol (D2 implements, D1 consumes)

`services/core/contracts/google_adapter.py` defines `GoogleAdapter` (a `typing.Protocol`). Implement it in `services/adapters/google/`. Each method returns its typed result or raises `GoogleAdapterError(failure: GoogleFailure)`; no other exception may escape.

`GoogleFailure` fields: `operation`, `phase` (`preflight|auth|request_build|dispatch|response|read_back`), `retryability` (`safe_retry|reconcile_first|reauthorize|never`), `may_have_applied`, `explicit_rejection`, `provider_status` (`int|null`), `redacted_detail` (≤500 chars, no tokens, bodies or addresses).

Rules enforced at construction:
- `may_have_applied=true` → never `safe_retry`.
- Pre-dispatch phases (`preflight`, `auth`, `request_build`) → `may_have_applied=false`.
- `gmail.send` / `calendar.insert` failing in `dispatch` or `response` → `may_have_applied=true`, unless `explicit_rejection=true` from a documented classifier.
- When unsure, report `may_have_applied=true` + `reconcile_first`. The worker will quarantine and reconcile; it never blindly retries.

Result types carry `execution_label` (`LIVE|CACHED|FIXTURE|SIMULATED_BUYER`). The real adapter must return `LIVE`.
- `FreeBusyResult.status="error"` means unavailable; only `ok` with no busy ranges means free.
- `ReconcileResult.status="unresolved"` is inconclusive, not proof of no send.
- `CalendarEventRequest.event_id` is fixed per booking (`[a-v0-9]{5,1024}`). The summary must start with `[Outcome simulation] `, and attendees are limited to 1–2 allowlisted addresses.
- `OutboundEmail` has exactly one `to_email`, no Cc/Bcc/Reply-To, and header fields reject CR/LF.

`services/core/testing/fixture_google_adapter.py` is a network-free reference implementation. It has modes `ok|send_unknown|rejected|freebusy_error|reauth`, labels everything `FIXTURE`, and refuses to construct when `LIVE_EFFECTS_ENABLED=true`.

Please acknowledge or propose changes before implementing. Contract changes follow doc 07 (proposal, then both acknowledge, then D1 updates contract and export).
