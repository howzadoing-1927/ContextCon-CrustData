import type {
  ApprovedFact,
  BriefSave,
  ConnectionSummary,
  EvidenceView,
  HealthReady,
  IdealCustomer,
  Limits,
  OrganizationView,
  SellerBrief,
  SourceView,
  WorkingHours,
} from "@/lib/contracts";
import { DEFAULT_LIMITS, SCHEMA_VERSION } from "@/lib/contracts";
import { BRIEF_STORAGE_KEY } from "@/lib/fixtures/onboarding";
import { createHttpTransport, type Transport, type TransportRequest, type TransportResponse } from "./transport";

/** Shape returned by the Outcome API for GET /workspace. */
interface BackendWorkspace {
  id: string;
  name: string;
  website_url: string | null;
  timezone: string;
  role: "owner" | "member";
  profile_version: number;
  approved_at: string | null;
  profile: { approved_facts: ApprovedFact[]; faq: OrganizationView["faq"]; forbidden_promises: string[] } | null;
  config_version: number;
  policy: {
    simulation: boolean;
    consented_recipients: OrganizationView["policy"]["consented_recipients"];
    selected_calendar_id: string | null;
    working_hours: WorkingHours | null;
    duration_minutes: number | null;
    limits: Limits | null;
  };
  connections: { purpose: "seller" | "buyer_test"; status: ConnectionSummary["status"]; account_email: string | null; granted_scopes: string[]; calendar_id: string | null }[];
  worker: HealthReady;
}

/** What the brief adds on top of the API workspace; kept in the browser until the API stores it. */
interface SavedBrief {
  organization_id: string;
  seller_brief: SellerBrief;
  ideal_customer: IdealCustomer;
  sources: SourceView[];
  evidence: EvidenceView[];
}

const SHORT = 1000;
const clip = (text: string) => (text.length > SHORT ? `${text.slice(0, SHORT - 1)}…` : text);

function loadBrief(organizationId: string): SavedBrief | null {
  try {
    const saved = JSON.parse(window.localStorage.getItem(BRIEF_STORAGE_KEY) ?? "null") as SavedBrief | null;
    return saved?.organization_id === organizationId ? saved : null;
  } catch {
    return null;
  }
}

function toWebWorkspace(b: BackendWorkspace): OrganizationView {
  const saved = loadBrief(b.id);
  const seller = b.connections.find((c) => c.purpose === "seller");
  return {
    id: b.id,
    name: b.name,
    website_url: b.website_url,
    timezone: b.timezone,
    profile_version: b.profile_version,
    approved_at: b.approved_at,
    approved_by: null,
    approved_facts: b.profile?.approved_facts ?? [],
    proposed_facts: [],
    faq: b.profile?.faq ?? [],
    forbidden_promises: b.profile?.forbidden_promises ?? [],
    sources: saved?.sources ?? [],
    evidence: saved?.evidence ?? [],
    policy: {
      config_version: b.config_version,
      simulation: true,
      consented_recipients: b.policy.consented_recipients,
      selected_calendar_id: b.policy.selected_calendar_id,
      working_hours: b.policy.working_hours ?? { timezone: b.timezone, weekdays: [1, 2, 3, 4, 5], start: "09:00", end: "17:00" },
      duration_minutes: b.policy.duration_minutes ?? 15,
      limits: b.policy.limits ?? DEFAULT_LIMITS,
    },
    connection: seller
      ? {
          connection_id: "seller",
          status: seller.status,
          account_email: seller.account_email,
          granted_scopes: seller.granted_scopes,
          calendar_id: seller.calendar_id,
        }
      : null,
    worker: b.worker,
    viewer_role: b.role,
    seller_brief: saved?.seller_brief ?? null,
    ideal_customer: saved?.ideal_customer ?? null,
  };
}

