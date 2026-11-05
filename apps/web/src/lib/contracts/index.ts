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

export const DEFAULT_LIMITS: Limits = {
  max_discovered: 10,
  max_enriched: 3,
  max_conversations: 1,
  max_outbound_messages: 6,
  max_model_calls: 20,
  max_research_calls: 10,
  max_runtime_seconds: 600,
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
