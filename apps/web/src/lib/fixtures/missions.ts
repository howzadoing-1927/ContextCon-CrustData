import type {
  BookingReceipt,
  CampaignState,
  CampaignView,
  ConversationState,
  ConversationView,
  DecisionView,
  EvidenceView,
  Handoff,
  MessageView,
  MissionDetail,
  ProspectCase,
  Slot,
  Usage,
} from "@/lib/contracts";
import { at, fhex, fid, fsha } from "./ids";

/*
 * Synthetic mission data for UI development. Every company, person, address and
 * provider id here is invented and rendered under a FIXTURE label. None of it is
 * research output or provider receipts.
 */

export const BUYER_TEST_EMAIL = "buyer-actor@outcome-test.example";
export const OWNER_TEST_EMAIL = "owner@demo-seller.example";
export const SELLER_TZ = "Asia/Kolkata";
export const CALENDAR_ID = "primary";

export type MissionScenario =
  | "draft"
  | "researching"
  | "drafting"
  | "waiting_reply"
  | "evaluating_reply"
  | "offering_slots"
  | "waiting_slot_acceptance"
  | "booking"
  | "booked"
  | "completed"
  | "needs_human_time"
  | "needs_human_reauth"
  | "send_unknown"
  | "no_match"
  | "declined"
  | "suppressed"
  | "paused"
  | "stopped"
  | "failed";

export const HAPPY_PATH: MissionScenario[] = [
  "draft",
  "researching",
  "drafting",
  "waiting_reply",
  "evaluating_reply",
  "offering_slots",
  "waiting_slot_acceptance",
  "booking",
  "booked",
  "completed",
];

/* ---------- Evidence ---------- */

function evidence(
  key: string,
  partial: Omit<EvidenceView, "id" | "content_sha256" | "source_as_of" | "source_url" | "provider_ref" | "field_path"> &
    Partial<Pick<EvidenceView, "source_as_of" | "source_url" | "provider_ref" | "field_path">>,
): EvidenceView {
  return {
    id: fid(`ev:${key}`),
    content_sha256: fsha(key),
    source_as_of: null,
    source_url: null,
    provider_ref: null,
    field_path: null,
    ...partial,
  };
}

const COMPANY_REF = "crust:company:4471902";
const PERSON_REF = "crust:person:88120457";
const REJECTED_REF = "crust:company:3390115";
const REJECTED_REF_2 = "crust:company:5120778";

