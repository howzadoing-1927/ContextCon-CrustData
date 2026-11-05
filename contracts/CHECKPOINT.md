# D1 → D2 contract checkpoint (B1 + B2)

- Contract: `outcome.v1`, planning baseline 1.0, prefix `/api/v1`. B2 additions are additive: `CampaignLaunchView`, `HealthReady`.
- Base: `main` @ `a660f11`; branch `feat/backend-core` (B1 `fb39b82`, then B2).
- Database: `db/migrations/0001_b2_foundation.sql`.
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

Not yet available: `GET /campaigns` (list), `/campaigns/{id}/ledger|control|poll`, `/workspace*`, `/decisions/*`, `/google/*`. `MissionDetail` collections stay empty until B4–B7 write them.

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
