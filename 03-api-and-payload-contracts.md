# 03 · API and JSON payload contracts

Contract `outcome.v1`, planning baseline 1.0. These are **application-owned interfaces**, not claims about external provider schemas. D1 owns implementation and executable JSON Schema/OpenAPI generation after 23:00. D2 implements against this document until that generated contract exists. Do not copy illustrative provider fields into real API calls without checking account docs.

## Common type and validation rules

UUID = canonical UUID string; Instant = RFC3339 string with explicit offset, normalized UTC on persistence; Zone = valid IANA zone; Email = one parsed mailbox, no CR/LF or display-list syntax; Reference = nonempty provider opaque string (never cast to an integer); Money/usage = nonnegative decimal in explicitly named units. Missing field and null are different: null only where specified. Reject unknown request fields and invalid enum values. Arrays deduplicated, ordered where meaningful. Request body max 64 KB; text request 1–4000 characters; pasted facts 20 KB; source fetch 1 MB max after decompression. Provider snapshots have separate bounded storage limits. Escape all rendered text; never inject external HTML.

All secured routes use `Authorization: Bearer <Supabase access token>` and `X-Organization-ID: <UUID>`. Membership is checked server-side. Mutation routes require `Idempotency-Key` (1–128 safe ASCII chars) except OAuth callback. Same org+route+key+canonical request hash returns original result; different hash is 409. Campaign create stores request key/hash; command routes use deduped task keys; evidence approval uses profile version compare-and-swap with deterministic key. API doesn't promise generic idempotency without a persisted key in the relevant table.

Success envelopes: `{ "schema_version":"outcome.v1", "data":<typed object>, "correlation_id":"<UUID>" }`. List data: `{ "items":[], "next_cursor":null }`. Opaque cursor encodes tenant-bound last created_at/id; default limit 25, max 100. Never return tokens or private raw provider payloads in a generic serializer.

Error envelope:

```json
{"schema_version":"outcome.v1","error":{"code":"RECIPIENT_NOT_ALLOWED","message":"Only the consented test buyer can receive this message.","retryable":false,"details":{"field":"buyer_test_email"}},"correlation_id":"<UUID>"}
```

HTTP: 400 malformed, 401 invalid auth, 403 insufficient membership/role, 404 nonexistent or foreign object, 409 stale version/idempotency conflict/state conflict, 422 valid JSON but invalid domain data, 429 local cap, 503 provider/dependency unavailable. Do not expose raw provider errors or secrets. Accepted work is 202, not success of the eventual job. Domain exceptions are visible in mission state even when the original request returned 202.

## P0 endpoint inventory

| Method and route (prefix /api/v1) | Input | Response and owner |
|---|---|---|
| GET /health/live | none, public | 200 process alive; no secrets; D1 |
| GET /health/ready | protected or sanitized public | DB reachable, worker heartbeat freshness summary; D1 |
| GET /workspace | selected org | OrganizationView with approved facts, safe policy, connection summary, worker health; D1 |
| PUT /workspace/profile | ProfileUpdate, owner role | OrganizationView or 409 on profile version; D1 |
| POST /workspace/sources | SourceInput | 202 task reference; fetch/normalize into evidence then propose facts, never auto-approve; D1 |
| PUT /workspace/policy | PolicyUpdate, owner role | config_version increment; fails closed on incomplete consent; D1 |
| POST /google/connect | purpose seller only in P0; fixed return path enum | authorization_url, expires_at; D2 logic wired by D1 |
| GET /google/callback | Google code/state/error query; no bearer header | Verify single-use state; exchange/store server-side; redirect to fixed web setup path; D2 |
| GET /google/status | org | Safe account/scopes/calendar/status, no token; D2 |
| POST /campaigns | CampaignCreate | 202 CampaignView and task_id; D1 |
| GET /campaigns | cursor/limit | List CampaignView; D1 |
| GET /campaigns/{id} | org+id | MissionDetail; D1 |
| GET /campaigns/{id}/ledger | cursor/limit | List DecisionView, chronological; D1 |
| POST /campaigns/{id}/control | pause/resume/stop, expected_version integer | 202 current status/task; owner only; D1 |
| POST /campaigns/{id}/poll | none | 202 deduped immediate poll request; does not inject a reply; D1 |
| POST /decisions/{id}/resolve | allowed typed resolution + expected conversation version | 202 resolution and next task; owner only; D1 |

No public `/send`, `/insert-event`, arbitrary tool execution, fixture injection or “mark complete” endpoint. No browser endpoint accepts Google tokens. No webhook/PubSub needed. Browser poll endpoint only asks worker to check Gmail; buyer emails must arrive through Gmail. Routes beyond this inventory are stretch and require an agreed contract update.