const EV = {
  seller: evidence("seller", {
    source_kind: "seller_website",
    source_url: "https://demo-seller.example/",
    excerpt: "Demo Seller Co. schedules field-service visits for mid-market fleet operators.",
    retrieved_at: at(-180),
    fact_status: "operator_approved",
  }),
  sellerOnboarding: evidence("seller-onboarding", {
    source_kind: "operator",
    excerpt: "Standard onboarding is a two-week guided setup with a named contact.",
    retrieved_at: at(-170),
    fact_status: "operator_approved",
  }),
  companySearch: evidence("company-search", {
    source_kind: "crustdata",
    provider_ref: `${COMPANY_REF}`,
    field_path: "industries[0]",
    excerpt: "Freight and logistics software",
    retrieved_at: at(1),
    fact_status: "observed",
  }),
  companyHeadcount: evidence("company-headcount", {
    source_kind: "crustdata",
    provider_ref: COMPANY_REF,
    field_path: "headcount.latest",
    excerpt: "412",
    retrieved_at: at(1),
    source_as_of: "2026-10-01T00:00:00Z",
    fact_status: "observed",
  }),
  companyGeo: evidence("company-geo", {
    source_kind: "crustdata",
    provider_ref: COMPANY_REF,
    field_path: "hq.country",
    excerpt: "India",
    retrieved_at: at(1),
    fact_status: "observed",
  }),
  personTitle: evidence("person-title", {
    source_kind: "crustdata",
    provider_ref: PERSON_REF,
    field_path: "current_employers[0].title",
    excerpt: "Vice President, Sales",
    retrieved_at: at(2),
    source_as_of: "2026-09-14T00:00:00Z",
    fact_status: "observed",
  }),
  relationship: evidence("relationship", {
    source_kind: "crustdata",
    provider_ref: PERSON_REF,
    field_path: "current_employers[0].company_id",
    excerpt: "4471902 (current employer, start 2023-04)",
    retrieved_at: at(2),
    fact_status: "observed",
  }),
  hiring: evidence("hiring", {
    source_kind: "crustdata",
    provider_ref: COMPANY_REF,
    field_path: "job_openings[].title",
    excerpt: "3 open roles titled “Field Operations Coordinator”",
    retrieved_at: at(2),
    source_as_of: "2026-11-03T00:00:00Z",
    fact_status: "observed",
  }),
  rejectedHeadcount: evidence("rejected-headcount", {
    source_kind: "crustdata",
    provider_ref: REJECTED_REF,
    field_path: "headcount.latest",
    excerpt: "null (not reported)",
    retrieved_at: at(1),
    fact_status: "observed",
  }),
  rejectedExcluded: evidence("rejected-excluded", {
    source_kind: "crustdata",
    provider_ref: REJECTED_REF_2,
    field_path: "industries[0]",
    excerpt: "Staffing and recruiting",
    retrieved_at: at(1),
    fact_status: "observed",
  }),
  policyRecipient: evidence("policy-recipient", {
    source_kind: "policy",
    excerpt: `Recipient ${BUYER_TEST_EMAIL} matches consented buyer_test (config v1).`,
    retrieved_at: at(4),
    fact_status: "observed",
  }),
  sent1: evidence("sent-1", {
    source_kind: "google_message",
    provider_ref: `gmail:msg:${fhex("m1", 16)}`,
    field_path: "id",
    excerpt: "messages.send returned id and threadId",
    retrieved_at: at(5),
    fact_status: "observed",
  }),
  reply1: evidence("reply-1", {
    source_kind: "google_message",
    provider_ref: `gmail:msg:${fhex("m2", 16)}`,
    field_path: "payload.parts[0].body",
    excerpt: "What does onboarding look like, and how long before our coordinators use it?",
    retrieved_at: at(14),
    fact_status: "observed",
  }),
  freebusy: evidence("freebusy", {
    source_kind: "google_calendar",
    provider_ref: "freebusy:primary",
    field_path: "calendars.primary.busy",
    excerpt: "2 busy ranges between 2026-11-12 09:00 and 2026-11-13 17:00 IST; no calendar errors",
    retrieved_at: at(15),
    fact_status: "observed",
  }),
  reply2: evidence("reply-2", {
    source_kind: "google_message",
    provider_ref: `gmail:msg:${fhex("m4", 16)}`,
    field_path: "payload.parts[0].body",
    excerpt: "Thursday at 3:30 works for me. Please send the invite.",
    retrieved_at: at(26),
    fact_status: "observed",
  }),
  event: evidence("event", {
    source_kind: "google_calendar",
    provider_ref: `gcal:event:${fhex("event", 26)}`,
    field_path: "events.get",
    excerpt: "Read-back matched start, end, calendar, attendees and fingerprint",
    retrieved_at: at(27),
    fact_status: "observed",
  }),
  replyAmbiguous: evidence("reply-ambiguous", {
    source_kind: "google_message",
    provider_ref: `gmail:msg:${fhex("m4-amb", 16)}`,
    field_path: "payload.parts[0].body",
    excerpt: "Thursday or Friday afternoon could work.",
    retrieved_at: at(26),
    fact_status: "observed",
  }),
  replyDecline: evidence("reply-decline", {
    source_kind: "google_message",
    provider_ref: `gmail:msg:${fhex("m2-decline", 16)}`,
    field_path: "payload.parts[0].body",
    excerpt: "Not a priority for us this quarter, thanks.",
    retrieved_at: at(14),
    fact_status: "observed",
  }),
  replyOptOut: evidence("reply-optout", {
    source_kind: "google_message",
    provider_ref: `gmail:msg:${fhex("m2-optout", 16)}`,
    field_path: "payload.parts[0].body",
    excerpt: "Please remove me from your list.",
    retrieved_at: at(14),
    fact_status: "observed",
  }),
};

const ALL_EVIDENCE: EvidenceView[] = Object.values(EV);

/* ---------- Prospects ---------- */

function prospect(fit: ProspectCase["fit"], withPerson: boolean): ProspectCase {
  return {
    id: fid("prospect:halden"),
    canonical_company_ref: COMPANY_REF,
    canonical_person_ref: withPerson ? PERSON_REF : null,
    company: { name: "Halden Freight Systems", domain: "haldenfreight.example" },
    person: withPerson ? { name: "Priya Raman", title: "Vice President, Sales" } : null,
    relationship: withPerson
      ? { status: "supported", evidence_ids: [EV.relationship.id] }
      : { status: "unknown", evidence_ids: [] },
    criteria: [
      {
        name: "Industry is logistics or fleet operations",
        result: "pass",
        evidence_ids: [EV.companySearch.id],
        reason: "Primary industry reported as freight and logistics software.",
      },
      {
        name: "Headcount between 200 and 2,000",
        result: "pass",
        evidence_ids: [EV.companyHeadcount.id],
        reason: "Latest reported headcount is 412 (as of 1 Oct 2026).",
      },
      {
        name: "Headquartered in India",
        result: "pass",
        evidence_ids: [EV.companyGeo.id],
        reason: "HQ country reported as India.",
      },
      {
        name: "Buyer is a sales leader at the company",
        result: withPerson ? "pass" : "unknown",
        evidence_ids: withPerson ? [EV.personTitle.id, EV.relationship.id] : [],
        reason: withPerson
          ? "Current title is VP Sales at this company. The title supports role relevance but does not prove purchasing authority."
          : "Person lookup still running.",
      },
    ],
    fit,
    facts: [
      { text: "Freight and logistics software company, about 412 employees.", evidence_ids: [EV.companySearch.id, EV.companyHeadcount.id] },
      ...(withPerson
        ? [{ text: "Priya Raman is currently VP Sales at Halden Freight Systems.", evidence_ids: [EV.personTitle.id, EV.relationship.id] }]
        : []),
      { text: "Three open roles for field operations coordinators.", evidence_ids: [EV.hiring.id] },
    ],
    hypotheses: [
      {
        text: "Hiring field coordinators may mean scheduling volume is growing.",
        basis_evidence_ids: [EV.hiring.id],
      },
    ],
    delivery: { mode: "simulation", buyer_test_email: BUYER_TEST_EMAIL, identity_is_simulated: true },
  };
}

