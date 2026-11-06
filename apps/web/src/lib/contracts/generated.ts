/* Generated from …/ContextCon-backend/contracts/schemas by scripts/gen-contracts.mjs. Do not edit; run `pnpm contracts:gen`. */

export type ActionId = string;
export type AttendeeAcceptance = "not_verified";
export type CalendarId = string;
export type End = string;
export type EventId = string;
export type HtmlLink = string | null;
export type Mode = "simulation";
export type Start = string;
export type Timezone = string;
export type VerifiedAt = string;
export type Attendees = string[];
export type BookingFingerprint = string | null;
export type CalendarId1 = string;
export type End1 = string;
export type EventId1 = string;
/**
 * Provenance shown in UI, logs and video. Only LIVE counts toward P0 acceptance.
 *
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ExecutionLabel".
 */
export type ExecutionLabel = "LIVE" | "CACHED" | "FIXTURE" | "SIMULATED_BUYER";
export type HtmlLink1 = string | null;
export type ReadAt = string;
export type Start1 = string;
export type Status = string;
export type Timezone1 = string;
export type Found = boolean;
export type ActionId1 = string;
/**
 * @minItems 1
 * @maxItems 2
 */
export type Attendees1 = [string] | [string, string];
export type BookingFingerprint1 = string;
export type CalendarId2 = string;
export type Description = string;
export type End2 = string;
export type EventId2 = string;
export type Start2 = string;
export type Summary = string;
export type Timezone2 = string;
export type MaxConversations = number;
export type MaxDiscovered = number;
export type MaxEnriched = number;
export type MaxModelCalls = number;
export type MaxOutboundMessages = number;
export type MaxReplyTurns = number;
export type MaxResearchCalls = number;
export type MaxRuntimeSeconds = number;
export type NoReplyFollowups = number;
export type BuyerTestEmail = string;
export type ConfigVersion = number;
export type Mode1 = "simulation";
export type ProfileVersion = number;
export type RequestText = string;
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "CampaignState".
 */
export type CampaignState =
  "draft" | "running" | "waiting_reply" | "completed" | "no_match" | "needs_human" | "paused" | "stopped" | "failed";
export type Amount = number | string;
export type Currency = string;
export type PricingSource = string;
export type CalendarAttempts = number;
export type ModelCalls = number;
export type OutboundAttempts = number;
export type ResearchCalls = number;
export type TokensIn = number;
export type TokensOut = number;
export type ConfigVersion1 = number;
export type CreatedAt = string;
export type Id = string;
export type LastDecisionId = string | null;
export type Mode2 = "simulation";
export type ProfileVersion1 = number;
export type RequestText1 = string;
export type Stage = string;
export type TaskId = string;
export type UpdatedAt = string;
export type Version = number;
export type ConfigVersion2 = number;
export type CreatedAt1 = string;
export type Id1 = string;
export type LastDecisionId1 = string | null;
export type Mode3 = "simulation";
export type ProfileVersion2 = number;
export type RequestText2 = string;
export type Stage1 = string;
export type UpdatedAt1 = string;
export type Version1 = number;
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ConnectionStatus".
 */
export type ConnectionStatus = "pending" | "connected" | "reauth_required" | "revoked";
export type AccountEmail = string | null;
export type CalendarId3 = string | null;
export type ConnectionId = string;
export type GrantedScopes = string[];
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "CampaignControl".
 */
export type CampaignControl = "pause" | "resume" | "stop";
export type ExpectedVersion = number;
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ConversationState".
 */
export type ConversationState =
  | "researching"
  | "qualified"
  | "drafting"
  | "waiting_reply"
  | "evaluating_reply"
  | "offering_slots"
  | "waiting_slot_acceptance"
  | "booking"
  | "booked"
  | "completed"
  | "declined"
  | "suppressed"
  | "needs_human"
  | "send_unknown"
  | "stopped";
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "MessageDirection".
 */
export type MessageDirection = "inbound" | "outbound";
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "MessageStatus".
 */
