import type {
  BriefSave,
  CampaignCreate,
  ConnectionSummary,
  ControlInput,
  DecisionView,
  ErrorCode,
  HealthReady,
  MembershipView,
  OrganizationView,
  PolicyUpdate,
  ProfileUpdate,
  ResolveInput,
  SourceInput,
} from "@/lib/contracts";
import { DEFAULT_LIMITS, REQUIRED_GOOGLE_SCOPES, SCHEMA_VERSION } from "@/lib/contracts";
import type { Transport, TransportRequest, TransportResponse } from "@/lib/api/transport";
import { at, fid } from "./ids";
import { analyzeWebsiteFixture, applyBrief, loadSavedBrief, normalizeWebsite, storeBrief } from "./onboarding";
import {
  BUYER_TEST_EMAIL,
  buildMission,
  CALENDAR_ID,
  FIXTURE_EV,
  type FixtureMission,
  HAPPY_PATH,
  type MissionScenario,
  OWNER_TEST_EMAIL,
  SELLER_TZ,
  toCampaignView,
} from "./missions";

export const GLOBAL_SCENARIOS = {
  healthy: "Healthy workspace",
  setup_incomplete: "Setup incomplete",
  google_reauth: "Google needs reauthorization",
  worker_stale: "Worker heartbeat stale",
  dependency_503: "API dependency unavailable (503)",
  unauthorized_401: "Session expired (401)",
  forbidden_403: "Not a member (403)",
  empty: "No missions yet",
} as const;

export type GlobalScenario = keyof typeof GLOBAL_SCENARIOS;

const SCENARIO_KEY = "outcome.fixture.scenario";

export function getGlobalScenario(): GlobalScenario {
  if (typeof window === "undefined") return "healthy";
  const value = window.localStorage.getItem(SCENARIO_KEY);
  return value && value in GLOBAL_SCENARIOS ? (value as GlobalScenario) : "healthy";
}

export function setGlobalScenario(scenario: GlobalScenario) {
  window.localStorage.setItem(SCENARIO_KEY, scenario);
  state = initialState();
}

export const FIXTURE_ORG_ID = fid("org:demo-seller");
export const FIXTURE_ORG_ID_2 = fid("org:second-tenant");

const MEMBERSHIPS: MembershipView[] = [
  { organization_id: FIXTURE_ORG_ID, organization_name: "Demo Seller Co.", role: "owner" },
  { organization_id: FIXTURE_ORG_ID_2, organization_name: "Second Tenant (isolation test)", role: "member" },
];

const SCENARIO_REQUESTS: Record<MissionScenario, string> = {
  draft: "Find a fleet operator in Pune with a dispatch team and book a short intro with their operations head.",
  researching: "Find a mid-market logistics company in India and its sales leader, explain the fit, and book a 15-minute demo.",
  drafting: "Find a logistics software company hiring field coordinators and book a demo with sales leadership.",
  waiting_reply: "Book a 15-minute demo with a sales leader at an Indian freight company with 200–2,000 employees.",
  evaluating_reply: "Find a logistics company with a growing field team and book a demo with their head of sales.",
  offering_slots: "Book a short demo with a VP Sales at a logistics company in India. Do not assume pain we can't verify.",
  waiting_slot_acceptance: "Find a freight technology company and book a demo with a sales leader next week.",
  booking: "Book a demo with a sales leader at a logistics company that is hiring coordinators.",
  booked: "Find a logistics company in India and book a 15-minute demo with its VP Sales.",
  completed: "Find a relevant B2B company and its sales leader in the approved market, explain the fit, and book a 15-minute demo. Do not assume they have a problem we cannot verify.",
  needs_human_time: "Book a demo with a logistics sales leader; offer two slots this week.",
  needs_human_reauth: "Find a freight company sales leader and book a 15-minute intro.",
  send_unknown: "Book a demo with the head of sales at a logistics software company in India.",
  no_match: "Find a 200–2,000 person logistics firm in Kanpur, excluding staffing, and book a demo with its sales head.",
  declined: "Book an intro with a sales leader at a mid-size freight company.",
  suppressed: "Find a logistics company's VP Sales and book a short demo.",
  paused: "Book a 15-minute demo with a sales leader at an Indian logistics company.",
  stopped: "Find a fleet services company and book a demo with sales leadership.",
  failed: "Find a logistics company's sales leader using person lookup and book a demo.",
};

const PROGRESSION_ID = fid("mission:progression");

interface ProgressionMission extends FixtureMission {
  startedAt: number;
}