async function digest(text: string): Promise<string> {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

export function createLiveTransport(baseUrl: string): Transport {
  const http = createHttpTransport(baseUrl);
  const isOk = (r: TransportResponse) => r.status >= 200 && r.status < 300;
  const data = <T>(r: TransportResponse) => (r.body as { data: T }).data;

  async function workspace(headers: Record<string, string>): Promise<TransportResponse> {
    const res = await http.send({ method: "GET", path: "/workspace", headers });
    if (!isOk(res)) return res;
    return { status: res.status, body: { ...(res.body as object), data: toWebWorkspace(data<BackendWorkspace>(res)) } };
  }

  /** Founder-confirmed brief: each excerpt becomes workspace evidence, then the approved facts cite those ids. */
  async function saveBrief(body: BriefSave, headers: Record<string, string>): Promise<TransportResponse> {
    const ws = await http.send({ method: "GET", path: "/workspace", headers });
    if (!isOk(ws)) return ws;
    const org = data<BackendWorkspace>(ws);

    const addSource = async (title: string, text: string) => {
      const key = `brief-src-${await digest(`${org.id}|${title}|${text}`)}`;
      const res = await http.send({
        method: "POST",
        path: "/workspace/sources",
        headers: { ...headers, "Idempotency-Key": key },
        body: { kind: "pasted_text", title: clip(title).slice(0, 200), text },
      });
      return res;
    };

    const ids = new Map<string, string>();
    const stored: EvidenceView[] = [];
    for (const ev of body.evidence) {
      const res = await addSource(`Read from ${ev.source_url ?? body.website_url}`, ev.excerpt);
      if (!isOk(res)) return res;
      const created = data<EvidenceView>(res);
      ids.set(ev.id, created.id);
      stored.push({ ...created, source_url: ev.source_url });
    }
    const described = await addSource("Founder-approved description", body.description);
    if (!isOk(described)) return described;
    const descriptionEvidence = data<EvidenceView>(described);
    stored.push(descriptionEvidence);

    const approved = new Set(body.approved_fact_ids);
    const facts: ApprovedFact[] = [
      { id: "F1", text: clip(body.description), evidence_ids: [descriptionEvidence.id], authority: "operator_approved", approved: true },
      ...body.proposed_facts
        .filter((f) => approved.has(f.id))
        .map((f, i) => ({
          id: `F${i + 2}`,
          text: clip(f.text),
          evidence_ids: f.evidence_ids.map((id) => ids.get(id)).filter((id): id is string => Boolean(id)),
          authority: "operator_approved" as const,
          approved: true as const,
        }))
        .filter((f) => f.evidence_ids.length > 0),
    ];
    const approvalKey = `brief-${await digest(JSON.stringify([org.id, org.profile_version, facts, body.name, body.timezone]))}`;
    const profile = await http.send({
      method: "PUT",
      path: "/workspace/profile",
      headers,
      body: {
        expected_profile_version: org.profile_version,
        approval_key: approvalKey,
        name: body.name,
        website_url: body.website_url,
        timezone: body.timezone,
        approved_facts: facts,
        faq: [],
        forbidden_promises: body.escalation_topics.map(clip).slice(0, 50),
      },
    });
    if (!isOk(profile)) return profile;

    const saved: SavedBrief = {
      organization_id: org.id,
      seller_brief: body.seller_brief,
      ideal_customer: body.ideal_customer,
      sources: [
        {
          id: `website-${org.id}`,
          kind: "website",
          label: body.website_url,
          status: "ready",
          retrieved_at: new Date().toISOString(),
          evidence_ids: stored.map((e) => e.id),
          error: null,
        },
      ],
      evidence: stored,
    };
    window.localStorage.setItem(BRIEF_STORAGE_KEY, JSON.stringify(saved));
    return workspace(headers);
  }

  return {
    kind: "LIVE",
    async send(request: TransportRequest) {
      const { method, path, headers } = request;
      if (method === "GET" && path === "/workspace") return workspace(headers);
      if (method === "PUT" && path === "/workspace/brief") return saveBrief(request.body as BriefSave, headers);
      if (method === "PUT" && path === "/workspace/policy") {
        const res = await http.send(request);
        if (!isOk(res)) return res;
        return { status: res.status, body: { ...(res.body as object), data: toWebWorkspace(data<BackendWorkspace>(res)) } };
      }
      if (method === "POST" && path === "/google/connect") {
        return http.send({ method: "POST", path: "/google/oauth/start", headers, body: { return_path: "/setup" } });
      }
      if (method === "GET" && path === "/google/status") {
        const res = await workspace(headers);
        if (!isOk(res)) return res;
        return { status: 200, body: { schema_version: SCHEMA_VERSION, data: data<OrganizationView>(res).connection, correlation_id: "" } };
      }
      return http.send(request);
    },
  };
}