export type MessageStatus = "planned" | "sent" | "received" | "unknown";
export type BodyText = string;
export type Id2 = string;
export type ProviderMessageId = string | null;
export type ReceivedAt = string | null;
export type SentAt = string | null;
export type Subject = string;
export type End3 = string;
export type FreebusyCheckedAt = string;
export type Id3 = string;
export type Start3 = string;
export type Timezone3 = string;
export type BuyerRoleLabel = "simulated buyer";
export type BuyerTestEmail1 = string;
export type Id4 = string;
export type Messages = MessageView[];
export type OfferedSlots = Slot[];
export type ProviderThreadId = string | null;
export type Version2 = number;
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ActionState".
 */
export type ActionState = "prepared" | "executing" | "succeeded" | "failed" | "unknown" | "cancelled";
export type ActionId2 = string;
export type ProviderRef = string | null;
export type Deployment = string;
export type ModelVersion = string | null;
export type PromptVersion = string;
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "DecisionStatus".
 */
export type DecisionStatus = "accepted" | "rejected" | "blocked" | "resolved";
export type Name = string;
export type Pass = boolean;
export type Reason = string;
export type Checks = PolicyCheck[];
export type Pass1 = boolean;
export type CreatedAt2 = string;
export type EvidenceIds = string[];
export type Id5 = string;
export type Kind = string;
export type ProposedAction = {
  [k: string]: unknown | undefined;
} | null;
export type Reason1 = string;
export type Resolution = {
  [k: string]: unknown | undefined;
} | null;
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ErrorCode".
 */
export type ErrorCode =
  | "VALIDATION_FAILED"
  | "UNAUTHENTICATED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "CONFLICT"
  | "DOMAIN_INVALID"
  | "RECIPIENT_NOT_ALLOWED"
  | "RATE_LIMITED"
  | "DEPENDENCY_UNAVAILABLE"
  | "INTERNAL";
export type Message = string;
export type Retryable = boolean;
export type CorrelationId = string;
export type SchemaVersion = "outcome.v1";
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "EvidenceSourceKind".
 */
export type EvidenceSourceKind =
  "crustdata" | "seller_website" | "operator" | "google_message" | "google_calendar" | "policy";
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "FactStatus".
 */
export type FactStatus = "observed" | "operator_approved" | "hypothesis" | "conflicted";
export type ContentSha256 = string;
export type Excerpt = string;
export type FieldPath = string | null;
export type Id6 = string;
export type ProviderRef1 = string | null;
export type RetrievedAt = string;
export type SourceAsOf = string | null;
export type SourceUrl = string | null;
export type End4 = string;
export type Start4 = string;
export type Busy = BusyRange[];
export type CalendarId4 = string;
export type CheckedAt = string;
export type ErrorReasons = string[];
export type Status1 = "ok" | "error";
export type TimeMax = string;
export type TimeMin = string;
export type ProviderMessageId1 = string;
export type ProviderThreadId1 = string;
export type RfcMessageId = string;
export type SentAt1 = string;
export type AccountEmail1 = string;
export type ConnectionId1 = string;
export type OrganizationId = string;
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "FailurePhase".
 */
export type FailurePhase = "preflight" | "auth" | "request_build" | "dispatch" | "response" | "read_back";
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "GoogleOperation".
 */
export type GoogleOperation =
  | "google.start_oauth"
  | "google.complete_oauth"
  | "gmail.send"
  | "gmail.poll_thread"
  | "gmail.reconcile_send"
  | "calendar.freebusy"
  | "calendar.insert"
  | "calendar.get";
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "Retryability".
 */
export type Retryability = "safe_retry" | "reconcile_first" | "reauthorize" | "never";
/**
 * True only when a documented adapter classifier proves the provider rejected the request before accepting it.
 */