## Seller setup schemas

`SourceInput`: exactly one of `{kind:"website",url:HTTPS_URL}` or `{kind:"pasted_text",title:string,text:string}`. Website must be public HTTP(S); default HTTPS. Server rejects credentials in URL, localhost, private/link-local/metadata IPs, unsafe ports, non-HTTP redirects, DNS rebinding and redirects to blocked ranges. Max two redirects, 10-second fetch, one page P0; strip scripts and treat resulting text as untrusted. If SSRF-safe fetching cannot be completed, allow only operator pasted text rather than unsafe arbitrary fetch. Evidence retains source URL and retrieval timestamp.

`ProfileUpdate`: `{expected_profile_version:integer, approval_key:string, name:string, website_url:HTTPS_URL, timezone:Zone, approved_facts:ApprovedFact[], faq:FAQ[], forbidden_promises:string[]}`. ApprovedFact = `{id:string, text:string, evidence_ids:UUID[], authority:"operator_approved", approved:true}`. FAQ = `{question:string, answer:string, fact_ids:string[]}`. Require references to existing same-org evidence; operator assertions become explicit operator-source evidence first. Do not silently turn inferred website text into approved authority. Profile change creates new version; running campaigns retain approved snapshot or pause for explicit revalidation.

`PolicyUpdate`: `{expected_config_version:integer, simulation:true, consented_recipients:[{email:Email, role:"buyer_test"|"owner_test", consent_record:string, consented_at:Instant}], selected_calendar_id:string, working_hours:{timezone:Zone, weekdays:[1,2,3,4,5], start:"09:00",end:"17:00"}, duration_minutes:15, limits:Limits}`. Consent record is a short operator-attested reference, not a legal-proof claim. P0 permits one buyer test email and optionally one owner test email. Email normalization trims and case-normalizes domain; do not strip dots or plus-tags or assume provider alias equivalence. Exact allowlist matches only. A buyer mapping cannot be edited by a model.

`Limits`: `{max_discovered:10,max_enriched:3,max_conversations:1,max_outbound_messages:6,max_model_calls:20,max_research_calls:10,max_runtime_seconds:600,max_reply_turns:4,no_reply_followups:0}`. Limits are our defaults, not provider quotas. Require positive bounded integers except allowed zero followups. Owner may lower caps; increases need explicit config change and quota review. Recipient, scopes and budgets are checked again at execution, not just launch.

## Campaign schemas

Example request, with placeholder addresses intentionally non-deliverable:

```json
{
  "request_text":"Find a relevant B2B company and its sales leader in the approved market, explain the fit, and book a 15-minute demo. Do not assume they have a problem we cannot verify.",
  "mode":"simulation",
  "buyer_test_email":"consenting-buyer@example.invalid",
  "profile_version":1,
  "config_version":1,
  "limits":{"max_discovered":10,"max_enriched":3,"max_conversations":1,"max_outbound_messages":6,"max_model_calls":20,"max_research_calls":10,"max_runtime_seconds":600,"max_reply_turns":4,"no_reply_followups":0}
}
```

The real inbox is selected by the operator at setup; replace example.invalid only with the consented test destination. Server rejects mode other than simulation, unknown consent, stale profile/config, missing seller Google scopes and unapproved seller facts before enqueueing external work. Mandatory ICP facts unknown after normalization trigger clarification or no_match, never softened silently.

`CampaignView`: `{id:UUID, request_text:string, mode:"simulation", status:CampaignState, version:integer, stage:string, profile_version:integer, config_version:integer, usage:Usage, last_decision_id:UUID|null, created_at:Instant, updated_at:Instant}`. Usage has model_calls, research_calls, outbound_attempts, calendar_attempts, tokens_in, tokens_out, optional estimated_cost with currency and pricing_source; unknown cost is null, never zero.

`NormalizedPlan`: `{objective:"book_demo", geography:string[], industries:string[], company_rules:[{field:string,operator:"equals"|"contains"|"range",value:scalar_or_array,must_have:boolean}], buyer_roles:string[], exclusions:string[], missing_required_fields:string[], assumptions:[{text:string,status:"hypothesis"}], research_queries:[{intent:string,limit:integer}], stop_conditions:string[]}`. Query intent is internal; adapter maps it to verified provider filters. Refuse arbitrary model-supplied SQL, REST URLs or Crustdata filter names.

