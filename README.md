# Outcome AI — two-developer hackathon implementation pack

Planning baseline v1.0 · prepared 5 November 2026 · all schedule times Asia/Kolkata (IST, UTC+05:30).

**No application code before 23:00 IST on 5 November 2026 (17:30 UTC). Repo and video due 07:00 IST on 6 November (01:30 UTC).** These files are specifications and prompts, not an implementation. Do not run implementation prompts early. Account preparation and reading are permitted by the supplied brief; resolve any organizer-specific uncertainty at kickoff.

## The job

A founder supplies a website, approved business facts and an unfamiliar B2B appointment-setting request. Outcome researches real companies and people through Crustdata, qualifies a prospect with evidence, sends a real Gmail message to a consenting test buyer, handles an unscripted reply, checks a real calendar, creates a real event, and finishes with a durable CRM record and handoff. Humans configure authority once and handle exceptions; they do not approve every routine decision.

**Simulation boundary:** the buyer role and its test email destination are simulated. Research, LLM decisions, Gmail send/read, Calendar free/busy/event creation, and the internal CRM/handoff must actually execute. No researched person's address may become an outbound recipient or event attendee. Do not describe the result as a real sales conversion.

## Reading and handoff order

| File | Purpose | Required readers |
|---|---|---|
| [01-product-and-judging.md](01-product-and-judging.md) | Scope, acceptance, judging proof | Both developers |
| [02-architecture-and-data.md](02-architecture-and-data.md) | Architecture, exactly 12 tables, tenancy, state and queue | Both, D1 owns |
| [03-api-and-payload-contracts.md](03-api-and-payload-contracts.md) | Frozen API, typed payloads, adapter boundaries | Both |
| [04-model-prompts-and-policy.md](04-model-prompts-and-policy.md) | LLM inputs/outputs, prompts, verification, Decision Ledger | D1, D2 reads policy |
| [05-developer-1-agent-brief.md](05-developer-1-agent-brief.md) | Backend implementation tickets and pasteable prompts | D1 |
| [06-developer-2-agent-brief.md](06-developer-2-agent-brief.md) | Google, UI, integration and demo tickets/prompts | D2 |
| [07-git-and-agent-coordination.md](07-git-and-agent-coordination.md) | Safe two-agent pattern, optional helpers, integration checkpoints | Both |
| [08-testing-and-simulation.md](08-testing-and-simulation.md) | Live test protocol, failure cases, release gates | Both |
| [09-overnight-runbook.md](09-overnight-runbook.md) | Hour-by-hour schedule, budgets, blockers, deployment and video | Both |
| [10-setup-checklist.md](10-setup-checklist.md) | Before/after start checklist and unresolved facts | Both |
| [11-sources-and-version-boundaries.md](11-sources-and-version-boundaries.md) | Source hierarchy, official links, API/version limits | Both agents |

For one-file sharing, use `OUTCOME-AI-COMPLETE-PACK.md`. The ZIP contains the same planning documents. Individual files are authoritative; regenerate the combined copy if changing them. This pack deliberately supersedes earlier 27-table designs, four-person assignments, bulk prospect targets, and routine approval flows. Earlier product vision remains context, not tonight's acceptance contract.

## Five fixed decisions

1. Build **one durable workflow** with bounded model calls, not a network of independent runtime agents.
2. Build one real vertical slice first: one campaign, one qualified prospect, one conversation, one booking, one internal CRM/handoff. Preserve tenant boundaries even with one demo tenant.
3. D1 owns backend/research/models/database/orchestration. D2 owns Next.js/Google OAuth/Gmail/Calendar adapters/integration/demo. D2 writes its Google adapters in Python to avoid a cross-language worker boundary.
4. Start with two primary coding agents total, one per developer, each in its own branch/worktree. Optional short read-only review is useful. More writers require explicit isolated tickets; no swarm.
5. The application executes side effects only through durable actions with tenant checks, suppression checks, recipient allowlists, evidence verification, budgets and ambiguity handling.

## Definition of finished

A fresh request that was not rehearsed produces a persisted evidence-backed prospect and real test email; a real reply is ingested and changes the next action; explicit slot acceptance causes a real event and an internal CRM/handoff. Provider IDs and ledger decisions prove the sequence. Required negative tests pass. UI, logs and video distinguish LIVE, CACHED, FIXTURE and SIMULATED BUYER. A blocked or cached fallback is shown honestly and is not relabeled complete P0.

## Critical unknowns to close

Google callback URLs are unset; calendar.freebusy save/grant is unverified; exact Crustdata account API schema/identity fields/credits and Azure deployment capabilities are not established; no Vedora knowledge documents were available in this task. See setup and source register. Do not invent missing capabilities, provider field names, account access, pricing or product facts.
