# Crustdata source / field / version mapping

- API: `https://api.crustdata.com`, header `x-api-version: 2025-11-01`, `authorization: Bearer $CRUSTDATA_API_KEY`, `content-type: application/json`.
- Verified 2026-11-06 against the live docs (`docs.crustdata.com/openapi-specs/2025-11-01/*`, the company and person search references, company identify, enrich and autocomplete, rate limits, pricing, best practices). Also checked against this account's `GET /account/endpoints` and live probes (about 8 credits, recorded in D1-B4).
- Re-verify on any version bump, and before trusting a new field.

## Endpoints used

| Endpoint | Account status | Our RPM pacing | Cost (this account) | Used for |
|---|---|---|---|---|
| `POST /company/search/autocomplete` | enabled | 300 | free | Exact filter values for the plan's geography, industry and funding |
| `POST /company/search` | enabled | 30 | 0.03 per result, plus premium groups (+0.1 each for filtering on `taxonomy` or `funding`); observed about 0.33 per result | Discovery, up to 10 results |
| `POST /person/search` | enabled | 30 | 0.03 per result + 0.1 for filtering `experience` + 0.1 for returning it, so 0.23 per result; 0 for no results | Person at company, up to 3 results |
| `POST /company/enrich` | enabled | 15 | 2 per record (no technographics or posts requested) | Identity and firmographics for up to 3 matched companies |
| `/person/identify`, `/person/contact/enrich` | **disabled** | — | — | Never used: researched contact data is out of scope |

Errors are `{"error":{"type","message","metadata"}}`. 402 (`insufficient_credits`) and 400/401/403/404 are terminal. 429 waits `x-ratelimit-reset` plus jitter, and 5xx backs off, up to 3 attempts. Every response carries `x-ratelimit-limit`, `x-ratelimit-remaining`, `x-ratelimit-reset`, `x-credits-used` and `x-request-id`; we store the last two per call.

## Canonical identity

| Our ref | Source field | Notes |
|---|---|---|
| `crustdata:company:<id>` | `crustdata_company_id` (int) | Always returned by company search and enrich. Converted back to int only inside the adapter |
| `crustdata:person:<id>` | `crustdata_person_id` (int) | Always returned by person search |

## Plan → company search filters (code-mapped; values only from autocomplete)

| Plan input | Filter field | Autocomplete field | Rule |
|---|---|---|---|
| geography (country) | `locations.country` `in` | `locations.country` | Exact case-insensitive suggestion |
| geography (city) | `locations.city` `in` | `city` (`locations.city` is **not** autocompletable: 400) | Exact suggestion |
| industries | `basic_info.industries` `in` (filter-only; returned as `taxonomy.professional_network_industry`) | `basic_info.industries` | Exact suggestion |
| industry not in the label set (for example "fintech") | `taxonomy.professional_network_specialities` `in` | same | Up to 3 suggestions containing the term; reported as **weak_matches** (self-tagged) |
| must-have funding rule (`funding_stage`, …) | `funding.last_round_type` `in` | same | Snake-case slugs, e.g. `series_a`; exact. A `range` with two round endpoints expands along `pre_seed, seed, series_a … series_j` (Series B–D gives b, c, d) |
| must-have headcount range | `headcount.total` `=>` / `=<` | — | Numeric bounds only |
| exclusions, assumptions, non-must-have or unknown rule fields | — | — | Reported **unmapped**; left for qualification (B5) |

`taxonomy.categories` is deliberately **not** used. A live probe showed noisy tag lists: a food company matched `FinTech`.

## Person ↔ company relationship

| Purpose | Path | Notes |
|---|---|---|
| Filter: current employer | `experience.employment_details.current.company_id` `=` id | Filter path |
| Response: current employer | `experience.employment_details.current[].crustdata_company_id` | Response twin. Filter paths in `fields` return 400 |
| Filter: title | `experience.employment_details.current.title` `(.)` words | All words, any order. Fixed alias variants (VP ↔ Vice President, CRO, CSO), OR'd |
| Response: title, primary role | `current[].title`, `current[].is_default` | Exactly one current role is the default |
| Empty-result explanation | `remarks[]` (`code`, `path`, `matches_without`) via `explain: true` | Stored on the decision |

`supported` requires a returned current role whose `crustdata_company_id` equals the company and whose title contains every role term. Otherwise the result is `conflicted` (profiles came back, but not matching) or `unknown` (no profiles), and the prospect is `needs_evidence`. Fields requested from person search: `crustdata_person_id`, `basic_profile.name`, `basic_profile.current_title`, `experience.employment_details.current`. We never request `contact`, `social_handles` or emails. From each current role we keep only `crustdata_company_id`, `name`, `title`, `is_default`, `seniority_level`, `function_category` and `start_date`.

## Evidence `field_path` convention

`crustdata:<endpoint>#<response path>`. For example:
- `crustdata:/company/search#basic_info.name`
- `crustdata:/company/enrich#funding.last_round_type`
- `crustdata:/person/search#experience.employment_details.current[crustdata_company_id=<id>].title`

Each row's `content_sha256` is the SHA-256 of the canonical provider record it came from. For people, that is only the kept role subset. `provider_ref` is the canonical ref, and `metadata_json` has the endpoint, API version, request ID, request/response hashes and credits. `source_url` is null; we never invent one. `source_as_of` is null, because no per-field timestamp is requested.