`MissionDetail`: CampaignView plus `{prospects:ProspectCase[],conversation:ConversationView|null,open_exceptions:DecisionView[],evidence:EvidenceView[],handoff:Handoff|null}`. Frontend must tolerate empty arrays, pending refs and explicit nulls.

`ProspectCase`: `{id:UUID,canonical_company_ref:string,canonical_person_ref:string|null,company:{name:string,domain:string|null},person:{name:string,title:string|null}|null,relationship:{status:"supported"|"unknown"|"conflicted",evidence_ids:UUID[]},criteria:[{name:string,result:"pass"|"fail"|"unknown",evidence_ids:UUID[],reason:string}],fit:"qualified"|"rejected"|"needs_evidence",facts:[{text:string,evidence_ids:UUID[]}],hypotheses:[{text:string,basis_evidence_ids:UUID[]}],delivery:{mode:"simulation",buyer_test_email:Email,identity_is_simulated:true}}`. Real researched emails, if returned by provider, are not part of delivery mapping or default browser payload.

`EvidenceView`: `{id:UUID,source_kind:"crustdata"|"seller_website"|"operator"|"google_message"|"google_calendar"|"policy",source_url:string|null,provider_ref:string|null,field_path:string|null,excerpt:string,retrieved_at:Instant,source_as_of:Instant|null,content_sha256:string,fact_status:string}`. Missing upstream source date remains null. API retrieval timestamp is not proof the underlying fact was verified today. Provider citation can be provider ID+field path+response hash when no public URL exists.

## Worker/model handoff contracts

`TaskPayload` common: `{schema_version:"outcome.v1",campaign_id:UUID,conversation_id:UUID|null,expected_conversation_version:integer|null,trigger_message_id:UUID|null,decision_id:UUID|null,input_ref_ids:UUID[]}`. Tenant comes from the task row, not model output. Each task kind accepts only its needed subset and validates references. Provider calls are not serialized as arbitrary executable instructions.

`ReplyInterpretation`: `{intent:"interested"|"question"|"objection"|"decline"|"opt_out"|"schedule_preference"|"accept_slot"|"ambiguous"|"out_of_office"|"request_human",quote:string,message_id:UUID,confidence:number,accepted_slot_id:string|null,requested_time:{start:Instant|null,timezone:Zone|null,raw_text:string}|null,needs_clarification:boolean,reason:string,evidence_ids:UUID[]}`. Confidence 0–1 is advisory, not authority. accept_slot requires exact offered slot or unambiguous fully resolved time with explicit acceptance.

`DraftProposal`: `{purpose:"initial"|"answer"|"clarify"|"offer_slots"|"confirm",subject:string,body_text:string,claims:[{text:string,start:integer,end:integer,kind:"seller_fact"|"prospect_fact"|"hypothesis"|"scheduling_fact",evidence_ids:UUID[],approved_fact_ids:string[]}],used_slot_ids:string[],reason:string,evidence_ids:UUID[]}`. Character offsets are Unicode code points, half-open, relative to body_text; validate exact match. Verifier also checks uncovered claims because the drafter may omit a claim from this list. There is deliberately no recipient/account/tool URL in model output.

`VerificationResult`: `{verdict:"pass"|"revise"|"block",unsupported_claims:[{text:string,reason:string}],contradictions:string[],unauthorized_promises:string[],unanswered_questions:string[],injection_flags:string[],reason:string,evidence_ids:UUID[]}`. Even pass cannot bypass deterministic policy.

`DecisionView`: `{id:UUID,kind:string,status:string,reason:string,evidence_ids:UUID[],input_refs:object,model:{deployment:string,model_version:string|null,prompt_version:string,usage:object}|null,policy:{pass:boolean,checks:[{name:string,pass:boolean,reason:string}]},proposed_action:object|null,actual_action:{action_id:UUID,state:string,provider_ref:string|null}|null,resolution:object|null,created_at:Instant}`. Source-free decisions must cite policy/request/state references rather than manufacture external evidence.

`ConversationView`: `{id:UUID,state:ConversationState,version:integer,buyer_role_label:"simulated buyer",buyer_test_email:Email,provider_thread_id:string|null,messages:MessageView[],offered_slots:Slot[],booking:BookingReceipt|null}`. MessageView includes ID, direction, safe subject/body, sent/received time, provider message ID, status. `Slot`: `{id:string,start:Instant,end:Instant,timezone:Zone,freebusy_checked_at:Instant}`. Slot is offer, not reservation. `BookingReceipt`: `{action_id:UUID,event_id:string,calendar_id:string,start:Instant,end:Instant,timezone:Zone,html_link:string|null,verified_at:Instant,attendee_acceptance:"not_verified",mode:"simulation"}`.

