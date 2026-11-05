# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Next.js App Router + TypeScript + Tailwind CSS v4 + shadcn/ui, in `apps/web`. Backend is a separate FastAPI service (`/api/v1`, contract `outcome.v1`) owned by Developer 1; the web app talks only to that API and to Supabase Auth. Desktop-first; the reference viewport is 1440 px wide, with a usable floor at 1024 px.

## Users

- **Seller / operator.** An authenticated member of one organization (a founder or a sales lead). They set up the seller's authority once: website, approved facts, Google connection, the consented test buyer inbox, working hours and limits. Then they type a free-text mission and watch the work happen. They do not approve routine drafts.
- **Exception owner.** The same seller, called in only when the worker is blocked: a missing fact, an ambiguous time, failed Google authorization, or an uncertain send. They need the reason, the evidence, and the allowed resolutions. They must not get a generic approve button.
- **Evaluator / judge.** Watches the operator's screen and needs to check, at a glance, that the work is real. That means seeing which steps executed live, which are cached or fixtures, which party is the simulated buyer, and why each decision was made.

The buyer actor is a consenting teammate replying from a real Gmail inbox. They never use this UI.

## Product Purpose

Outcome AI does the small but complete job of an outsourced SDR. It understands a seller, finds one relevant company and person through Crustdata research, explains with evidence why outreach is justified, emails a consented test buyer, handles the buyer's actual reply, checks a real calendar, books a real event, and finishes with a durable internal CRM record and handoff.

Success means the operator can trust what they see. Every claim traces back to a source, every effect to a provider ID, and every stop to a stated reason.

## Positioning

The product is an autonomous worker that gets authority once and returns proof, not a drafting assistant that asks for approval at each step. The UI's job is to make that proof readable: a decision ledger with sources, honest provenance labels, and a clear boundary between the real researched identity and the simulated buyer.

## Operating Context

- Flow: sign in → select organization → workspace setup (once) → new mission → mission detail (polled every 2 s) → completion/handoff, or the exception drawer when blocked.
- Mission lifecycle (campaign): `draft → running → waiting_reply → running → completed`, plus `no_match`, `needs_human`, `paused`, `stopped`, `failed`.
- Conversation lifecycle: `researching → qualified → drafting → waiting_reply → evaluating_reply → offering_slots → waiting_slot_acceptance → booking → booked → completed`, plus terminal `declined`, `suppressed`, `needs_human`, `send_unknown`, `stopped`.
- Waiting for a buyer is a normal state, not ongoing work. It shows the last inbox check and the next expected event; it does not show a spinner.
- The operator often has Gmail and Google Calendar open beside this app to cross-check provider IDs.

## Capabilities and Constraints

- Mode is always "Live tools · simulated buyer" (`mode: "simulation"`). This label is visible on every mission surface.
- Provenance per step is one of `LIVE`, `CACHED`, `FIXTURE` or `SIMULATED BUYER`. Replayed or fixture data is never labeled live.
- Facts carry separate labels: observed (provider evidence), operator-approved, hypothesis, conflicted. Each fact opens its evidence: excerpt, source kind, provider ref and field path, retrieval time, source as-of (or "unknown"), and content hash.
- The real researched person's email is never shown as a destination or selectable recipient. Delivery goes only to the consented test inbox, labeled as playing the buyer.
- There is no approve-all, force-send, or mark-complete control. Pause/stop explains which effects are pending and which are already in flight.
- The completion card is derived from API receipts. A calendar invitation is never labeled "accepted"; attendee acceptance is `not_verified`. Event links appear only when the API returns them.
- Unknown cost is shown as unknown, never as zero.
- The UI must render without crashing for empty arrays, null conversation/handoff, 401/403/404/409/422/503, a stale worker, reauthorization needed, and no-match.
- Terminology: **mission** (API: campaign), **prospect case**, **decision ledger**, **exception** (a blocked decision), **handoff**.
- Open / undecided: the demo seller's identity and approved facts (keep seller copy generic); the deployed API hostname; the real Google connection status. Most backend routes are not built yet, so the UI develops against labeled fixtures.

## Brand Commitments

Product name: **Outcome AI**. Voice: plain, factual, and specific. It states what happened and why, and makes no sales hype or claims of buyer demand. No logo assets exist yet.

## Evidence on Hand

- Contract schemas and fixtures: `contracts/schemas/*.json`, `contracts/fixtures/*.json` on `feat/backend-core` (fixtures carry `"_fixture": "FIXTURE"`).
- Planning pack: `01-…` to `11-…` Markdown files at the repo root.
- No customer data, testimonials, screenshots, or approved seller facts exist. Do not fabricate any.

## Product Principles

1. Proof over polish. If a choice trades evidence visibility for aesthetics, keep the evidence.
2. Honest state. Show exactly what the worker is doing, waiting on, or blocked by, and never imply progress that isn't happening.
3. Humans handle exceptions only. Controls exist for setup, pause/stop and typed resolutions, not for routine approval.
4. Real and simulated never blur. The researched identity and the test buyer stay visually and textually distinct.
5. Calm density. Operators scan a lot of structured data, so use consistent placement and quiet chrome, and make state impossible to miss.

## Accessibility & Inclusion

WCAG 2.2 AA. Status is always conveyed in text as well as colour. Ledger rows, fact popovers and drawers are keyboard-operable and drawers trap focus. Respect `prefers-reduced-motion`.
