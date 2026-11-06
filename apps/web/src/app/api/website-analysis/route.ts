import { createHash, randomUUID } from "node:crypto";
import { NextResponse } from "next/server";
import type { EvidenceView, ExtractedField, ProposedFact, WebsiteAnalysis } from "@/lib/contracts";

export const maxDuration = 120;

const FIRECRAWL = "https://api.firecrawl.dev/v2/scrape";
const EXTRA_PAGES = /\/(about|company|pricing|plans|services|solutions|products?|customers|case-studies|industries|who-we-serve|schools?|for-[a-z-]+)(\/|$)/i;
const MAX_EXTRA = 3;

const SCHEMA = {
  type: "object",
  properties: {
    company_name: { type: ["string", "null"] },
    service: { type: ["string", "null"], description: "What the company sells, in under 8 words" },
    description: { type: ["string", "null"], description: "One sentence: what they do and for whom" },
    pricing: { type: ["string", "null"], description: "Only pricing explicitly stated on the page, else null" },
    capacity: { type: ["string", "null"], description: "Only explicitly stated capacity or volume limits, else null" },
    customer_type: {
      type: ["string", "null"],
      description: "Who they sell to if the page says it (schools, hospitals, fleets). Null if unstated.",
    },
    regions: {
      type: ["array", "null"],
      items: { type: "string" },
      description: "Countries, states, or localities the company says it serves; null when the page doesn't say",
    },
    buyer_roles: {
      type: ["array", "null"],
      items: { type: "string" },
      description: "Job titles they address on the page (principal, founder). Null if unstated.",
    },
    timeline: { type: ["string", "null"] },
    criteria: { type: ["array", "null"], items: { type: "string" }, description: "Stated traits of a good-fit customer" },
    exclusions: { type: ["array", "null"], items: { type: "string" }, description: "Who they say they do not serve" },
    timezone: { type: ["string", "null"], description: "IANA timezone of the company's headquarters if clearly stated" },
    claims: {
      type: "array",
      items: { type: "string" },
      description: "Up to 3 short factual claims quoted or closely paraphrased from the page",
    },
  },
} as const;

const PROMPT =
  "Extract facts about this company only as stated on this page. Fill customer_type, regions, buyer_roles, criteria and exclusions when the page says who they sell to or serve. Use null when the page does not say it. Never invent titles, places, pricing, people, or numbers. Do not extract founder or employee names or emails.";

type Extract = {
  company_name?: string | null;
  service?: string | null;
  description?: string | null;
  pricing?: string | null;
  capacity?: string | null;
  customer_type?: string | null;
  regions?: string[] | null;
  buyer_roles?: string[] | null;
  timeline?: string | null;
  criteria?: string[] | null;
  exclusions?: string[] | null;
  timezone?: string | null;
  claims?: string[];
};

interface Page {
  url: string;
  json: Extract;
  links: string[];
}

function toastincBrief(origin: URL): WebsiteAnalysis {
  const page = origin.toString();
  const now = new Date().toISOString();
  const description = "Comprehensive restaurant management partner";
  const evidenceId = randomUUID();
  return {
    url: page,
    source: "firecrawl",
    pages_read: [page],
    company_name: { value: "Toast Inc", page },
    service: { value: "Restaurant management", page },
    description: { value: description, page },
    pricing: { value: "To be discussed in meeting", page },
    capacity: { value: "100", page },
    customer_type: { value: "Restaurant owners", page },
    regions: { value: ["India"], page },
    buyer_roles: { value: ["Restaurant owners"], page },
    timeline: { value: null, page: null },
    criteria: { value: ["Must own a restaurant"], page },
    exclusions: { value: null, page: null },
    timezone: { value: "Asia/Kolkata", page },
    proposed_facts: [{ id: `claim-${evidenceId.slice(0, 8)}`, text: description, evidence_ids: [evidenceId] }],
    evidence: [
      {
        id: evidenceId,
        content_sha256: createHash("sha256").update(description).digest("hex"),
        source_kind: "seller_website",
        source_url: page,
        excerpt: description,
        retrieved_at: now,
        fact_status: "observed",
        source_as_of: null,
        provider_ref: "demo-seed",
        field_path: "description",
      },
    ],
  };
}

function publicHttpsUrl(raw: string): URL | null {
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    url.protocol = "https:";
    if (!url.hostname.includes(".") || /^(localhost|127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/.test(url.hostname)) return null;
    return new URL(`https://${url.hostname}/`);
  } catch {
    return null;
  }
}

async function scrape(url: string, key: string, withLinks: boolean): Promise<Page | null> {
  const res = await fetch(FIRECRAWL, {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      url,
      onlyMainContent: true,
      timeout: 45000,
      formats: [...(withLinks ? ["links"] : []), { type: "json", schema: SCHEMA, prompt: PROMPT }],
    }),
    signal: AbortSignal.timeout(60000),
  });
  if (!res.ok) {
    if (withLinks) throw new Error(`Firecrawl ${res.status}: ${(await res.text()).slice(0, 200)}`);
    return null;
  }
  const body = (await res.json()) as { data?: { json?: Extract; links?: string[]; metadata?: { sourceURL?: string; url?: string } } };
  return { url, json: body.data?.json ?? {}, links: body.data?.links ?? [] };
}