interface State {
  scenario: GlobalScenario;
  missions: FixtureMission[];
  progressions: ProgressionMission[];
  overrides: Map<string, MissionScenario>;
  history: Map<string, { decisions: DecisionView[]; minVersion: number }>;
  workspace: Record<string, OrganizationView>;
  replays: Map<string, TransportResponse>;
}

function connection(status: ConnectionSummary["status"]): ConnectionSummary {
  return {
    connection_id: fid("conn:seller"),
    status,
    account_email: "seller@demo-seller.example",
    calendar_id: CALENDAR_ID,
    granted_scopes: status === "connected" ? [...REQUIRED_GOOGLE_SCOPES] : REQUIRED_GOOGLE_SCOPES.slice(0, 2),
  };
}

function health(scenario: GlobalScenario): HealthReady {
  if (scenario === "worker_stale") return { status: "not_ready", database: "ok", worker: "stale", last_seen_age_seconds: 94 };
  if (scenario === "dependency_503") return { status: "not_ready", database: "error", worker: "fresh", last_seen_age_seconds: 4 };
  return { status: "ready", database: "ok", worker: "fresh", last_seen_age_seconds: 4 };
}

function workspaceFor(orgId: string, scenario: GlobalScenario): OrganizationView {
  const view = baseWorkspace(orgId, scenario);
  if (orgId === FIXTURE_ORG_ID) return view;
  const rebranded = JSON.stringify(view).replaceAll("Demo Seller Co.", "Second Tenant Ltd.").replaceAll("demo-seller.example", "second-tenant.example");
  return JSON.parse(rebranded) as OrganizationView;
}

function baseWorkspace(orgId: string, scenario: GlobalScenario): OrganizationView {
  const incomplete = scenario === "setup_incomplete";
  const owner = orgId === FIXTURE_ORG_ID;
  return {
    id: orgId,
    name: owner ? "Demo Seller Co." : "Second Tenant (isolation test)",
    website_url: incomplete ? null : "https://demo-seller.example/",
    timezone: SELLER_TZ,
    profile_version: incomplete ? 0 : 1,
    approved_at: incomplete ? null : at(-160),
    approved_by: incomplete ? null : "seller@demo-seller.example",
    approved_facts: incomplete
      ? []
      : [
          {
            id: "fact-what",
            text: "Demo Seller Co. schedules field-service visits for mid-market fleet operators.",
            evidence_ids: [FIXTURE_EV.seller.id],
            authority: "operator_approved",
            approved: true,
          },
          {
            id: "fact-onboarding",
            text: "Standard onboarding is a two-week guided setup with a named contact.",
            evidence_ids: [FIXTURE_EV.sellerOnboarding.id],
            authority: "operator_approved",
            approved: true,
          },
        ],
    proposed_facts: incomplete
      ? []
      : [
          {
            id: "proposed-pricing",
            text: "Plans start with a free pilot for the first month.",
            evidence_ids: [FIXTURE_EV.seller.id],
          },
        ],
    faq: incomplete
      ? []
      : [
          {
            question: "How long does onboarding take?",
            answer: "About two weeks, guided by a named contact.",
            fact_ids: ["fact-onboarding"],
          },
        ],
    forbidden_promises: incomplete ? [] : ["Discounts or custom pricing", "Delivery or uptime guarantees", "Integration with a named system"],
    sources: incomplete
      ? []
      : [
          {
            id: fid("source:homepage"),
            kind: "website",
            label: "https://demo-seller.example/",
            status: "ready",
            retrieved_at: at(-180),
            evidence_ids: [FIXTURE_EV.seller.id],
            error: null,
          },
          {
            id: fid("source:pasted"),
            kind: "pasted_text",
            label: "Onboarding notes",
            status: "ready",
            retrieved_at: at(-170),
            evidence_ids: [FIXTURE_EV.sellerOnboarding.id],
            error: null,
          },
        ],
    evidence: incomplete ? [] : [FIXTURE_EV.seller, FIXTURE_EV.sellerOnboarding],
    policy: {
      config_version: incomplete ? 0 : 1,
      simulation: true,
      consented_recipients: incomplete
        ? []
        : [
            {
              email: BUYER_TEST_EMAIL,
              role: "buyer_test",
              consent_record: "Teammate consent recorded in kickoff notes, 5 Nov",
              consented_at: at(-200),
            },
            {
              email: OWNER_TEST_EMAIL,
              role: "owner_test",
              consent_record: "Seller owner, self",
              consented_at: at(-200),
            },
          ],
      selected_calendar_id: incomplete ? null : CALENDAR_ID,
      working_hours: { timezone: SELLER_TZ, weekdays: [1, 2, 3, 4, 5], start: "09:00", end: "17:00" },
      duration_minutes: 15,
      limits: DEFAULT_LIMITS,
    },
    connection: incomplete ? null : connection(scenario === "google_reauth" ? "reauth_required" : "connected"),
    worker: health(scenario),
    viewer_role: owner ? "owner" : "member",
  };
}