function rejectedProspect(key: string, name: string, ref: string, reason: string, criterion: string, evId: string): ProspectCase {
  return {
    id: fid(`prospect:${key}`),
    canonical_company_ref: ref,
    canonical_person_ref: null,
    company: { name, domain: null },
    person: null,
    relationship: { status: "unknown", evidence_ids: [] },
    criteria: [{ name: criterion, result: key === "kestrel" ? "unknown" : "fail", evidence_ids: [evId], reason }],
    fit: "rejected",
    facts: [],
    hypotheses: [],
    delivery: { mode: "simulation", buyer_test_email: BUYER_TEST_EMAIL, identity_is_simulated: true },
  };
}

const REJECTED_A = rejectedProspect(
  "kestrel",
  "Kestrel Route Labs",
  REJECTED_REF,
  "Headcount isn't reported. A must-have that is unknown doesn't count as a match.",
  "Headcount between 200 and 2,000",
  EV.rejectedHeadcount.id,
);
const REJECTED_B = rejectedProspect(
  "brightyard",
  "Brightyard Staffing",
  REJECTED_REF_2,
  "Industry is staffing, which the mission excludes.",
  "Industry is logistics or fleet operations",
  EV.rejectedExcluded.id,
);

/* ---------- Messages ---------- */

const SUBJECT = "Scheduling field visits at Halden Freight";

function message(key: string, partial: Omit<MessageView, "id" | "subject"> & { subject?: string }): MessageView {
  return { id: fid(`msg:${key}`), subject: partial.subject ?? SUBJECT, ...partial };
}

const M = {
  initial: message("m1", {
    direction: "outbound",
    status: "sent",
    sent_at: at(5),
    received_at: null,
    provider_message_id: fhex("m1", 16),
    body_text:
      "Hi Priya,\n\nI noticed Halden Freight is hiring three field operations coordinators. Demo Seller Co. schedules field-service visits for mid-market fleet operators, and growing coordinator teams are usually when scheduling gets harder.\n\nWould a 15-minute walkthrough be useful?\n\nBest,\nDemo Seller Co.",
  }),
  question: message("m2", {
    direction: "inbound",
    status: "received",
    sent_at: null,
    received_at: at(14),
    provider_message_id: fhex("m2", 16),
    subject: `Re: ${SUBJECT}`,
    body_text: "Thanks. What does onboarding look like, and how long before our coordinators use it?",
  }),
  offer: message("m3", {
    direction: "outbound",
    status: "sent",
    sent_at: at(16),
    received_at: null,
    provider_message_id: fhex("m3", 16),
    subject: `Re: ${SUBJECT}`,
    body_text:
      "Standard onboarding is a two-week guided setup with a named contact.\n\nI can walk you through it in 15 minutes. Either of these work?\n\n• Thu 12 Nov, 3:30–3:45 PM IST\n• Fri 13 Nov, 11:00–11:15 AM IST",
  }),
  accept: message("m4", {
    direction: "inbound",
    status: "received",
    sent_at: null,
    received_at: at(26),
    provider_message_id: fhex("m4", 16),
    subject: `Re: ${SUBJECT}`,
    body_text: "Thursday at 3:30 works for me. Please send the invite.",
  }),
  confirm: message("m5", {
    direction: "outbound",
    status: "sent",
    sent_at: at(28),
    received_at: null,
    provider_message_id: fhex("m5", 16),
    subject: `Re: ${SUBJECT}`,
    body_text: "Done. You'll get a calendar invitation for Thu 12 Nov, 3:30–3:45 PM IST. Talk then.",
  }),
  ambiguous: message("m4-amb", {
    direction: "inbound",
    status: "received",
    sent_at: null,
    received_at: at(26),
    provider_message_id: fhex("m4-amb", 16),
    subject: `Re: ${SUBJECT}`,
    body_text: "Thursday or Friday afternoon could work.",
  }),
  decline: message("m2-decline", {
    direction: "inbound",
    status: "received",
    sent_at: null,
    received_at: at(14),
    provider_message_id: fhex("m2-decline", 16),
    subject: `Re: ${SUBJECT}`,
    body_text: "Not a priority for us this quarter, thanks.",
  }),
  optOut: message("m2-optout", {
    direction: "inbound",
    status: "received",
    sent_at: null,
    received_at: at(14),
    provider_message_id: fhex("m2-optout", 16),
    subject: `Re: ${SUBJECT}`,
    body_text: "Please remove me from your list.",
  }),
};