export type ExplicitRejection = boolean;
export type MayHaveApplied = boolean;
export type ProviderStatus = number | null;
export type RedactedDetail = string;
export type MessageId = string;
export type Text = string;
export type BuyerStatedNeeds = BuyerStatedNeed[];
export type CampaignId = string;
export type ConversationId = string;
export type FitEvidenceIds = string[];
export type FitSummary = string;
export type Hypotheses = string[];
export type Mode4 = "simulation";
export type NextSteps = string[];
export type NotificationStatus = "not_requested" | "pending" | "sent" | "failed";
export type OpenQuestions = string[];
export type OwnerEmail = string | null;
export type ProspectId = string;
export type Status2 = "complete";
export type Version3 = 1;
export type ContractVersion = "outcome.v1";
export type Service = "api";
export type Status3 = "alive";
export type Database = "ok" | "error";
export type LastSeenAgeSeconds = number | null;
export type Status4 = "ready" | "not_ready";
export type Worker = "fresh" | "stale" | "missing" | "unknown";
export type EvidenceIds1 = string[];
export type Name1 = string;
export type Reason2 = string;
export type Result = "pass" | "fail" | "unknown";
export type BuyerTestEmail2 = string;
export type IdentityIsSimulated = true;
export type Mode5 = "simulation";
export type CanonicalCompanyRef = string;
export type CanonicalPersonRef = string | null;
export type Domain = string | null;
export type Name2 = string;
export type Criteria = CriterionResult[];
export type EvidenceIds2 = string[];
export type Text1 = string;
export type Facts = ProspectFact[];
export type Fit = "qualified" | "rejected" | "needs_evidence";
export type BasisEvidenceIds = string[];
export type Text2 = string;
export type Hypotheses1 = ProspectHypothesis[];
export type Id7 = string;
export type Name3 = string;
export type Title = string | null;
export type EvidenceIds3 = string[];
export type Status5 = "supported" | "unknown" | "conflicted";
export type ConfigVersion3 = number;
export type CreatedAt3 = string;
export type Evidence = EvidenceView[];
export type Id8 = string;
export type LastDecisionId2 = string | null;
export type Mode6 = "simulation";
export type OpenExceptions = DecisionView[];
export type ProfileVersion3 = number;
export type Prospects = ProspectCase[];
export type RequestText3 = string;
export type Stage2 = string;
export type UpdatedAt2 = string;
export type Version4 = number;
export type ConnectionId2 = string;
export type InitiatorUserId = string;
export type OrganizationId1 = string;
export type Purpose = "seller";
export type ReturnPath = "/setup";
export type AuthorizationUrl = string;
export type ExpiresAt = string;
export type ActionId3 = string;
export type ActionKey = string;
export type BodyText1 = string;
export type FromEmail = string;
export type InReplyTo = string | null;
export type ProviderThreadId2 = string | null;
export type References = string[];
export type RequestHash = string;
export type RfcMessageId1 = string;
export type Subject1 = string;
export type ToEmail = string;
export type CheckedAt1 = string;
export type Status6 = "matched" | "unresolved";
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ResolutionType".
 */
export type ResolutionType = "supply_fact" | "clarify_time" | "confirm_identity" | "reauthorize_complete" | "stop";
export type EvidenceIds4 = string[];
export type ExpectedConversationVersion = number | null;
export type Note = string;
export type BodyText2 = string;
export type FromEmail1 = string;
export type InReplyTo1 = string | null;
export type ProviderMessageId2 = string;
export type ProviderThreadId3 = string;
export type ReceivedAt1 = string;
export type RfcMessageId2 = string | null;
export type Subject2 = string;
export type ToEmails = string[];
export type Messages1 = PolledMessage[];
export type PolledAt = string;
export type ProviderThreadId4 = string;

/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "BookingReceipt".
 */