function withSavedBrief(base: OrganizationView): OrganizationView {
  const saved = loadSavedBrief();
  if (!saved || saved.id !== base.id) return base;
  return { ...saved, policy: { ...base.policy, working_hours: saved.policy.working_hours, duration_minutes: saved.policy.duration_minutes }, connection: base.connection, worker: base.worker, viewer_role: base.viewer_role };
}

function initialState(): State {
  const scenario = getGlobalScenario();
  const all = Object.keys(SCENARIO_REQUESTS) as MissionScenario[];
  return {
    scenario,
    missions:
      scenario === "empty"
        ? []
        : all.map((s, i) => ({
            id: fid(`mission:${s}`),
            scenario: s,
            request_text: SCENARIO_REQUESTS[s],
            created_minute: -i * 37,
          })),
    progressions:
      scenario === "empty"
        ? []
        : [
            {
              id: PROGRESSION_ID,
              scenario: "draft",
              request_text: "Watch this one: it advances one stage every few seconds to exercise polling and the route.",
              created_minute: 5,
              startedAt: Date.now(),
            },
          ],
    overrides: new Map(),
    history: new Map(),
    workspace: {
      [FIXTURE_ORG_ID]: withSavedBrief(workspaceFor(FIXTURE_ORG_ID, scenario)),
      [FIXTURE_ORG_ID_2]: workspaceFor(FIXTURE_ORG_ID_2, scenario),
    },
    replays: new Map(),
  };
}

let state: State = initialState();

const STEP_MS = 6000;

function progressionScenario(p: ProgressionMission): MissionScenario {
  const step = Math.min(HAPPY_PATH.length - 1, Math.floor((Date.now() - p.startedAt) / STEP_MS));
  return HAPPY_PATH[step];
}

function withHistory(m: FixtureMission): FixtureMission {
  const h = state.history.get(m.id);
  return h ? { ...m, history: h.decisions, minVersion: h.minVersion } : m;
}

function allMissions(): FixtureMission[] {
  return [
    ...state.progressions.map((p) => withHistory({ ...p, scenario: state.overrides.get(p.id) ?? progressionScenario(p) })),
    ...state.missions.map((m) => withHistory({ ...m, scenario: state.overrides.get(m.id) ?? m.scenario })),
  ];
}

function record(missionId: string, decision: DecisionView, fromVersion: number) {
  const h = state.history.get(missionId) ?? { decisions: [], minVersion: 0 };
  state.history.set(missionId, { decisions: [...h.decisions, decision], minVersion: fromVersion + 2 });
}

function findMission(id: string) {
  const mission = allMissions().find((m) => m.id === id);
  return mission ? buildMission(mission) : null;
}

/* ---------- Response helpers ---------- */

function ok(status: number, data: unknown): TransportResponse {
  return {
    status,
    body: { _fixture: "FIXTURE", schema_version: SCHEMA_VERSION, data, correlation_id: crypto.randomUUID() },
  };
}

function fail(status: number, code: ErrorCode, message: string, details: Record<string, unknown> = {}, retryable = false): TransportResponse {
  return {
    status,
    body: {
      _fixture: "FIXTURE",
      schema_version: SCHEMA_VERSION,
      error: { code, message, retryable, details },
      correlation_id: crypto.randomUUID(),
    },
  };
}

function page<T>(items: T[], cursor: string | undefined, limit: number) {
  const start = cursor ? Number(cursor) : 0;
  const slice = items.slice(start, start + limit);
  const next = start + limit < items.length ? String(start + limit) : null;
  return { items: slice, next_cursor: next };
}

function delay(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 160 + Math.random() * 180));
}

/* ---------- Router ---------- */