/* ---------- Slots and booking ---------- */

const SLOTS: Slot[] = [
  {
    id: "slot-1",
    start: "2026-11-12T10:00:00Z",
    end: "2026-11-12T10:15:00Z",
    timezone: SELLER_TZ,
    freebusy_checked_at: at(15),
  },
  {
    id: "slot-2",
    start: "2026-11-13T05:30:00Z",
    end: "2026-11-13T05:45:00Z",
    timezone: SELLER_TZ,
    freebusy_checked_at: at(15),
  },
];

const BOOKING: BookingReceipt = {
  action_id: fid("action:booking"),
  event_id: (EV.event.provider_ref ?? "").replace("gcal:event:", ""),
  calendar_id: CALENDAR_ID,
  start: SLOTS[0].start,
  end: SLOTS[0].end,
  timezone: SELLER_TZ,
  html_link: "https://calendar.google.com/calendar/event?eid=fixture",
  verified_at: at(27),
  attendee_acceptance: "not_verified",
  mode: "simulation",
};

/* ---------- Decisions ---------- */

const PROMPT = { deployment: "gpt-outcome-mini", model_version: "2026-08-01" };

function decision(
  key: string,
  minute: number,
  partial: Partial<DecisionView> & Pick<DecisionView, "kind" | "reason">,
): DecisionView {
  return {
    id: fid(`dec:${key}`),
    created_at: at(minute),
    status: "accepted",
    evidence_ids: [],
    input_refs: {},
    model: null,
    policy: { pass: true, checks: [] },
    proposed_action: null,
    actual_action: null,
    resolution: null,
    ...partial,
  };
}

function model(promptVersion: string, tokensIn: number, tokensOut: number): DecisionView["model"] {
  return { ...PROMPT, prompt_version: promptVersion, usage: { tokens_in: tokensIn, tokens_out: tokensOut } };
}