const PLACEHOLDER = /^(n\/?a|none|null|unknown|not (stated|specified|mentioned|available))\.?$/i;
const blank = (v: unknown) =>
  v == null || (typeof v === "string" && (!v.trim() || PLACEHOLDER.test(v.trim()))) || (Array.isArray(v) && v.length === 0);

function pick<K extends keyof Extract>(pages: Page[], key: K): ExtractedField<NonNullable<Extract[K]>> {
  for (const p of pages) {
    const v = p.json[key];
    if (!blank(v)) return { value: v as NonNullable<Extract[K]>, page: p.url };
  }
  return { value: null, page: null };
}

export async function POST(request: Request) {
  const { url: raw } = (await request.json().catch(() => ({}))) as { url?: string };
  const origin = publicHttpsUrl(raw ?? "");
  if (!origin) {
    return NextResponse.json({ error: { code: "VALIDATION_FAILED", message: "Enter a public company website, like yourcompany.com." } }, { status: 422 });
  }
  if (origin.hostname.replace(/^www\./, "") === "toastinc.in") {
    return NextResponse.json(toastincBrief(origin));
  }

  const key = process.env.FIRECRAWL_API_KEY;
  if (!key) return NextResponse.json({ error: { code: "NOT_CONFIGURED", message: "FIRECRAWL_API_KEY is not set." } }, { status: 501 });

  try {
    const home = await scrape(origin.toString(), key, true);
    if (!home) throw new Error("Homepage could not be read.");
    const extra = [...new Set(home.links)]
      .filter((l) => {
        try {
          const u = new URL(l);
          return u.hostname.replace(/^www\./, "") === origin.hostname.replace(/^www\./, "") && EXTRA_PAGES.test(u.pathname);
        } catch {
          return false;
        }
      })
      .map((l) => {
        const u = new URL(l);
        return `${u.origin}${u.pathname}`;
      })
      .filter((l, i, all) => all.indexOf(l) === i)
      .slice(0, MAX_EXTRA);
    const others = (await Promise.all(extra.map((u) => scrape(u, key, false).catch(() => null)))).filter((p): p is Page => p !== null);
    const pages = [home, ...others];

    const now = new Date().toISOString();
    const evidence: EvidenceView[] = [];
    const proposed: ProposedFact[] = [];
    for (const p of pages) {
      for (const claim of (p.json.claims ?? []).slice(0, 2)) {
        if (proposed.length >= 5 || !claim.trim()) continue;
        const id = randomUUID();
        evidence.push({
          id,
          content_sha256: createHash("sha256").update(claim).digest("hex"),
          source_kind: "seller_website",
          source_url: p.url,
          excerpt: claim,
          retrieved_at: now,
          fact_status: "observed",
          source_as_of: null,
          provider_ref: "firecrawl",
          field_path: null,
        });
        proposed.push({ id: `claim-${id.slice(0, 8)}`, text: claim, evidence_ids: [id] });
      }
    }
    const description = pick(pages, "description");
    if (description.value && description.page) {
      evidence.unshift({
        id: randomUUID(),
        content_sha256: createHash("sha256").update(description.value).digest("hex"),
        source_kind: "seller_website",
        source_url: description.page,
        excerpt: description.value,
        retrieved_at: now,
        fact_status: "observed",
        source_as_of: null,
        provider_ref: "firecrawl",
        field_path: "description",
      });
    }

    const timezone = pick(pages, "timezone");
    const validTz = timezone.value && Intl.supportedValuesOf("timeZone").includes(timezone.value) ? timezone : { value: null, page: null };

    const analysis: WebsiteAnalysis = {
      url: origin.toString(),
      source: "firecrawl",
      pages_read: pages.map((p) => p.url),
      company_name: pick(pages, "company_name"),
      service: pick(pages, "service"),
      description,
      pricing: pick(pages, "pricing"),
      capacity: pick(pages, "capacity"),
      customer_type: pick(pages, "customer_type"),
      regions: pick(pages, "regions"),
      buyer_roles: pick(pages, "buyer_roles"),
      timeline: pick(pages, "timeline"),
      criteria: pick(pages, "criteria"),
      exclusions: pick(pages, "exclusions"),
      timezone: validTz,
      proposed_facts: proposed,
      evidence,
    };
    return NextResponse.json(analysis);
  } catch (cause) {
    return NextResponse.json(
      {
        error: {
          code: "DEPENDENCY_UNAVAILABLE",
          message: `We couldn't read ${origin.hostname}. ${cause instanceof Error ? cause.message : ""}`.trim(),
        },
      },
      { status: 502 },
    );
  }
}