export interface BookingReceipt {
  action_id: ActionId;
  attendee_acceptance: AttendeeAcceptance;
  calendar_id: CalendarId;
  end: End;
  event_id: EventId;
  html_link: HtmlLink;
  mode: Mode;
  start: Start;
  timezone: Timezone;
  verified_at: VerifiedAt;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "CalendarEventReceipt".
 */
export interface CalendarEventReceipt {
  attendees: Attendees;
  booking_fingerprint: BookingFingerprint;
  calendar_id: CalendarId1;
  end: End1;
  event_id: EventId1;
  execution_label: ExecutionLabel;
  html_link: HtmlLink1;
  read_at: ReadAt;
  start: Start1;
  status: Status;
  timezone: Timezone1;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "CalendarEventLookup".
 */
export interface CalendarEventLookup {
  event: CalendarEventReceipt | null;
  execution_label: ExecutionLabel;
  found: Found;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "CalendarEventRequest".
 */
export interface CalendarEventRequest {
  action_id: ActionId1;
  attendees: Attendees1;
  booking_fingerprint: BookingFingerprint1;
  calendar_id: CalendarId2;
  description: Description;
  end: End2;
  event_id: EventId2;
  start: Start2;
  summary: Summary;
  timezone: Timezone2;
}
/**
 * P0 single-conversation ceilings. Raising a bound needs a reviewed contract and quota change.
 *
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "Limits".
 */
export interface Limits {
  max_conversations: MaxConversations;
  max_discovered: MaxDiscovered;
  max_enriched: MaxEnriched;
  max_model_calls: MaxModelCalls;
  max_outbound_messages: MaxOutboundMessages;
  max_reply_turns: MaxReplyTurns;
  max_research_calls: MaxResearchCalls;
  max_runtime_seconds: MaxRuntimeSeconds;
  no_reply_followups: NoReplyFollowups;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "CampaignCreate".
 */
export interface CampaignCreate {
  buyer_test_email: BuyerTestEmail;
  config_version: ConfigVersion;
  limits: Limits;
  mode: Mode1;
  profile_version: ProfileVersion;
  request_text: RequestText;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "EstimatedCost".
 */
export interface EstimatedCost {
  amount: Amount;
  currency: Currency;
  pricing_source: PricingSource;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "Usage".
 */
export interface Usage {
  calendar_attempts: CalendarAttempts;
  /**
   * Unknown cost is null, never zero.
   */
  estimated_cost?: EstimatedCost | null;
  model_calls: ModelCalls;
  outbound_attempts: OutboundAttempts;
  research_calls: ResearchCalls;
  tokens_in: TokensIn;
  tokens_out: TokensOut;
}
/**
 * 202 response of POST /campaigns: the campaign plus the queued normalize_mission task.
 *
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "CampaignLaunchView".
 */
export interface CampaignLaunchView {
  config_version: ConfigVersion1;
  created_at: CreatedAt;
  id: Id;
  last_decision_id: LastDecisionId;
  mode: Mode2;
  profile_version: ProfileVersion1;
  request_text: RequestText1;
  stage: Stage;
  status: CampaignState;
  task_id: TaskId;
  updated_at: UpdatedAt;
  usage: Usage;
  version: Version;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "CampaignView".
 */
export interface CampaignView {
  config_version: ConfigVersion2;
  created_at: CreatedAt1;
  id: Id1;
  last_decision_id: LastDecisionId1;
  mode: Mode3;
  profile_version: ProfileVersion2;
  request_text: RequestText2;
  stage: Stage1;
  status: CampaignState;
  updated_at: UpdatedAt1;
  usage: Usage;
  version: Version1;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ConnectionSummary".
 */
export interface ConnectionSummary {
  account_email: AccountEmail;
  calendar_id: CalendarId3;
  connection_id: ConnectionId;
  granted_scopes: GrantedScopes;
  status: ConnectionStatus;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ControlInput".
 */
export interface ControlInput {
  action: CampaignControl;
  expected_version: ExpectedVersion;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "MessageView".
 */
export interface MessageView {
  body_text: BodyText;
  direction: MessageDirection;
  id: Id2;
  provider_message_id: ProviderMessageId;
  received_at: ReceivedAt;
  sent_at: SentAt;
  status: MessageStatus;
  subject: Subject;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "Slot".
 */
export interface Slot {
  end: End3;
  freebusy_checked_at: FreebusyCheckedAt;
  id: Id3;
  start: Start3;
  timezone: Timezone3;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ConversationView".
 */
export interface ConversationView {
  booking: BookingReceipt | null;
  buyer_role_label: BuyerRoleLabel;
  buyer_test_email: BuyerTestEmail1;
  id: Id4;
  messages: Messages;
  offered_slots: OfferedSlots;
  provider_thread_id: ProviderThreadId;
  state: ConversationState;
  version: Version2;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ActualAction".
 */
export interface ActualAction {
  action_id: ActionId2;
  provider_ref: ProviderRef;
  state: ActionState;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "DecisionModelMeta".
 */
export interface DecisionModelMeta {
  deployment: Deployment;
  model_version: ModelVersion;
  prompt_version: PromptVersion;
  usage: Usage1;
}
export interface Usage1 {
  [k: string]: unknown | undefined;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "PolicyCheck".
 */
export interface PolicyCheck {
  name: Name;
  pass: Pass;
  reason: Reason;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "PolicyResult".
 */
export interface PolicyResult {
  checks: Checks;
  pass: Pass1;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "DecisionView".
 */
export interface DecisionView {
  actual_action: ActualAction | null;
  created_at: CreatedAt2;
  evidence_ids: EvidenceIds;
  id: Id5;
  input_refs: InputRefs;
  kind: Kind;
  model: DecisionModelMeta | null;
  policy: PolicyResult;
  proposed_action: ProposedAction;
  reason: Reason1;
  resolution: Resolution;
  status: DecisionStatus;
}
export interface InputRefs {
  [k: string]: unknown | undefined;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ErrorBody".
 */
export interface ErrorBody {
  code: ErrorCode;
  details?: Details;
  message: Message;
  retryable: Retryable;
}
export interface Details {
  [k: string]: unknown | undefined;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ErrorEnvelope".
 */
export interface ErrorEnvelope {
  correlation_id: CorrelationId;
  error: ErrorBody;
  schema_version?: SchemaVersion;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "EvidenceView".
 */
export interface EvidenceView {
  content_sha256: ContentSha256;
  excerpt: Excerpt;
  fact_status: FactStatus;
  field_path: FieldPath;
  id: Id6;
  provider_ref: ProviderRef1;
  retrieved_at: RetrievedAt;
  source_as_of: SourceAsOf;
  source_kind: EvidenceSourceKind;
  source_url: SourceUrl;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "BusyRange".
 */
export interface BusyRange {
  end: End4;
  start: Start4;
}
/**
 * An `error` result means unavailable. An `ok` result with no busy ranges is the only free signal.
 *
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "FreeBusyResult".
 */
export interface FreeBusyResult {
  busy: Busy;
  calendar_id: CalendarId4;
  checked_at: CheckedAt;
  error_reasons: ErrorReasons;
  execution_label: ExecutionLabel;
  status: Status1;
  time_max: TimeMax;
  time_min: TimeMin;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "GmailSendReceipt".
 */
export interface GmailSendReceipt {
  execution_label: ExecutionLabel;
  provider_message_id: ProviderMessageId1;
  provider_thread_id: ProviderThreadId1;
  rfc_message_id: RfcMessageId;
  sent_at: SentAt1;
}
/**
 * Server-selected connection. Adapters load and refresh tokens themselves; tokens never cross this boundary.
 *
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "GoogleConnectionRef".
 */
export interface GoogleConnectionRef {
  account_email: AccountEmail1;
  connection_id: ConnectionId1;
  organization_id: OrganizationId;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "GoogleFailure".
 */
export interface GoogleFailure {
  explicit_rejection?: ExplicitRejection;
  may_have_applied: MayHaveApplied;
  operation: GoogleOperation;
  phase: FailurePhase;
  provider_status: ProviderStatus;
  redacted_detail: RedactedDetail;
  retryability: Retryability;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "BuyerStatedNeed".
 */
export interface BuyerStatedNeed {
  message_id: MessageId;
  text: Text;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "Handoff".
 */
export interface Handoff {
  booking: BookingReceipt;
  buyer_stated_needs: BuyerStatedNeeds;
  campaign_id: CampaignId;
  conversation_id: ConversationId;
  fit_evidence_ids: FitEvidenceIds;
  fit_summary: FitSummary;
  hypotheses: Hypotheses;
  mode: Mode4;
  next_steps: NextSteps;
  notification_status: NotificationStatus;
  open_questions: OpenQuestions;
  owner_email: OwnerEmail;
  prospect_id: ProspectId;
  status: Status2;
  version: Version3;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "HealthLive".
 */
export interface HealthLive {
  contract_version: ContractVersion;
  service: Service;
  status: Status3;
}
/**
 * Sanitized readiness summary. Returned as data on 200, and as error.details on 503.
 *
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "HealthReady".
 */
export interface HealthReady {
  database: Database;
  last_seen_age_seconds: LastSeenAgeSeconds;
  status: Status4;
  worker: Worker;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "CriterionResult".
 */
export interface CriterionResult {
  evidence_ids: EvidenceIds1;
  name: Name1;
  reason: Reason2;
  result: Result;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "Delivery".
 */
export interface Delivery {
  buyer_test_email: BuyerTestEmail2;
  identity_is_simulated: IdentityIsSimulated;
  mode: Mode5;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ProspectCase".
 */
export interface ProspectCase {
  canonical_company_ref: CanonicalCompanyRef;
  canonical_person_ref: CanonicalPersonRef;
  company: ProspectCompany;
  criteria: Criteria;
  delivery: Delivery;
  facts: Facts;
  fit: Fit;
  hypotheses: Hypotheses1;
  id: Id7;
  person: ProspectPerson | null;
  relationship: ProspectRelationship;
  draft?: { subject: string; body_text: string } | null;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ProspectCompany".
 */
export interface ProspectCompany {
  domain: Domain;
  name: Name2;
  location?: string | null;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ProspectFact".
 */
export interface ProspectFact {
  evidence_ids: EvidenceIds2;
  text: Text1;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ProspectHypothesis".
 */
export interface ProspectHypothesis {
  basis_evidence_ids: BasisEvidenceIds;
  text: Text2;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ProspectPerson".
 */
export interface ProspectPerson {
  name: Name3;
  title: Title;
  found_email?: string | null;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ProspectRelationship".
 */
export interface ProspectRelationship {
  evidence_ids: EvidenceIds3;
  status: Status5;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "MissionDetail".
 */
export interface MissionDetail {
  config_version: ConfigVersion3;
  conversation: ConversationView | null;
  created_at: CreatedAt3;
  evidence: Evidence;
  handoff: Handoff | null;
  id: Id8;
  last_decision_id: LastDecisionId2;
  mode: Mode6;
  open_exceptions: OpenExceptions;
  profile_version: ProfileVersion3;
  prospects: Prospects;
  request_text: RequestText3;
  stage: Stage2;
  status: CampaignState;
  updated_at: UpdatedAt2;
  usage: Usage;
  version: Version4;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "OAuthStart".
 */
export interface OAuthStart {
  connection_id: ConnectionId2;
  initiator_user_id: InitiatorUserId;
  organization_id: OrganizationId1;
  purpose: Purpose;
  return_path: ReturnPath;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "OAuthStartResult".
 */
export interface OAuthStartResult {
  authorization_url: AuthorizationUrl;
  expires_at: ExpiresAt;
}
/**
 * Immutable plain-text message built by the server. Exactly one recipient; no Cc/Bcc/Reply-To.
 *
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "OutboundEmail".
 */
export interface OutboundEmail {
  action_id: ActionId3;
  action_key: ActionKey;
  body_text: BodyText1;
  from_email: FromEmail;
  in_reply_to: InReplyTo;
  provider_thread_id: ProviderThreadId2;
  references: References;
  request_hash: RequestHash;
  rfc_message_id: RfcMessageId1;
  subject: Subject1;
  to_email: ToEmail;
}
/**
 * `unresolved` is inconclusive (indexing lag), never proof that nothing was sent.
 *
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ReconcileResult".
 */
export interface ReconcileResult {
  checked_at: CheckedAt1;
  execution_label: ExecutionLabel;
  receipt: GmailSendReceipt | null;
  status: Status6;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ResolveInput".
 */
export interface ResolveInput {
  evidence_ids: EvidenceIds4;
  expected_conversation_version: ExpectedConversationVersion;
  note: Note;
  resolution_type: ResolutionType;
  value: Value;
}
export interface Value {
  [k: string]: unknown | undefined;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "PolledMessage".
 */
export interface PolledMessage {
  body_text: BodyText2;
  from_email: FromEmail1;
  in_reply_to: InReplyTo1;
  provider_message_id: ProviderMessageId2;
  provider_thread_id: ProviderThreadId3;
  received_at: ReceivedAt1;
  rfc_message_id: RfcMessageId2;
  subject: Subject2;
  to_emails: ToEmails;
}
/**
 * This interface was referenced by `OutcomeContracts`'s JSON-Schema
 * via the `definition` "ThreadPoll".
 */
export interface ThreadPoll {
  execution_label: ExecutionLabel;
  messages: Messages1;
  polled_at: PolledAt;
  provider_thread_id: ProviderThreadId4;
}