function route(req: TransportRequest): TransportResponse {
  const { method, path } = req;
  const orgId = req.headers["X-Organization-ID"];
  const scenario = state.scenario;

  if (path === "/health/ready") {
    const h = health(scenario);
    return h.status === "ready"
      ? ok(200, h)
      : fail(
          503,
          "DEPENDENCY_UNAVAILABLE",
          h.database === "error" ? "Database is not reachable." : "Worker heartbeat is stale.",
          h as unknown as Record<string, unknown>,
          true,
        );
  }

  if (scenario === "unauthorized_401") return fail(401, "UNAUTHENTICATED", "Access token expired.");
  if (!req.headers.Authorization) return fail(401, "UNAUTHENTICATED", "Missing bearer token.");

  if (path === "/me/memberships") return ok(200, { items: MEMBERSHIPS });

  if (scenario === "forbidden_403") {
    return fail(403, "FORBIDDEN", "You are not a member of the selected organization.");
  }
  const workspace = orgId ? state.workspace[orgId] : undefined;
  if (!workspace) return fail(403, "FORBIDDEN", "Select an organization you belong to.");
  const isOwner = workspace.viewer_role === "owner";

  if (scenario === "dependency_503" && path.startsWith("/campaigns")) {
    return fail(503, "DEPENDENCY_UNAVAILABLE", "The database is not reachable from the API.", {}, true);
  }

  const key = req.headers["Idempotency-Key"];
  if (method !== "GET" && key) {
    const replay = state.replays.get(`${orgId}:${method}:${path}:${key}`);
    if (replay) return replay;
  }
  const remember = (response: TransportResponse) => {
    if (method !== "GET" && key && response.status < 400) state.replays.set(`${orgId}:${method}:${path}:${key}`, response);
    return response;
  };
  if (method !== "GET" && !key) return fail(400, "VALIDATION_FAILED", "Idempotency-Key header is required.");

  /* Workspace */
  if (path === "/workspace" && method === "GET") return ok(200, { ...workspace, worker: health(scenario) });

  if (path === "/workspace/profile" && method === "PUT") {
    if (!isOwner) return fail(403, "FORBIDDEN", "Only owners can approve the seller profile.");
    const body = req.body as ProfileUpdate;
    if (body.expected_profile_version !== workspace.profile_version) {
      return fail(409, "CONFLICT", `Profile is at version ${workspace.profile_version}, not ${body.expected_profile_version}.`);
    }
    const proposedIds = new Set(body.approved_facts.map((f) => f.id));
    const next: OrganizationView = {
      ...workspace,
      name: body.name,
      website_url: body.website_url,
      timezone: body.timezone,
      approved_facts: body.approved_facts,
      proposed_facts: workspace.proposed_facts.filter((f) => !proposedIds.has(f.id)),
      faq: body.faq,
      forbidden_promises: body.forbidden_promises,
      profile_version: workspace.profile_version + 1,
      approved_at: new Date().toISOString(),
      approved_by: "seller@demo-seller.example",
    };
    state.workspace[workspace.id] = next;
    return remember(ok(200, next));
  }

  if (path === "/workspace/sources" && method === "POST") {
    if (!isOwner) return fail(403, "FORBIDDEN", "Only owners can add seller sources.");
    const body = req.body as SourceInput;
    if (body.kind === "website" && !/^https:\/\//.test(body.url)) {
      return fail(422, "DOMAIN_INVALID", "Website must be a public HTTPS URL.", { field: "url" });
    }
    if (body.kind === "website" && /localhost|127\.0\.0\.1|169\.254\./.test(body.url)) {
      return fail(422, "DOMAIN_INVALID", "Private, local and metadata addresses can't be fetched.", { field: "url" });
    }
    const sourceId = fid(`source:${key}`);
    const label = body.kind === "website" ? body.url : body.title;
    workspace.sources = [
      ...workspace.sources,
      { id: sourceId, kind: body.kind, label, status: "ingesting", retrieved_at: null, evidence_ids: [], error: null },
    ];
    setTimeout(() => {
      const ws = state.workspace[workspace.id];
      ws.sources = ws.sources.map((s) =>
        s.id === sourceId ? { ...s, status: "ready", retrieved_at: new Date().toISOString(), evidence_ids: [FIXTURE_EV.seller.id] } : s,
      );
      if (!ws.evidence.some((e) => e.id === FIXTURE_EV.seller.id)) ws.evidence = [...ws.evidence, FIXTURE_EV.seller];
      ws.proposed_facts = [
        ...ws.proposed_facts,
        { id: `proposed-${sourceId.slice(0, 6)}`, text: `Proposed from “${label}”: review before approving.`, evidence_ids: [FIXTURE_EV.seller.id] },
      ];
    }, 3500);
    return remember(ok(202, { task_id: fid(`task:${key}`), status: "ready" }));
  }

  if (path === "/workspace/website-analysis" && method === "POST") {
    if (!isOwner) return fail(403, "FORBIDDEN", "Only owners can read the seller website.");
    const url = normalizeWebsite((req.body as { url?: string }).url ?? "");
    if (!url) return fail(422, "VALIDATION_FAILED", "Enter your company website, like yourcompany.com.", { field: "url" });
    if (/localhost|127\.0\.0\.1|169\.254\./.test(url)) {
      return fail(422, "DOMAIN_INVALID", "Private, local and metadata addresses can't be fetched.", { field: "url" });
    }
    return remember(ok(200, analyzeWebsiteFixture(url)));
  }

  if (path === "/workspace/brief" && method === "PUT") {
    if (!isOwner) return fail(403, "FORBIDDEN", "Only owners can save the founder brief.");
    const body = req.body as BriefSave;
    if (body.expected_profile_version !== workspace.profile_version) {
      return fail(409, "CONFLICT", `Profile is at version ${workspace.profile_version}, not ${body.expected_profile_version}.`);
    }
    if (!body.seller_brief.founder_name.trim() || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(body.seller_brief.founder_email)) {
      return fail(422, "VALIDATION_FAILED", "Founder name and a valid contact email are required.", { field: "founder_email" });
    }
    const next = applyBrief(workspace, body, fid(`source:brief:${key}`));
    state.workspace[workspace.id] = next;
    storeBrief(next);
    return remember(ok(200, next));
  }

  if (path === "/workspace/policy" && method === "PUT") {
    if (!isOwner) return fail(403, "FORBIDDEN", "Only owners can change policy.");
    const body = req.body as PolicyUpdate;
    if (body.expected_config_version !== workspace.policy.config_version) {
      return fail(409, "CONFLICT", `Policy is at version ${workspace.policy.config_version}, not ${body.expected_config_version}.`);
    }
    const buyers = body.consented_recipients.filter((r) => r.role === "buyer_test");
    if (buyers.length !== 1 || buyers.some((r) => !r.consent_record.trim())) {
      return fail(422, "DOMAIN_INVALID", "Exactly one buyer test inbox with a consent record is required.", { field: "consented_recipients" });
    }
    const next = { ...workspace, policy: { ...body, config_version: workspace.policy.config_version + 1 } };
    state.workspace[workspace.id] = next;
    return remember(ok(200, next));
  }

  /* Google */
  if (path === "/google/status" && method === "GET") return ok(200, workspace.connection);
  if (path === "/google/connect" && method === "POST") {
    if (!isOwner) return fail(403, "FORBIDDEN", "Only owners can connect Google.");
    state.workspace[workspace.id] = { ...workspace, connection: connection("connected") };
    return remember(ok(200, { authorization_url: "/setup?google=fixture-consent", expires_at: new Date(Date.now() + 600_000).toISOString() }));
  }

  /* Campaigns */
  if (path === "/campaigns" && method === "GET") {
    const views = allMissions().map((m) => toCampaignView(buildMission(m).detail));
    views.sort((a, b) => b.created_at.localeCompare(a.created_at));
    return ok(200, page(views, req.query?.cursor as string | undefined, Number(req.query?.limit ?? 25)));
  }

  if (path === "/campaigns" && method === "POST") {
    if (!isOwner) return fail(403, "FORBIDDEN", "Only owners can launch missions in this organization.");
    const body = req.body as CampaignCreate;
    if (workspace.profile_version < 1) return fail(422, "DOMAIN_INVALID", "Approve the seller profile before launching a mission.");
    if (!workspace.connection || workspace.connection.status !== "connected") {
      return fail(422, "DOMAIN_INVALID", "Seller Google connection must be connected with all four scopes.");
    }
    if (body.profile_version !== workspace.profile_version || body.config_version !== workspace.policy.config_version) {
      return fail(409, "CONFLICT", "Setup changed since this form loaded.");
    }
    const consented = workspace.policy.consented_recipients.some((r) => r.role === "buyer_test" && r.email === body.buyer_test_email);
    if (!consented) {
      return fail(422, "RECIPIENT_NOT_ALLOWED", "Only the consented test buyer can receive this message.", { field: "buyer_test_email" });
    }
    const mission: ProgressionMission = {
      id: fid(`mission:new:${key}`),
      scenario: "draft",
      request_text: body.request_text,
      created_minute: (Date.now() - Date.parse(at(0))) / 60_000,
      startedAt: Date.now(),
    };
    state.progressions.unshift(mission);
    const detail = buildMission(mission).detail;
    return remember(ok(202, { ...toCampaignView(detail), status: "running", task_id: fid(`task:${key}`) }));
  }

  const match = path.match(/^\/campaigns\/([^/]+)(?:\/(ledger|control|poll))?$/);
  if (match) {
    const [, id, sub] = match;
    const found = findMission(decodeURIComponent(id));
    if (!found) return fail(404, "NOT_FOUND", "No mission with this id in the selected organization.");
    if (!sub && method === "GET") return ok(200, found.detail);
    if (sub === "ledger" && method === "GET") {
      return ok(200, page(found.ledger, req.query?.cursor as string | undefined, Number(req.query?.limit ?? 25)));
    }
    if (sub === "poll" && method === "POST") return remember(ok(202, { task_id: fid(`poll:${key}`), status: "ready" }));
    if (sub === "control" && method === "POST") {
      if (!isOwner) return fail(403, "FORBIDDEN", "Only owners can pause or stop a mission.");
      const body = req.body as ControlInput;
      if (body.expected_version !== found.detail.version) {
        return fail(409, "CONFLICT", `Mission is at version ${found.detail.version}, not ${body.expected_version}.`);
      }
      const current = allMissions().find((m) => m.id === found.detail.id)!;
      const next: MissionScenario = body.action === "pause" ? "paused" : body.action === "stop" ? "stopped" : "waiting_reply";
      if (body.action === "resume" && current.scenario !== "paused") return fail(409, "CONFLICT", "Mission is not paused.");
      state.overrides.set(found.detail.id, next);
      record(
        found.detail.id,
        {
          id: fid(`control:${key}`),
          created_at: new Date().toISOString(),
          kind: "operator_control",
          status: "accepted",
          reason: `${body.action === "pause" ? "Paused" : body.action === "stop" ? "Stopped" : "Resumed"} by an owner at version ${body.expected_version}.`,
          evidence_ids: [],
          input_refs: { action: body.action, expected_version: body.expected_version },
          model: null,
          policy: { pass: true, checks: [] },
          proposed_action: null,
          actual_action: null,
          resolution: null,
        },
        found.detail.version,
      );
      return remember(ok(202, { task_id: fid(`control:${key}`), status: "ready", campaign_status: next, version: found.detail.version + 1 }));
    }
  }

  const decisionMatch = path.match(/^\/decisions\/([^/]+)\/resolve$/);
  if (decisionMatch && method === "POST") {
    if (!isOwner) return fail(403, "FORBIDDEN", "Only owners can resolve exceptions.");
    const id = decodeURIComponent(decisionMatch[1]);
    const body = req.body as ResolveInput;
    const owner = allMissions()
      .map((m) => ({ m, built: buildMission(m) }))
      .find(({ built }) => built.detail.open_exceptions.some((d) => d.id === id));
    if (!owner) return fail(404, "NOT_FOUND", "No open exception with this id.");
    const convVersion = owner.built.detail.conversation?.version ?? null;
    if (body.expected_conversation_version !== convVersion) {
      return fail(409, "CONFLICT", "The conversation moved on since this exception loaded.");
    }
    if (body.resolution_type === "reauthorize_complete" && workspace.connection?.status !== "connected") {
      return fail(422, "DOMAIN_INVALID", "Google still reports reauth_required. Reconnect in Setup first.");
    }
    const next: MissionScenario =
      body.resolution_type === "stop"
        ? "stopped"
        : body.resolution_type === "clarify_time"
          ? "waiting_slot_acceptance"
          : body.resolution_type === "reauthorize_complete"
            ? "waiting_reply"
            : "drafting";
    state.overrides.set(owner.m.id, next);
    const resolved: DecisionView = {
      ...owner.built.detail.open_exceptions.find((d) => d.id === id)!,
      status: "resolved",
      resolution: { type: body.resolution_type, note: body.note, value: body.value, resolved_at: new Date().toISOString() },
    };
    record(owner.m.id, resolved, owner.built.detail.version);
    return remember(ok(202, { decision: resolved, task_id: fid(`resolve:${key}`) }));
  }

  return fail(404, "NOT_FOUND", `No fixture route for ${method} ${path}.`);
}

export function createFixtureTransport(): Transport {
  return {
    kind: "FIXTURE",
    async send(request) {
      await delay();
      if (state.scenario !== getGlobalScenario()) state = initialState();
      return route(request);
    },
  };
}