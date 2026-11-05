import type { BriefSave, EvidenceView, OrganizationView, WebsiteAnalysis } from "@/lib/contracts";
import { fid, fsha } from "./ids";
import { SELLER_TZ } from "./missions";

export const BRIEF_STORAGE_KEY = "outcome.fixture.brief";

/** Pages the fixture reader "visits", in order. Shown as progress while fields fill. */
export const FIXTURE_PAGES = ["/", "/services", "/about", "/customers"] as const;

function titleFromHost(host: string): string {
  const label = host.replace(/^www\./, "").split(".")[0] ?? host;
  return label
    .split(/[-_]/)
    .filter(Boolean)
    .map((w) => w[0]!.toUpperCase() + w.slice(1))
    .join(" ");
}

export function normalizeWebsite(input: string): string | null {
  const raw = input.trim();
  if (!raw) return null;
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    if (!url.hostname.includes(".")) return null;
    return `https://${url.hostname}/`;
  } catch {
    return null;
  }
}

export function analyzeWebsiteFixture(url: string): WebsiteAnalysis {
  const origin = new URL(url);
  const host = origin.hostname;
  const isDemo = host === "demo-seller.example";
  const name = isDemo ? "Demo Seller Co." : titleFromHost(host);
  const page = (path: string) => new URL(path, origin).toString();
  const now = new Date().toISOString();

  const ev = (key: string, path: string, excerpt: string): EvidenceView => ({
    id: fid(`onboarding:${host}:${key}`),
    content_sha256: fsha(`onboarding:${host}:${key}`),
    source_kind: "seller_website",
    source_url: page(path),
    excerpt,
    retrieved_at: now,
    fact_status: "observed",
    source_as_of: null,
    provider_ref: null,
    field_path: null,
  });

  const home = ev("home", "/", `${name} schedules field-service visits for mid-market fleet operators.`);
  const services = ev("services", "/services", "Standard onboarding is a two-week guided setup with a named contact.");
  const about = ev("about", "/about", "We take on up to 12 new operators a quarter so every rollout gets a named lead.");
  const customers = ev("customers", "/customers", isDemo ? "Trusted by regional fleets across the UK and Ireland." : "Trusted by regional fleet operators.");

  return {
    url: page("/"),
    pages_read: FIXTURE_PAGES.map(page),
    company_name: { value: name, page: page("/") },
    service: { value: "Field-service scheduling", page: page("/services") },
    description: { value: home.excerpt, page: page("/") },
    pricing: { value: null, page: null },
    capacity: { value: "Up to 12 new operators a quarter", page: page("/about") },
    customer_type: { value: "Mid-market fleet operators", page: page("/") },
    regions: isDemo ? { value: ["United Kingdom", "Ireland"], page: page("/customers") } : { value: null, page: null },
    buyer_roles: { value: ["Head of Operations", "Fleet Manager"], page: page("/customers") },
    timeline: { value: null, page: null },
    criteria: { value: ["Runs 50 or more field vehicles", "Schedules visits by hand or in spreadsheets"], page: page("/customers") },
    exclusions: { value: null, page: null },
    timezone: isDemo ? { value: SELLER_TZ, page: page("/about") } : { value: null, page: null },
    proposed_facts: [
      { id: `brief-onboarding-${host}`, text: services.excerpt, evidence_ids: [services.id] },
      { id: `brief-capacity-${host}`, text: about.excerpt, evidence_ids: [about.id] },
      { id: `brief-customers-${host}`, text: customers.excerpt, evidence_ids: [customers.id] },
    ],
    evidence: [home, services, about, customers],
  };
}

export function applyBrief(workspace: OrganizationView, body: BriefSave, sourceId: string): OrganizationView {
  const approvedIds = new Set(body.approved_fact_ids);
  const homeEvidence = body.evidence.find((e) => e.source_url === body.website_url) ?? body.evidence[0];
  return {
    ...workspace,
    name: body.name,
    website_url: body.website_url,
    timezone: body.timezone,
    profile_version: workspace.profile_version + 1,
    approved_at: new Date().toISOString(),
    approved_by: body.seller_brief.founder_email,
    approved_facts: [
      {
        id: "brief-description",
        text: body.description,
        evidence_ids: homeEvidence ? [homeEvidence.id] : [],
        authority: "operator_approved",
        approved: true,
      },
      ...body.proposed_facts
        .filter((f) => approvedIds.has(f.id))
        .map((f) => ({ ...f, authority: "operator_approved" as const, approved: true as const })),
    ],
    proposed_facts: body.proposed_facts.filter((f) => !approvedIds.has(f.id)),
    faq: [],
    forbidden_promises: body.escalation_topics,
    sources: [
      {
        id: sourceId,
        kind: "website",
        label: body.website_url,
        status: "ready",
        retrieved_at: new Date().toISOString(),
        evidence_ids: body.evidence.map((e) => e.id),
        error: null,
      },
    ],
    evidence: body.evidence,
    policy: { ...workspace.policy, working_hours: body.working_hours, duration_minutes: body.duration_minutes },
    seller_brief: body.seller_brief,
    ideal_customer: body.ideal_customer,
  };
}

export function loadSavedBrief(): OrganizationView | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(BRIEF_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as OrganizationView) : null;
  } catch {
    return null;
  }
}

export function storeBrief(workspace: OrganizationView) {
  window.localStorage.setItem(BRIEF_STORAGE_KEY, JSON.stringify(workspace));
}