const D = {
  normalize: decision("normalize", 0.3, {
    kind: "normalize_mission",
    reason:
      "Plan: logistics or fleet-operations companies in India, 200–2,000 employees, buyer is a sales leader. Excludes staffing. Objective: book a 15-minute demo.",
    model: model("normalize.v3", 1210, 240),
    input_refs: { request: "campaign.request_text", profile_version: 1 },
    policy: { pass: true, checks: [{ name: "mandatory_fields_present", pass: true, reason: "Industry, geography, size and buyer role resolved." }] },
  }),
  search: decision("search", 1, {
    kind: "research_companies",
    reason: "Company search returned 3 candidates within the discovery limit (3 of 10).",
    evidence_ids: [EV.companySearch.id, EV.rejectedHeadcount.id, EV.rejectedExcluded.id],
    policy: { pass: true, checks: [{ name: "research_budget", pass: true, reason: "1 of 10 research calls used." }] },
  }),
  rejectA: decision("rejectA", 1.2, {
    kind: "prospect_rejected",
    status: "rejected",
    reason: "Kestrel Route Labs: headcount not reported, so the must-have is unknown.",
    evidence_ids: [EV.rejectedHeadcount.id],
  }),
  rejectB: decision("rejectB", 1.3, {
    kind: "prospect_rejected",
    status: "rejected",
    reason: "Brightyard Staffing: staffing is an excluded industry.",
    evidence_ids: [EV.rejectedExcluded.id],
  }),
  qualify: decision("qualify", 3, {
    kind: "qualify_prospect",
    reason: "Halden Freight Systems passes all 4 must-haves; Priya Raman's current employment is supported by relationship evidence.",
    evidence_ids: [EV.companySearch.id, EV.companyHeadcount.id, EV.companyGeo.id, EV.personTitle.id, EV.relationship.id],
    model: model("qualify.v2", 2140, 310),
  }),
  draft: decision("draft", 4, {
    kind: "draft_verified",
    reason: "Initial draft passed verification: 2 seller facts and 1 prospect fact are each covered by evidence; 1 hypothesis worded as a question.",
    evidence_ids: [EV.seller.id, EV.hiring.id],
    model: model("draft.v4+verify.v2", 3020, 520),
    policy: {
      pass: true,
      checks: [
        { name: "claims_supported", pass: true, reason: "Every claim maps to evidence or an approved fact." },
        { name: "forbidden_promises", pass: true, reason: "No discount, guarantee or deadline language." },
        { name: "recipient_allowlist", pass: true, reason: "To is the consented buyer_test inbox." },
      ],
    },
  }),
  send1: decision("send1", 5, {
    kind: "send_email",
    reason: "Sent the initial message to the consented test inbox playing the buyer.",
    evidence_ids: [EV.policyRecipient.id, EV.sent1.id],
    proposed_action: { kind: "email_send", to: BUYER_TEST_EMAIL, purpose: "initial" },
    actual_action: { action_id: fid("action:send1"), state: "succeeded", provider_ref: `gmail:${fhex("m1", 16)}` },
    policy: {
      pass: true,
      checks: [
        { name: "recipient_allowlist", pass: true, reason: "Exact match on buyer_test." },
        { name: "suppression", pass: true, reason: "No suppression for this email, company or person." },
        { name: "outbound_budget", pass: true, reason: "1 of 6 outbound messages." },
      ],
    },
  }),
  interpret1: decision("interpret1", 14.5, {
    kind: "reply_interpreted",
    reason: "Intent: question (onboarding time). The buyer hasn't accepted a time. Answer from approved facts, then offer 2 slots.",
    evidence_ids: [EV.reply1.id],
    model: model("reply.v3", 1880, 190),
    input_refs: { message_id: fid("msg:m2"), quote: "What does onboarding look like" },
  }),
  slots: decision("slots", 15, {
    kind: "check_slots",
    reason: "2 free 15-minute slots found within working hours (Mon–Fri 09:00–17:00 IST) with a 5-minute buffer.",
    evidence_ids: [EV.freebusy.id],
    policy: { pass: true, checks: [{ name: "freebusy_complete", pass: true, reason: "No per-calendar errors in the response." }] },
  }),
  send2: decision("send2", 16, {
    kind: "send_email",
    reason: "Answered the onboarding question from an approved fact and offered 2 slots.",
    evidence_ids: [EV.sellerOnboarding.id, EV.freebusy.id],
    model: model("draft.v4+verify.v2", 2410, 380),
    proposed_action: { kind: "email_send", to: BUYER_TEST_EMAIL, purpose: "offer_slots" },
    actual_action: { action_id: fid("action:send2"), state: "succeeded", provider_ref: `gmail:${fhex("m3", 16)}` },
  }),
  interpret2: decision("interpret2", 26.4, {
    kind: "reply_interpreted",
    reason: "Intent: accept_slot. “Thursday at 3:30” matches offered slot-1 exactly.",
    evidence_ids: [EV.reply2.id],
    model: model("reply.v3", 1960, 160),
    input_refs: { message_id: fid("msg:m4"), accepted_slot_id: "slot-1" },
  }),
  book: decision("book", 27, {
    kind: "book_meeting",
    reason: "Rechecked free/busy, created the event with a fixed id, and the read-back matched.",
    evidence_ids: [EV.freebusy.id, EV.event.id],
    proposed_action: { kind: "calendar_insert", slot_id: "slot-1", attendees: [BUYER_TEST_EMAIL, OWNER_TEST_EMAIL] },
    actual_action: { action_id: BOOKING.action_id, state: "succeeded", provider_ref: BOOKING.event_id },
    policy: {
      pass: true,
      checks: [
        { name: "explicit_acceptance", pass: true, reason: "Buyer accepted an offered slot." },
        { name: "freebusy_recheck", pass: true, reason: "Slot still free at 18:32 UTC." },
        { name: "attendee_allowlist", pass: true, reason: "Only buyer_test and owner_test." },
      ],
    },
  }),
  confirm: decision("confirm", 28, {
    kind: "send_email",
    reason: "Sent a short confirmation to the test inbox.",
    actual_action: { action_id: fid("action:send3"), state: "succeeded", provider_ref: `gmail:${fhex("m5", 16)}` },
    model: model("draft.v4+verify.v2", 1320, 90),
  }),
  handoff: decision("handoff", 28.5, {
    kind: "write_handoff",
    reason: "Handoff written to the internal CRM with fit, the buyer's stated need, open questions and next steps.",
    evidence_ids: [EV.event.id, EV.reply1.id],
    model: model("handoff.v1", 2650, 410),
  }),
};

const HANDOFF: Handoff = {
  version: 1,
  status: "complete",
  mode: "simulation",
  campaign_id: "",
  prospect_id: fid("prospect:halden"),
  conversation_id: "",
  booking: BOOKING,
  fit_summary:
    "Halden Freight Systems (about 412 employees, logistics software, India) passes every must-have. Priya Raman's current VP Sales title supports role relevance; purchasing authority isn't established.",
  fit_evidence_ids: [EV.companySearch.id, EV.companyHeadcount.id, EV.personTitle.id, EV.relationship.id],
  buyer_stated_needs: [{ text: "Wants to know onboarding time before coordinators can use it.", message_id: fid("msg:m2") }],
  hypotheses: ["Coordinator hiring may mean scheduling volume is growing. The buyer hasn't confirmed this."],
  open_questions: ["Who else is involved in evaluating scheduling tools?", "Which system do coordinators use today?"],
  next_steps: ["Prepare a 15-minute walkthrough focused on onboarding.", "Confirm attendance the morning of 12 Nov."],
  owner_email: OWNER_TEST_EMAIL,
  notification_status: "sent",
};