`Handoff`: `{version:1,status:"complete",mode:"simulation",campaign_id:UUID,prospect_id:UUID,conversation_id:UUID,booking:BookingReceipt,fit_summary:string,fit_evidence_ids:UUID[],buyer_stated_needs:[{text:string,message_id:UUID}],hypotheses:string[],open_questions:string[],next_steps:string[],owner_email:Email|null,notification_status:"not_requested"|"pending"|"sent"|"failed"}`. Don't attribute simulated needs to the real researched person. CRM JSON stores stage, terminal_reason, booking_action_id, handoff_version and last_decision_id.

`ResolveInput`: `{expected_conversation_version:integer|null,resolution_type:"supply_fact"|"clarify_time"|"confirm_identity"|"reauthorize_complete"|"stop",note:string,evidence_ids:UUID[],value:object}`. Never allow a resolution to override recipient allowlist or assert an unknown send failed without evidence. Reauthorization must be proved by connection status, not a user checkbox. Send uncertainty remains quarantined until receipt or explicit documented operator investigation; ordinary resolution cannot cause resend.

## Application-owned provider adapters

| Adapter method | Input | Result | Must not assume |
|---|---|---|---|
| research.search_companies | normalized query intent, limit | normalized company refs + raw provenance + pagination metadata | Exact endpoint/filter names or cost |
| research.find_people | company ref, role intent, limit | person refs, relationship evidence, missing fields | Verified email or purchasing authority |
| research.enrich_identity | canonical ref | bounded observed fields/evidence | Always available fields or freshness |
| google.start_oauth / complete_oauth | tenant/user-bound pending connection | URL / safe connection | Current console settings equal granted token scopes |
| gmail.send | authorized account, immutable MIME, action key | sent receipt / known rejection / unknown | Native idempotency key support |
| gmail.poll_thread | authorized account, Gmail thread ID | normalized messages with provider IDs | Subject alone proves membership |
| gmail.reconcile_send | persisted Message-ID/account/thread | positive receipt / unresolved | Immediate negative search proves no send |
| calendar.freebusy | selected calendar, interval | busy ranges or explicit calendar error | Empty/missing response means free |
| calendar.insert / get | deterministic event ID, fingerprint, allowed attendee | verified event receipt / unknown/error | Atomic reserve or automatic conference link |

D2 implements Google adapter contract and a typed failure class with `phase`, `retryability`, `may_have_applied`, `provider_status`, redacted detail. D1 owns workflow decisions based on it. Both developers use the same contract examples; stubs are labeled contract fixtures and never displayed as live execution.

## JSON Schema reference (planning text, not generated application code)

