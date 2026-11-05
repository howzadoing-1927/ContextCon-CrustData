# 07 · Git, worktrees and safe coding-agent parallelism

## Recommendation: two primary agents, then optional bounded help

Use one active writer per developer. D1's primary agent builds backend/research/state; D2's primary agent builds Google/UI. Each human reviews its agent and integrates at fixed times. Do not run five agents building overlapping versions of the whole app. For this eight-hour job, shared contracts, OAuth and side-effect correctness are bottlenecks; more unfinished branches increase integration cost.

A third short-lived agent can review a diff read-only or write a genuinely isolated ticket after contracts stabilize. Examples: UI empty-state copy on a separate component, adversarial contract tests, documentation review. An extra writer must have its own branch/worktree, allowed file list, base commit, deadline and acceptance test. At most three concurrent writers recommended, and only if both humans can review them; default stays two. This is a team operating rule, not a platform concurrency claim. Runtime “agents” in the product are bounded model roles, unrelated to how many coding assistants you run.

## Exact coordination pattern

1. At 23:00 create repository and `main`, copy approved planning docs, confirm contract 1.0. D1 makes the small shared layout/contracts baseline commit; both acknowledge SHA. No generated app scaffolding before 23:00.
2. D1 works on `feat/backend-core`; D2 on `feat/google-web`. Use separate local worktrees/checkouts even on one machine. Different branches in the same directory are not isolation. On two machines, separate clones are sufficient. Shared folder/synced checkout is not.
3. D1 owns root Python dependencies/migrations/contracts. D2 owns web package files/lockfile and Google folder. Integration notes are appended to each ticket's own note file; avoid two agents editing one status file. Root config changes are requested to the owner and landed as one small commit.
4. D1 is the only integration-branch merger and shared DB migration applier. D2 reviews changes affecting Google/UI. Merge one small checkpoint at a time into `main` (or a single agreed `integration` branch if main protection requires PRs). Never cherry-pick and later merge the same patch inadvertently. Keep main buildable; don't wait until 05:00 for the first merge.
5. Before each merge: working tree clean, base SHA known, inspect diff, check no secrets or forbidden paths, relevant tests pass, provider labels truthful. Integrator resolves conflicts with owner; do not accept “ours/theirs” for schema or lockfiles without review.
6. After merge, both sync to the same integrated baseline before the next dependent ticket. Do not rebase another agent's active branch from under it; let its owner rebase/merge the baseline. No force-push shared main. Record integrated SHA and contract version.
7. Use one shared live demo environment/DB and **one enabled live worker**. Other agent environments use isolated tenant/database and fixture/sandbox adapters; the phrase “test environment” alone does not prevent sending real email. Each worktree has separate virtualenv/node_modules/ports/build cache. Never run two agents against the same generated artifacts or migration database.
8. Secrets are ignored local environment or approved secret store, not Git/PR/prompt text. Cloud agents get only the least access needed. Secret rotation and separate test accounts beat sharing production keys. No agent may deploy another worker, change OAuth settings or run live side effects without its human coordinating the active environment.

After 23:00 a human can use standard `git worktree add` or the editor's native worktree controls. This pack intentionally provides no runnable pre-start setup script. Codex documents isolated worktree environments ([official worktrees guide](https://learn.chatgpt.com/docs/environments/git-worktrees)); Cursor documents cloud agents working on branches ([official cloud guide](https://cursor.com/docs/cloud-agent)). Isolation does not eliminate merge review, shared database conflicts or duplicate live effects.

## Integration checkpoints (all IST)

| Time | Both must share | Required proof | If failed |
|---|---|---|---|
| 23:15 Nov 5 | Base SHA, directory ownership, enums, Google adapter result/failure shape, config names | Web can parse a contract fixture; API health exists | Pair 15 min on contract; no independent schema drift |
| 00:00 Nov 6 | Auth+DB/task baseline and OAuth callback path | Real sign-in, persisted mission/task, seller scope status | Fix access/callback now; UI polish stops |
| 01:00 | Crustdata+model mapping and Google adapter smoke | Live canonical refs and actual test send/read/freebusy/event IDs | Cut breadth; pair on provider blocker |
| 02:00 | First complete merged workflow path | Real outreach reaches actor; real reply persisted | No new features; fix wiring and state |
| 03:00 | Booking + handoff merged | Explicit acceptance→event read-back→CRM/handoff | Cut all stretch; mentor question if useful |
| 04:00 | Mandatory safety and recovery fixes | Tests pass for allowlist, opt-out, replay, tenant, timeout | Only blocker fixes; no general refactor |
| 05:00 | Release candidate environment | Novel mission completes, evidence visible | Choose honest fallback and disclose gap |
| 06:00 | Frozen feature scope and video candidate | Candidate matches commit/environment | Fix only release blockers; recheck affected gate |
| 06:30 | Final candidate | Repo/video links open; no secrets | Submission checks take priority |

## Change protocol for shared contracts

The proposer writes: old field/behavior, proposed change, reason, affected routes/tables/adapters, fixture migration, responsible owner and integration SHA. Both acknowledge before mutation. D1 updates document plus executable schema after 23:00, D2 updates API client; merge together or make additive-compatible change first. Never rename fields to match a guessed provider payload; provider adapters normalize to our contract. Contract version stays outcome.v1 for compatible additions; incompatible changes need explicit baseline bump, not stealth edits.

## Copy-paste helper task prompt

> Work on isolated ticket [ID] from commit [SHA] in branch/worktree [name]. You may edit only [exact paths]. Read contracts outcome.v1 and policy docs. Do not modify dependencies, migrations, shared types, OAuth config, secrets or live environment. Do not run real outbound sends/calendar writes. Do not merge/deploy or spawn more agents. Acceptance is [specific check]. Return a small diff, actual checks/results, limitations and commit SHA by [time]. If the task requires forbidden paths, stop and propose a contract request. No application code before 23:00 IST Nov 5, 2026.

## Copy-paste read-only reviewer prompt

> Review the diff from [base] to [head] without changing files. Focus on tenant isolation, exact test-recipient mapping, MIME/header recipient bypasses, prompt injection, false claims/evidence, Gmail ambiguous sends, stale leases, booking replay and honest live/fixture labels. Identify only actionable issues with path/line, concrete failure trigger, impact and minimal fix. Do not access secrets or trigger provider actions. Report what was inspected and what could not be verified. A clean review is not proof live integration passed.

## Choosing Cursor or Codex

Use the tool each developer already knows. Cursor local Agent mode is a reasonable primary choice given existing access; background/cloud execution suits isolated asynchronous branches if environment setup is already solved. Codex local/worktree mode is an equally viable primary alternative. Do not ask both to implement the same ticket in the same folder. You may ask a separate read-only agent to review another tool's diff. Exact model labels/availability/pricing vary by account and date; verify installed choices rather than hardcoding a recommendation.

When an agent says “done,” ask for concrete API output, test result and provider receipt as appropriate, not a prose assurance. Merge checkpoint-sized units roughly every 30–60 minutes. Humans own final authorization/configuration, integration and honest submission claims.