/* ---------- Snapshot assembly ---------- */

interface Snapshot {
  status: CampaignState;
  stage: string;
  decisions: DecisionView[];
  prospects: ProspectCase[];
  conversation: { state: ConversationState; messages: MessageView[]; slots: Slot[]; booking: BookingReceipt | null } | null;
  handoff: Handoff | null;
}

const RESEARCHED = [D.normalize, D.search, D.rejectA, D.rejectB];

function happy(step: MissionScenario): Snapshot {
  const conv = (state: ConversationState, messages: MessageView[], slots: Slot[] = [], booking: BookingReceipt | null = null) => ({
    state,
    messages,
    slots,
    booking,
  });
  const both = (p: ProspectCase) => [p, REJECTED_A, REJECTED_B];
  switch (step) {
    case "draft":
      return { status: "draft", stage: "normalize_mission", decisions: [], prospects: [], conversation: null, handoff: null };
    case "researching":
      return {
        status: "running",
        stage: "research",
        decisions: RESEARCHED,
        prospects: both(prospect("needs_evidence", false)),
        conversation: conv("researching", []),
        handoff: null,
      };
    case "drafting":
      return {
        status: "running",
        stage: "qualify_and_draft",
        decisions: [...RESEARCHED, D.qualify],
        prospects: both(prospect("qualified", true)),
        conversation: conv("drafting", []),
        handoff: null,
      };
    case "waiting_reply":
      return {
        status: "waiting_reply",
        stage: "poll_inbox",
        decisions: [...RESEARCHED, D.qualify, D.draft, D.send1],
        prospects: both(prospect("qualified", true)),
        conversation: conv("waiting_reply", [M.initial]),
        handoff: null,
      };
    case "evaluating_reply":
      return {
        ...happy("waiting_reply"),
        status: "running",
        stage: "handle_reply",
        conversation: conv("evaluating_reply", [M.initial, M.question]),
      };
    case "offering_slots":
      return {
        ...happy("evaluating_reply"),
        stage: "check_slots",
        decisions: [...happy("waiting_reply").decisions, D.interpret1, D.slots],
        conversation: conv("offering_slots", [M.initial, M.question], SLOTS),
      };
    case "waiting_slot_acceptance":
      return {
        ...happy("offering_slots"),
        status: "waiting_reply",
        stage: "poll_inbox",
        decisions: [...happy("offering_slots").decisions, D.send2],
        conversation: conv("waiting_slot_acceptance", [M.initial, M.question, M.offer], SLOTS),
      };
    case "booking":
      return {
        ...happy("waiting_slot_acceptance"),
        status: "running",
        stage: "book_meeting",
        decisions: [...happy("waiting_slot_acceptance").decisions, D.interpret2],
        conversation: conv("booking", [M.initial, M.question, M.offer, M.accept], SLOTS),
      };
    case "booked":
      return {
        ...happy("booking"),
        stage: "write_handoff",
        decisions: [...happy("booking").decisions, D.book],
        conversation: conv("booked", [M.initial, M.question, M.offer, M.accept], SLOTS, BOOKING),
      };
    case "completed":
      return {
        ...happy("booked"),
        status: "completed",
        stage: "handoff_written",
        decisions: [...happy("booked").decisions, D.confirm, D.handoff],
        conversation: conv("completed", [M.initial, M.question, M.offer, M.accept, M.confirm], SLOTS, BOOKING),
        handoff: HANDOFF,
      };
    default:
      throw new Error(`not a happy-path step: ${step}`);
  }
}

