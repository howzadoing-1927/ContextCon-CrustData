export type * from "./generated";

import type {
  CampaignView,
  ConnectionSummary,
  DecisionView,
  EvidenceView,
  HealthReady,
  Limits,
} from "./generated";

export const SCHEMA_VERSION = "outcome.v1";

export interface SuccessEnvelope<T> {
  schema_version: typeof SCHEMA_VERSION;
  data: T;
  correlation_id: string;
}

export interface ListPage<T> {
  items: T[];
  next_cursor: string | null;
}

export type CampaignList = ListPage<CampaignView>;
export type LedgerPage = ListPage<DecisionView>;

export const REQUIRED_GOOGLE_SCOPES = [
  "https://www.googleapis.com/auth/gmail.readonly",
  "https://www.googleapis.com/auth/gmail.send",
  "https://www.googleapis.com/auth/calendar.events",
  "https://www.googleapis.com/auth/calendar.freebusy",
] as const;

export const MAX_PEOPLE = 25;
export const DEFAULT_PEOPLE = 10;
export const MAX_BUYER_INBOXES = 5;

/** Mirrors `limits_for` in services/core/contracts/requests.py. */
export function limitsFor(people: number): Limits {
  const n = Math.max(1, Math.min(MAX_PEOPLE, Math.floor(people) || 1));
  return {
    max_discovered: Math.min(50, Math.max(10, 2 * n)),
    max_enriched: n,
    max_conversations: n,
    max_outbound_messages: 6,
    max_model_calls: Math.min(150, 5 * n + 10),
    max_research_calls: Math.min(80, 3 * n + 5),
    max_runtime_seconds: Math.min(1800, 60 * n + 300),
    max_reply_turns: 4,
    no_reply_followups: 0,
  };
}

export const DEFAULT_LIMITS: Limits = limitsFor(DEFAULT_PEOPLE);

/** Contract ceilings for each budget. */
export const LIMIT_CEILINGS: Limits = {
  max_discovered: 50,
  max_enriched: MAX_PEOPLE,
  max_conversations: MAX_PEOPLE,
  max_outbound_messages: 6,
  max_model_calls: 150,
  max_research_calls: 80,
  max_runtime_seconds: 1800,
  max_reply_turns: 4,
  no_reply_followups: 0,
};

/*
 * Provisional shapes. D1 has not exported schemas for these routes yet
 * (`/workspace*`, `/google/status`, membership listing). They follow doc 03's prose
 * and are listed as contract requests in docs/dev-notes/D2-F3.md. Replace with
 * generated types once `contracts/schemas` contains them.
 */

export type MembershipRole = "owner" | "member";

export interface MembershipView {
  organization_id: string;
  organization_name: string;
  role: MembershipRole;
}

export interface ApprovedFact {
  id: string;
  text: string;
  evidence_ids: string[];
  authority: "operator_approved";
  approved: true;
}

export interface ProposedFact {
  id: string;
  text: string;
  evidence_ids: string[];
}

export interface FAQ {
  question: string;
  answer: string;
  fact_ids: string[];
}

export interface SourceView {
  id: string;
  kind: "website" | "pasted_text";
  label: string;
  status: "ingesting" | "ready" | "failed";
  retrieved_at: string | null;
  evidence_ids: string[];
  error: string | null;
}

export interface ConsentedRecipient {
  email: string;
  role: "buyer_test" | "owner_test";
  consent_record: string;
  consented_at: string;
}

export interface WorkingHours {
  timezone: string;
  weekdays: number[];
  start: string;
  end: string;
}

export interface PolicyView {
  config_version: number;
  simulation: true;
  consented_recipients: ConsentedRecipient[];
  selected_calendar_id: string | null;
  working_hours: WorkingHours;
  duration_minutes: number;
  limits: Limits;
}

export interface OrganizationView {
  id: string;
  name: string;
  website_url: string | null;
  timezone: string;
  profile_version: number;
  approved_at: string | null;
  approved_by: string | null;
  approved_facts: ApprovedFact[];
  proposed_facts: ProposedFact[];
  faq: FAQ[];
  forbidden_promises: string[];
  sources: SourceView[];
  /** Evidence records referenced by sources and facts above. */
  evidence: EvidenceView[];
  policy: PolicyView;
  connection: ConnectionSummary | null;
  worker: HealthReady;
  viewer_role: MembershipRole;
  /** Pending contract request (D2-F3 #10): written by the founder brief. */
  seller_brief?: SellerBrief | null;
  /** Pending contract request (D2-F3 #10): prefills new missions. */
  ideal_customer?: IdealCustomer | null;
}

export interface IdealCustomer {
  customer_type: string;
  regions: string[];
  buyer_roles: string[];
  timeline: string | null;
  criteria: string[];
  exclusions: string[];
}

export interface SellerBrief {
  founder_name: string;
  founder_email: string;
  service: string;
  pricing: string | null;
  capacity: string | null;
}

/** A value read from the seller's site; `null` means the page didn't state it. */
export interface ExtractedField<T> {
  value: T | null;
  page: string | null;
}

/** Pending contract request (D2-F3 #10): POST /workspace/website-analysis. */
export interface WebsiteAnalysis {
  url: string;
  /** `firecrawl` when the site was actually read; `fixture` for the sample brief. */
  source: "firecrawl" | "fixture";
  pages_read: string[];
  company_name: ExtractedField<string>;
  service: ExtractedField<string>;
  description: ExtractedField<string>;
  pricing: ExtractedField<string>;
  capacity: ExtractedField<string>;
  customer_type: ExtractedField<string>;
  regions: ExtractedField<string[]>;
  buyer_roles: ExtractedField<string[]>;
  timeline: ExtractedField<string>;
  criteria: ExtractedField<string[]>;
  exclusions: ExtractedField<string[]>;
  timezone: ExtractedField<string>;
  proposed_facts: ProposedFact[];
  evidence: EvidenceView[];
}

/** Pending contract request (D2-F3 #10): PUT /workspace/brief. */
export interface BriefSave {
  expected_profile_version: number;
  name: string;
  website_url: string;
  timezone: string;
  seller_brief: SellerBrief;
  ideal_customer: IdealCustomer;
  description: string;
  approved_fact_ids: string[];
  proposed_facts: ProposedFact[];
  evidence: EvidenceView[];
  escalation_topics: string[];
  working_hours: WorkingHours;
  duration_minutes: number;
}

export type SourceInput =
  | { kind: "website"; url: string }
  | { kind: "pasted_text"; title: string; text: string };

export interface ProfileUpdate {
  expected_profile_version: number;
  approval_key: string;
  name: string;
  website_url: string;
  timezone: string;
  approved_facts: ApprovedFact[];
  faq: FAQ[];
  forbidden_promises: string[];
}

export interface PolicyUpdate {
  expected_config_version: number;
  simulation: true;
  consented_recipients: ConsentedRecipient[];
  selected_calendar_id: string;
  working_hours: WorkingHours;
  duration_minutes: number;
  limits: Limits;
}

export interface TaskAccepted {
  task_id: string;
  status: string;
}

export interface GoogleConnectStart {
  authorization_url: string;
  expires_at: string;
}