The following Draft 2020-12 schema defines the critical inbound and model-output shapes. It is documentation to implement after 23:00, not a runnable app artifact. `$defs` names are selectable validation roots; the default root is CampaignCreate. Enforce `format` assertions in the chosen validator. UUID/evidence existence, tenant membership, supported timezone, exact quoted substring, policy authority and evidence truth need the additional semantic checks above. Azure strict-output mode may support a subset of JSON Schema: derive an API-compatible schema after verifying the deployment; do not send this entire document unmodified to a provider.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:outcome:planning:1.0:critical-payloads",
  "$ref": "#/$defs/CampaignCreate",
  "$defs": {
    "Limits": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "max_discovered",
        "max_enriched",
        "max_conversations",
        "max_outbound_messages",
        "max_model_calls",
        "max_research_calls",
        "max_runtime_seconds",
        "max_reply_turns",
        "no_reply_followups"
      ],
      "properties": {
        "max_discovered": {
          "type": "integer",
          "minimum": 1,
          "maximum": 10
        },
        "max_enriched": {
          "type": "integer",
          "minimum": 1,
          "maximum": 3
        },
        "max_conversations": {
          "type": "integer",
          "minimum": 1,
          "maximum": 1
        },
        "max_outbound_messages": {
          "type": "integer",
          "minimum": 1,
          "maximum": 6
        },
        "max_model_calls": {
          "type": "integer",
          "minimum": 1,
          "maximum": 20
        },
        "max_research_calls": {
          "type": "integer",
          "minimum": 1,
          "maximum": 10
        },
        "max_runtime_seconds": {
          "type": "integer",
          "minimum": 1,
          "maximum": 600
        },
        "max_reply_turns": {
          "type": "integer",
          "minimum": 1,
          "maximum": 4
        },
        "no_reply_followups": {
          "type": "integer",
          "minimum": 0,
          "maximum": 0
        }
      }
    },
    "CampaignCreate": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "request_text",
        "mode",
        "buyer_test_email",
        "profile_version",
        "config_version",
        "limits"
      ],
      "properties": {
        "request_text": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000
        },
        "mode": {
          "const": "simulation"
        },
        "buyer_test_email": {
          "type": "string",
          "format": "email"
        },
        "profile_version": {
          "type": "integer",
          "minimum": 1
        },
        "config_version": {
          "type": "integer",
          "minimum": 1
        },
        "limits": {
          "$ref": "#/$defs/Limits"
        }
      }
    },
    "Claim": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "text",
        "start",
        "end",
        "kind",
        "evidence_ids",
        "approved_fact_ids"
      ],
      "properties": {
        "text": {
          "type": "string"
        },
        "start": {
          "type": "integer",
          "minimum": 0
        },
        "end": {
          "type": "integer",
          "minimum": 0
        },
        "kind": {
          "type": "string",
          "enum": [
            "seller_fact",
            "prospect_fact",
            "hypothesis",
            "scheduling_fact"
          ]
        },
        "evidence_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "format": "uuid"
          }
        },
        "approved_fact_ids": {
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
    },
    "DraftProposal": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "purpose",
        "subject",
        "body_text",
        "claims",
        "used_slot_ids",
        "reason",
        "evidence_ids"
      ],
      "properties": {
        "purpose": {
          "type": "string",
          "enum": [
            "initial",
            "answer",
            "clarify",
            "offer_slots",
            "confirm"
          ]
        },
        "subject": {
          "type": "string",
          "maxLength": 200
        },
        "body_text": {
          "type": "string",
          "minLength": 1,
          "maxLength": 4000
        },
        "claims": {
          "type": "array",
          "items": {
            "$ref": "#/$defs/Claim"
          }
        },
        "used_slot_ids": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "reason": {
          "type": "string",
          "minLength": 1
        },
        "evidence_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "format": "uuid"
          }
        }
      }
    },
    "ReplyInterpretation": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "intent",
        "quote",
        "message_id",
        "confidence",
        "accepted_slot_id",
        "requested_time",
        "needs_clarification",
        "reason",
        "evidence_ids"
      ],
      "properties": {
        "intent": {
          "type": "string",
          "enum": [
            "interested",
            "question",
            "objection",
            "decline",
            "opt_out",
            "schedule_preference",
            "accept_slot",
            "ambiguous",
            "out_of_office",
            "request_human"
          ]
        },
        "quote": {
          "type": "string"
        },
        "message_id": {
          "type": "string",
          "format": "uuid"
        },
        "confidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "accepted_slot_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ]
        },
        "requested_time": {
          "anyOf": [
            {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "start",
                "timezone",
                "raw_text"
              ],
              "properties": {
                "start": {
                  "anyOf": [
                    {
                      "type": "string",
                      "format": "date-time"
                    },
                    {
                      "type": "null"
                    }
                  ]
                },
                "timezone": {
                  "anyOf": [
                    {
                      "type": "string"
                    },
                    {
                      "type": "null"
                    }
                  ]
                },
                "raw_text": {
                  "type": "string"
                }
              }
            },
            {
              "type": "null"
            }
          ]
        },
        "needs_clarification": {
          "type": "boolean"
        },
        "reason": {
          "type": "string",
          "minLength": 1
        },
        "evidence_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "format": "uuid"
          }
        }
      }
    },
    "VerificationResult": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "verdict",
        "unsupported_claims",
        "contradictions",
        "unauthorized_promises",
        "unanswered_questions",
        "injection_flags",
        "reason",
        "evidence_ids"
      ],
      "properties": {
        "verdict": {
          "type": "string",
          "enum": [
            "pass",
            "revise",
            "block"
          ]
        },
        "unsupported_claims": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "text",
              "reason"
            ],
            "properties": {
              "text": {
                "type": "string"
              },
              "reason": {
                "type": "string"
              }
            }
          }
        },
        "contradictions": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "unauthorized_promises": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "unanswered_questions": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "injection_flags": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "reason": {
          "type": "string",
          "minLength": 1
        },
        "evidence_ids": {
          "type": "array",
          "items": {
            "type": "string",
            "format": "uuid"
          }
        }
      }
    }
  }
}
```

Limits in this schema enforce the default single-conversation P0 ceiling. A reviewed increase requires changing both server configuration and validation bounds, plus rerunning relevant budget/concurrency tests; owner UI alone cannot bypass them. Adapter wire schemas remain provider-specific and must be captured from authenticated docs.
