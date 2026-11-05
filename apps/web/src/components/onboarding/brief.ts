import type { BriefSave, WebsiteAnalysis } from "@/lib/contracts";

export interface BriefDraft {
  company_name: string;
  website_url: string;
  founder_name: string;
  founder_email: string;
  service: string;
  pricing: string;
  description: string;
  capacity: string;
  customer_type: string;
  regions: string;
  buyer_roles: string;
  timeline: string;
  criteria: string;
  exclusions: string;
  duration: number;
  timezone: string;
  weekdays: number[];
  start: string;
  end: string;
  escalation: string;
}

export type BriefKey = Exclude<keyof BriefDraft, "weekdays" | "duration" | "start" | "end">;

/** Where a field's value came from; drives the chip next to its label. */
export type FieldOrigin = { kind: "site"; page: string } | { kind: "founder" } | { kind: "default" } | { kind: "missing" };

const DEFAULT_ESCALATION = ["Discounts or custom pricing", "Contract or legal terms", "Delivery or uptime guarantees"];

const tidy = (parts: string[]) => parts.map((s) => s.trim()).filter(Boolean);
const splitLines = (v: string) => tidy(v.split("\n"));
const splitList = (v: string) => tidy(v.split(/[\n,]/));

const ICP_KEYS: BriefKey[] = ["customer_type", "regions", "buyer_roles", "timeline", "criteria", "exclusions"];

export function draftFromAnalysis(a: WebsiteAnalysis): { draft: BriefDraft; origins: Partial<Record<BriefKey, FieldOrigin>> } {
  const origins: Partial<Record<BriefKey, FieldOrigin>> = {};
  const site = <T>(key: BriefKey, field: { value: T | null; page: string | null }): T | null => {
    const empty = field.value === null || (Array.isArray(field.value) && field.value.length === 0);
    origins[key] = empty || !field.page ? { kind: "missing" } : { kind: "site", page: field.page };
    return empty ? null : field.value;
  };
  const draft: BriefDraft = {
    company_name: site("company_name", a.company_name) ?? "",
    website_url: a.url,
    founder_name: "",
    founder_email: "",
    service: site("service", a.service) ?? "",
    pricing: site("pricing", a.pricing) ?? "",
    description: site("description", a.description) ?? "",
    capacity: site("capacity", a.capacity) ?? "",
    customer_type: "",
    regions: "",
    buyer_roles: "",
    timeline: "",
    criteria: "",
    exclusions: "",
    duration: 30,
    timezone: site("timezone", a.timezone) ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
    weekdays: [1, 2, 3, 4, 5],
    start: "09:00",
    end: "17:00",
    escalation: DEFAULT_ESCALATION.join("\n"),
  };
  for (const key of ICP_KEYS) origins[key] = { kind: "founder" };
  origins.website_url = { kind: "site", page: a.url };
  origins.founder_name = { kind: "founder" };
  origins.founder_email = { kind: "founder" };
  origins.escalation = { kind: "default" };
  if (origins.timezone?.kind === "missing") origins.timezone = { kind: "default" };
  return { draft, origins };
}

export const REQUIRED: BriefKey[] = [
  "company_name",
  "website_url",
  "founder_name",
  "founder_email",
  "service",
  "description",
  "customer_type",
  "buyer_roles",
  "criteria",
  "timezone",
];

export function briefErrors(d: BriefDraft): Partial<Record<keyof BriefDraft, string>> {
  const errors: Partial<Record<keyof BriefDraft, string>> = {};
  for (const key of REQUIRED) if (!d[key].trim()) errors[key] = "Required";
  if (d.founder_email.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(d.founder_email.trim())) {
    errors.founder_email = "Enter an email address like you@company.com";
  }
  if (d.weekdays.length === 0) errors.weekdays = "Pick at least one working day";
  if (d.start >= d.end) errors.end = "End must be after start";
  return errors;
}

export function toBriefSave(
  d: BriefDraft,
  a: WebsiteAnalysis,
  approvedFactIds: string[],
  expectedProfileVersion: number,
): BriefSave {
  return {
    expected_profile_version: expectedProfileVersion,
    name: d.company_name.trim(),
    website_url: d.website_url.trim(),
    timezone: d.timezone,
    seller_brief: {
      founder_name: d.founder_name.trim(),
      founder_email: d.founder_email.trim(),
      service: d.service.trim(),
      pricing: d.pricing.trim() || null,
      capacity: d.capacity.trim() || null,
    },
    ideal_customer: {
      customer_type: d.customer_type.trim(),
      regions: splitList(d.regions),
      buyer_roles: splitList(d.buyer_roles),
      timeline: d.timeline.trim() || null,
      criteria: splitLines(d.criteria),
      exclusions: splitLines(d.exclusions),
    },
    description: d.description.trim(),
    approved_fact_ids: approvedFactIds,
    proposed_facts: a.proposed_facts,
    evidence: a.evidence,
    escalation_topics: splitLines(d.escalation),
    working_hours: { timezone: d.timezone, weekdays: d.weekdays, start: d.start, end: d.end },
    duration_minutes: d.duration,
  };
}
