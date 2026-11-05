# 01 · Product requirements and judging alignment

## Product promise and service replaced

Outcome AI performs the small but complete job of an outsourced SDR: understand a seller, find a relevant business and buyer, explain why outreach is justified, conduct a conversation, coordinate a demo, and give the seller an actionable meeting brief. A prospect list or a generated email alone is unfinished work.

The supplied “Services as software” brief is the source of judging requirements. The source conversation reports doors at 21:30, kickoff at 22:00, walkthrough at 22:30, build start at 23:00 on 5 November; code/video due at 07:00 on 6 November. These organizer details are user-supplied, not independently confirmed event rules. Confirm submission method, time zone, video duration and repository visibility at kickoff.

## Users and authority

- **Seller/operator:** authenticated organization member, authorizes business facts, connects its Google account, chooses working hours, consented destinations and limits, then launches the job.
- **Autonomous worker:** researches, reasons, sends permitted messages, polls replies, books only after acceptance, writes handoff. It cannot expand its own permissions.
- **Buyer actor:** a consenting teammate at a dedicated Gmail inbox. May reply freely, decline, ask questions, negotiate dates or opt out. This is buyer participation, not a human approving the agent's work.
- **Exception owner:** seller member who resolves missing facts, ambiguous identity/time, failed authorization or uncertain side effects. Never asked to approve routine drafts.

Onboarding approval is a business authority boundary, not a recurring approval step. Website content is evidence, not permission to offer discounts or guarantees. Treat sender/buyer accounts as distinct for clear proof. Three configured OAuth test users are authorization eligibility, not an outbound mailing list.

## P0: only the following must ship

| Capability | Smallest real implementation | Exit proof |
|---|---|---|
| Seller setup | Website URL, bounded fetch of homepage, approved fact/FAQ text, timezone, calendar/business hours, owner and recipient consent | Approved version with source evidence |
| Auth/tenancy | Supabase sign-in, one organization and membership; two-tenant negative test | Unauthorized reads/writes fail |
| Job understanding | Free-text request normalized into ICP, exclusions, objective, clarifications | Structured plan and reason |
| Research | Crustdata company search/lookup and person search/lookup using actual available APIs; obtain company/person canonical references and relationship evidence | Live response provenance and mapped IDs |
| Qualification | Explicit must-have/unknown/exclusion evaluation; select at most one eligible prospect initially | Rule result with evidence per criterion |
| Outreach | Real Gmail send to one explicitly mapped, consented buyer test inbox | Gmail message/thread ID; researched address never used |
| Conversation | Poll sender mailbox; match thread and allowed sender; model handles actual newest reply | Persisted inbound ID and decision |
| Scheduling | One connected seller calendar, duration 15 minutes default, timezone explicit; offer at most two free slots; accept one; recheck and insert | Real event ID and read-back |
| Finish | Internal CRM state and durable handoff summary on dashboard; separate owner email if safely configured | Event, transcript, evidence, next steps linked |
| Exceptions | Visible blocking decisions, pause/stop, bounded retries | Resolvable exceptions and clear status |
| Decision Ledger | Compact reasons, sources, inputs, policy outcomes and actual effects | Expandable chronological trace |

Private Supabase Storage holds bounded source snapshots and redacted run evidence. The P0 optional document input is pasted text or a small UTF-8 text file, not a general PDF/DOCX ingestion system. A file-format matrix, OCR, browsing many pages and embeddings are stretch. A working homepage fetch plus approved pasted seller facts is sufficient website-first setup. If fetch is blocked, ask for pasted source text and label it operator supplied.

Internal CRM is real persistent application data, not an external Salesforce/HubSpot integration. Dashboard handoff is mandatory. Owner email is an independently tracked action and stretch if it threatens the core slice. If dashboard succeeds and owner email fails, show handoff complete / notification failed separately.

## Explicit non-goals and stretch order

No real cold outbound, recruiting workflow, payment flow, signup verification, broad autonomous web browsing, bulk campaigns, background follow-ups without reply, external CRM integration, Gmail watch/PubSub, multi-calendar pooling, universal time-language parser, multi-user admin UI, vector DB or model orchestration framework. Never build them before P0 passes.

Stretch in order: notification email, second unfamiliar ICP, richer objection handling, optional documents, multiple prospects/campaigns, external CRM adapter. Safety, tenant isolation and source attribution are never stretch. Do not enable a second campaign until per-tenant budgets, scheduling locks and deduplication are tested.

## Journey and screens

1. Sign in and select the seeded member organization.
2. Setup card: website, facts with source links/approval, connect Google, connection status, test buyer consent, business hours.
3. New mission: free text, explicit mode “Live tools · simulated buyer,” small limits, launch.
4. Mission detail: workflow stage, prospect/company/person references, observed facts vs inferred relevance, messages, evidence ledger, next action or blocker. Poll API every 2 seconds; no realtime infrastructure required.
5. Completion card: seller-local time and UTC, event link, simulated attendee label, fit rationale, buyer-stated need, open questions and next steps. Exception drawer with permitted resolution actions.

Do not make the founder fill a large CRM form. Seed known setup after 23:00, then type a fresh mission during recording. Do not seed researched results for the novel request.

## Qualification semantics

Must-have criteria are true / false / unknown. A must-have unknown is not a match. Exclusions take precedence. Titles can support likely role relevance but never prove purchasing authority. Distinguish “works at company” from “is decision-maker.” Crustdata identity/relationship evidence is mandatory; additional official evidence may refine criteria but cannot replace missing canonical identity with an invented one.

Prefer a broad B2B segment that the available Crustdata account can resolve reliably. Vedora/CBSE schools in Kanpur is an optional candidate, not a fixed demo dependency: historical context itself reported weak principal and affiliation coverage. Never infer affiliation, student count or buying pain from a school name. Try another valid segment or return an explained no-match if identity is unavailable. Product facts about Vedora must come from operator-approved materials, not this pack.

## Judging proof matrix

| Criterion supplied | What judges see | Test and evidence |
|---|---|---|
| Unfamiliar request → finished job | Newly entered ICP changes company/person research and booking handoff | Novel-run log; request timestamp; provider receipts |
| Human only for exceptions | No draft approval clicks; actor replies as buyer | Timeline distinguishes operator actions from buyer participation |
| Every decision reason/source | Selected/rejected prospect reasons, factual claims, policy decisions and book/no-book | Decision IDs and source excerpts; negative decisions retained |
| Canonical identity graph | Actual company and person references plus current relationship evidence | Raw-response hash, field paths, retrieval times |
| Robust messy inputs | Ambiguous date produces clarification; opt-out stops; tool failure is bounded | Recorded test results and visible exception |
| Two-minute real demo | Live workflow with clearly labeled buyer simulation | Video with any time cuts disclosed; actual runtime reported |

A two-minute video is a presentation target, not a guarantee all providers finish within 120 seconds. Target 90 seconds of system work plus actor replies in rehearsal. If longer, use disclosed cuts/time compression with visible timestamps; never call a compressed recording a two-minute uninterrupted execution. At least one unscripted reply should alter a model decision rather than follow a hardcoded accepted phrase.

## Acceptance and outcome labels

`completed` means verified calendar event + durable internal CRM/handoff. `booked` alone means event read-back passed. `waiting_reply` is legitimate unfinished work. `declined`, `suppressed`, `no_match` are explained terminal non-conversions. `needs_human` means blocked exception; `send_unknown` means delivery outcome uncertain, never automatic resend. A calendar invitation is not evidence of attendee acceptance; explicit email acceptance and event creation must be shown separately. Never claim buyer demand was validated by a simulated conversation.