function alternative(scenario: MissionScenario): Snapshot {
  switch (scenario) {
    case "needs_human_time": {
      const base = happy("waiting_slot_acceptance");
      const blocked = decision("ambiguous-time", 26.4, {
        kind: "clarify_time",
        status: "blocked",
        reason:
          "“Thursday or Friday afternoon” is a preference, not an acceptance of an offered slot. No booking is made. Choose a slot the buyer named, or have the worker ask them to pick one.",
        evidence_ids: [EV.replyAmbiguous.id],
        model: model("reply.v3", 1910, 170),
        input_refs: { message_id: fid("msg:m4-amb"), intent: "schedule_preference", needs_clarification: true },
        policy: { pass: false, checks: [{ name: "explicit_acceptance", pass: false, reason: "No offered slot or fully resolved time." }] },
        proposed_action: { resolution_types: ["clarify_time", "stop"] },
      });
      return {
        ...base,
        status: "needs_human",
        stage: "handle_reply",
        decisions: [...base.decisions, blocked],
        conversation: { ...base.conversation!, state: "needs_human", messages: [M.initial, M.question, M.offer, M.ambiguous] },
      };
    }
    case "needs_human_reauth": {
      const base = happy("drafting");
      const blocked = decision("reauth", 4.5, {
        kind: "google_reauthorization",
        status: "blocked",
        reason:
          "The seller's Google connection returned invalid_grant before send. Nothing was dispatched. Reconnect Google in Setup; this resolves once the connection reports connected with all four scopes.",
        evidence_ids: [],
        input_refs: { connection: "seller", phase: "auth", may_have_applied: false },
        policy: { pass: false, checks: [{ name: "connection_status", pass: false, reason: "reauth_required" }] },
        proposed_action: { resolution_types: ["reauthorize_complete", "stop"] },
      });
      return {
        ...base,
        status: "needs_human",
        stage: "send_email",
        decisions: [...base.decisions, D.draft, blocked],
        conversation: { ...base.conversation!, state: "needs_human" },
      };
    }
    case "send_unknown": {
      const base = happy("drafting");
      const blocked = decision("send-unknown", 5.4, {
        kind: "send_unknown",
        status: "blocked",
        reason:
          "Gmail send timed out after dispatch, so the message may have been delivered. Further sends are frozen. 3 reconciliation checks over 60 s found no match, which doesn't prove it wasn't sent. Check the seller's Sent folder before deciding.",
        evidence_ids: [EV.policyRecipient.id],
        proposed_action: { kind: "email_send", to: BUYER_TEST_EMAIL, purpose: "initial", resolution_types: ["stop"] },
        actual_action: { action_id: fid("action:send1-unknown"), state: "unknown", provider_ref: null },
        policy: { pass: false, checks: [{ name: "send_outcome_known", pass: false, reason: "may_have_applied=true, reconcile unresolved" }] },
      });
      return {
        ...base,
        status: "needs_human",
        stage: "reconcile_action",
        decisions: [...base.decisions, D.draft, blocked],
        conversation: {
          state: "send_unknown",
          messages: [{ ...M.initial, status: "unknown", sent_at: null, provider_message_id: null }],
          slots: [],
          booking: null,
        },
      };
    }
    case "no_match": {
      const noMatch = decision("no-match", 2.5, {
        kind: "no_match",
        reason:
          "No candidate passed every must-have within the discovery limit. One candidate's headcount is unknown and one is in an excluded industry. Not widening the search without a changed mission.",
        evidence_ids: [EV.rejectedHeadcount.id, EV.rejectedExcluded.id],
      });
      return {
        status: "no_match",
        stage: "research",
        decisions: [D.normalize, D.search, D.rejectA, D.rejectB, noMatch],
        prospects: [REJECTED_A, REJECTED_B],
        conversation: null,
        handoff: null,
      };
    }
    case "declined": {
      const base = happy("waiting_reply");
      const declined = decision("declined", 14.5, {
        kind: "reply_interpreted",
        reason: "Intent: decline. The conversation ends with no follow-up and no booking.",
        evidence_ids: [EV.replyDecline.id],
        model: model("reply.v3", 1700, 120),
      });
      return {
        ...base,
        status: "stopped",
        stage: "conversation_declined",
        decisions: [...base.decisions, declined],
        conversation: { state: "declined", messages: [M.initial, M.decline], slots: [], booking: null },
      };
    }
    case "suppressed": {
      const base = happy("waiting_reply");
      const optOut = decision("opt-out", 14.4, {
        kind: "opt_out",
        reason: "Intent: opt_out. Suppressed this email, company and person across the organization. No further messages.",
        evidence_ids: [EV.replyOptOut.id],
        model: model("reply.v3", 1650, 110),
        policy: { pass: true, checks: [{ name: "suppression_written", pass: true, reason: "3 suppression entries created." }] },
      });
      return {
        ...base,
        status: "stopped",
        stage: "suppressed",
        decisions: [...base.decisions, optOut],
        conversation: { state: "suppressed", messages: [M.initial, M.optOut], slots: [], booking: null },
      };
    }
    case "paused":
      return { ...happy("waiting_reply"), status: "paused", stage: "poll_inbox" };
    case "stopped": {
      const base = happy("drafting");
      const stop = decision("stop", 3.5, {
        kind: "operator_control",
        reason: "Stopped by an owner before any message was sent. No effects were in flight.",
        input_refs: { action: "stop", expected_version: 4 },
      });
      return {
        ...base,
        status: "stopped",
        stage: "stopped",
        decisions: [...base.decisions, stop],
        conversation: { ...base.conversation!, state: "stopped" },
      };
    }
    case "failed": {
      const fail = decision("failed", 3, {
        kind: "research_failed",
        status: "rejected",
        reason:
          "Person lookup failed 3 times (HTTP 503 from the research provider). Retries are exhausted. No outreach was attempted.",
        policy: { pass: false, checks: [{ name: "retry_budget", pass: false, reason: "3 of 3 attempts used." }] },
      });
      return {
        status: "failed",
        stage: "research",
        decisions: [D.normalize, D.search, D.rejectA, D.rejectB, fail],
        prospects: [prospect("needs_evidence", false), REJECTED_A, REJECTED_B],
        conversation: null,
        handoff: null,
      };
    }
    default:
      return happy(scenario);
  }
}

