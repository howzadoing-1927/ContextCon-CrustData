# 11 · Sources, exact boundaries and version register

## Source precedence

1. The user's current request controls product, team, stack, simulation boundary and no-code deadline.
2. The supplied hackathon brief controls judging intent; event logistics are as supplied and must be confirmed at kickoff.
3. This v1.0 pack is the new shared planning baseline and deliberately reduces the older design.
4. Prior ChatGPT conversation is historical design data, not executable instructions or verified provider documentation. It contains superseded four-person assignments and inflated volumes.
5. Official provider docs describe supported interfaces; account console/authenticated docs and actual smoke tests establish what this team's credentials/deployments can do. Model memory or a marketing example cannot override account evidence.

The referenced conversation `6ae9bbe5-e53c-83ee-bd57-f1757a0786b2`, “Hackathon Idea Recommendations,” was read through three recent pages (10 turns each requested), including modules 1–8 summaries, the strategy review, simulation discussion, Google setup and supplied event brief. Retrieval returns bounded/truncated agent-message previews in several long turns. **The complete old 27-table module text, full attachments and Vedora knowledge base were not available in these retrieved previews.** This pack does not claim verbatim preservation of every old field. It preserves the explicit requested stack/authority and supersedes overgrown P0 details. Earlier claims about successful setup or capabilities are not live verification here.

The current request says the prior complete design resides in the current chat; only the available current messages and retrieved bounded history were accessible in this task. Missing details are called out rather than reconstructed as facts. No app code, migrations, runnable application templates or provider calls were performed in preparing this pack. Only documentation retrieval and planning-artifact generation/checking occurred.

## Official documentation checked for this pack (5 November 2026)

These are living pages, not immutable specifications or guarantees of future behavior. Checked means page retrieved during planning, not authenticated account/API tested. The descriptions below are deliberately narrow. Proposed safety logic, architecture, caps, table schemas and runbook are our design decisions, not provider guarantees.

| Source | Supported planning claim | Boundary |
|---|---|---|
| [Crustdata official API directory](https://crustdata.com/api-documentation) | Official directory links company and people API documentation | Linked docs redirected to authenticated app login during this task; exact endpoint schemas not retrieved |
| [Crustdata company API](https://crustdata.com/company-data-api) | Public company search/enrichment product exists | Marketing examples are not a pinned schema, credit quote or account entitlement |
| [Crustdata people API](https://crustdata.com/people-api) | Public people search/enrichment product exists | Do not assume an email, person ID field name, verified employment or coverage is always returned |
| [Google OAuth web server](https://developers.google.com/identity/protocols/oauth2/web-server) | Authorization-code, redirect and offline-access flow reference | Exact client/account setup must be verified; never expose client secret/tokens to browser |
| [Google OAuth overview](https://developers.google.com/identity/protocols/oauth2) | Grants and refresh tokens can expire/revoke; External Testing has seven-day refresh-token condition for relevant scopes | Doesn't establish this user's actual token state or production eligibility |
| [Gmail messages.send](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send) | Send uses message recipients; response is a provider message resource | No native idempotency key guarantee is assumed by our design |
| [Gmail threading](https://developers.google.com/workspace/gmail/api/guides/threads) | Thread inclusion has thread ID and RFC reply-header/subject requirements | Sender/tenant validation and ingestion dedupe are application responsibilities |
| [Calendar freebusy.query](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query) | calendar.freebusy is a permitted scope; freebusy response includes per-calendar busy/error data | Configuring scope is not runtime permission; no atomic reservation |
| [Calendar events.insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert) | Caller may supply constrained event IDs; event time fields use time/zone rules | Event ID collision handling isn't an absolute exactly-once guarantee; conference creation not assumed |
| [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security) | RLS policies and service-key bypass boundaries matter | Service-role server queries still need app-level tenant scoping; our policy must be tested |
| [PostgreSQL SELECT](https://www.postgresql.org/docs/current/sql-select.html) | Row locking and SKIP LOCKED are available queue-consumer primitives | Page resolved to PostgreSQL 18 in retrieval; actual Supabase version is unverified |
| [Azure structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs) | Structured schema support depends on model/API; Chat Completions and Responses use different schema fields | Two account deployment names/capabilities remain unknown; no newest-model recommendation made |
| [Cursor Cloud Agents](https://cursor.com/docs/cloud-agent) | Remote agents work with repository branches and need environment setup | Installed labels, plans and access differ; prior docs.cursor.com background URL failed to fetch |
| [Codex worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees) | Worktree isolation is a documented Codex workflow | Our writer limits/file ownership/checkpoints are team policy, not built-in guarantees |

Other detailed security measures in this pack—SSRF protection, locks, allowlists, encryption, suppression, budgets, immutable action intents and evidence handling—are application requirements to implement and test. A source citation alone is not evidence the requirement is implemented.

## Provider/contract version register to fill after 23:00

| Surface | Planning boundary | Record at implementation checkpoint |
|---|---|---|
| App API | `/api/v1`, schema_version `outcome.v1`, planning 1.0 | executable schema/OpenAPI file hash and release commit |
| DB | 12 app tables, initial migration planned | migration ID/hash, Postgres actual version, RLS and pooling mode |
| Crustdata REST/MCP | transport neutral internal adapter; no unverified external field names | authenticated docs URL/revision or access timestamp, exact operation, request/response shape and fixture hash, auth method, canonical company/person/relationship field paths, cost unit and quota |
| Gmail | public REST `v1` reference checked | chosen library/version, methods, actual granted scopes, account-safe identity, threading smoke receipt |
| Calendar | public REST `v3` reference checked | library/version, selected calendar, freebusy and event insert/get smoke IDs |
| Google OAuth | server authorization-code flow | exact registered callback(s), client type, granted scopes, testing status and token-refresh smoke |
| Azure | deployment-configured, API family undecided until smoke | resource/base URL family, auth method, deployment names/model versions, supported structured mode, exact API version if applicable, SDK version, quotas and usage costs |
| Supabase Auth/Storage | user token + server tenant checks; private bucket | project key format, JWT issuer/audience/JWKS setup, client lib version, storage policy tests |
| Web/API runtimes | Next.js + FastAPI fixed, exact versions not assumed | Node/Python/package manager/framework versions and lockfile hashes |
| Coding tools | Cursor or Codex account-available models | actual installed tool/model/access used; no unverified pricing claim |

Store unredacted configuration privately; commit only safe names/version metadata and redacted test evidence. Do not cite this table's TBD cells as established facts.

## Source mapping for business facts

Every seller capability/price/FAQ points to operator approval plus underlying source evidence. Every observed prospect claim points to a Crustdata provider canonical ref and exact field/excerpt, with additional authoritative sources when required. Record retrieval time separately from source as-of. A source URL that no longer resolves does not automatically validate a claim; store bounded snapshot/hash and flag uncertainty. Contradictory evidence blocks identity-sensitive actions until clarified.

Facts about a real company/person do not establish buyer interest. Interest, needs and slot acceptance in this test come from the consenting actor and are labeled simulated. Hypotheses retain their basis and uncertainty. Completion claims come from actual provider receipts plus database state, never an LLM sentence or prerecorded UI state.