function usageFor(snapshot: Snapshot): Usage {
  const modelDecisions = snapshot.decisions.filter((d) => d.model);
  const tokensIn = modelDecisions.reduce((sum, d) => sum + Number(d.model?.usage.tokens_in ?? 0), 0);
  const tokensOut = modelDecisions.reduce((sum, d) => sum + Number(d.model?.usage.tokens_out ?? 0), 0);
  return {
    model_calls: modelDecisions.length,
    research_calls: snapshot.decisions.some((d) => d.kind === "research_companies") ? (snapshot.prospects.some((p) => p.person) ? 4 : 2) : 0,
    outbound_attempts: snapshot.conversation?.messages.filter((m) => m.direction === "outbound").length ?? 0,
    calendar_attempts: snapshot.conversation?.booking ? 1 : 0,
    tokens_in: tokensIn,
    tokens_out: tokensOut,
    estimated_cost: null,
  };
}

export interface FixtureMission {
  id: string;
  scenario: MissionScenario;
  request_text: string;
  created_minute: number;
}

export function buildMission(mission: FixtureMission): { detail: MissionDetail; ledger: DecisionView[] } {
  const snapshot = HAPPY_PATH.includes(mission.scenario) ? happy(mission.scenario) : alternative(mission.scenario);
  const lastMinute = snapshot.decisions.length
    ? Math.max(...snapshot.decisions.map((d) => Date.parse(d.created_at)))
    : Date.parse(at(mission.created_minute));

  const referenced = new Set<string>();
  for (const d of snapshot.decisions) d.evidence_ids.forEach((id) => referenced.add(id));
  for (const p of snapshot.prospects) {
    p.relationship.evidence_ids.forEach((id) => referenced.add(id));
    p.criteria.forEach((c) => c.evidence_ids.forEach((id) => referenced.add(id)));
    p.facts.forEach((f) => f.evidence_ids.forEach((id) => referenced.add(id)));
    p.hypotheses.forEach((h) => h.basis_evidence_ids.forEach((id) => referenced.add(id)));
  }
  if (snapshot.decisions.some((d) => d.kind === "draft_verified" || d.kind === "send_email")) {
    referenced.add(EV.seller.id);
    referenced.add(EV.sellerOnboarding.id);
  }

  const conversationId = fid(`conv:${mission.id}`);
  const conversation: ConversationView | null = snapshot.conversation
    ? {
        id: conversationId,
        state: snapshot.conversation.state,
        version: snapshot.decisions.length + 1,
        buyer_role_label: "simulated buyer",
        buyer_test_email: BUYER_TEST_EMAIL,
        provider_thread_id: snapshot.conversation.messages.some((m) => m.provider_message_id) ? fhex("thread", 16) : null,
        messages: snapshot.conversation.messages,
        offered_slots: snapshot.conversation.slots,
        booking: snapshot.conversation.booking,
      }
    : null;

  const ledger = snapshot.decisions.map((d) => ({ ...d, id: fid(`${mission.id}:${d.id}`) }));

  const detail: MissionDetail = {
    id: mission.id,
    request_text: mission.request_text,
    mode: "simulation",
    status: snapshot.status,
    version: snapshot.decisions.length + 1,
    stage: snapshot.stage,
    profile_version: 1,
    config_version: 1,
    usage: usageFor(snapshot),
    last_decision_id: ledger.at(-1)?.id ?? null,
    created_at: at(mission.created_minute),
    updated_at: new Date(lastMinute).toISOString().replace(".000Z", "Z"),
    prospects: snapshot.prospects,
    conversation,
    open_exceptions: ledger.filter((d) => d.status === "blocked" && !d.resolution),
    evidence: ALL_EVIDENCE.filter((e) => referenced.has(e.id)),
    handoff: snapshot.handoff
      ? { ...snapshot.handoff, campaign_id: mission.id, conversation_id: conversationId }
      : null,
  };
  return { detail, ledger };
}

export function toCampaignView(detail: MissionDetail): CampaignView {
  return {
    id: detail.id,
    request_text: detail.request_text,
    mode: detail.mode,
    status: detail.status,
    version: detail.version,
    stage: detail.stage,
    profile_version: detail.profile_version,
    config_version: detail.config_version,
    usage: detail.usage,
    last_decision_id: detail.last_decision_id,
    created_at: detail.created_at,
    updated_at: detail.updated_at,
  };
}

export { ALL_EVIDENCE as FIXTURE_EVIDENCE, EV as FIXTURE_EV };
