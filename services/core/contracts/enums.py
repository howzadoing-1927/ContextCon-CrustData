from enum import StrEnum


class CampaignState(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    WAITING_REPLY = "waiting_reply"
    COMPLETED = "completed"
    NO_MATCH = "no_match"
    NEEDS_HUMAN = "needs_human"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


class ConversationState(StrEnum):
    RESEARCHING = "researching"
    QUALIFIED = "qualified"
    DRAFTING = "drafting"
    WAITING_REPLY = "waiting_reply"
    EVALUATING_REPLY = "evaluating_reply"
    OFFERING_SLOTS = "offering_slots"
    WAITING_SLOT_ACCEPTANCE = "waiting_slot_acceptance"
    BOOKING = "booking"
    BOOKED = "booked"
    COMPLETED = "completed"
    DECLINED = "declined"
    SUPPRESSED = "suppressed"
    NEEDS_HUMAN = "needs_human"
    SEND_UNKNOWN = "send_unknown"
    STOPPED = "stopped"


class TaskKind(StrEnum):
    NORMALIZE_MISSION = "normalize_mission"
    RESEARCH = "research"
    QUALIFY_AND_DRAFT = "qualify_and_draft"
    SEND_EMAIL = "send_email"
    POLL_INBOX = "poll_inbox"
    HANDLE_REPLY = "handle_reply"
    CHECK_SLOTS = "check_slots"
    BOOK_MEETING = "book_meeting"
    WRITE_HANDOFF = "write_handoff"
    NOTIFY_OWNER = "notify_owner"
    RECONCILE_ACTION = "reconcile_action"


class TaskStatus(StrEnum):
    READY = "ready"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionKind(StrEnum):
    EMAIL_SEND = "email_send"
    CALENDAR_INSERT = "calendar_insert"
    OWNER_NOTIFY = "owner_notify"


class ActionState(StrEnum):
    PREPARED = "prepared"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"


class DecisionStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    RESOLVED = "resolved"


class EvidenceSourceKind(StrEnum):
    CRUSTDATA = "crustdata"
    SELLER_WEBSITE = "seller_website"
    OPERATOR = "operator"
    GOOGLE_MESSAGE = "google_message"
    GOOGLE_CALENDAR = "google_calendar"
    POLICY = "policy"


class FactStatus(StrEnum):
    OBSERVED = "observed"
    OPERATOR_APPROVED = "operator_approved"
    HYPOTHESIS = "hypothesis"
    CONFLICTED = "conflicted"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(StrEnum):
    PLANNED = "planned"
    SENT = "sent"
    RECEIVED = "received"
    UNKNOWN = "unknown"


class ConnectionProvider(StrEnum):
    GOOGLE = "google"


class ConnectionPurpose(StrEnum):
    SELLER = "seller"
    BUYER_TEST = "buyer_test"


class ConnectionStatus(StrEnum):
    PENDING = "pending"
    CONNECTED = "connected"
    REAUTH_REQUIRED = "reauth_required"
    REVOKED = "revoked"


class MembershipRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class SuppressionIdentityKind(StrEnum):
    EMAIL = "email"
    COMPANY = "company"
    PERSON = "person"


class ReplyIntent(StrEnum):
    INTERESTED = "interested"
    QUESTION = "question"
    OBJECTION = "objection"
    DECLINE = "decline"
    OPT_OUT = "opt_out"
    SCHEDULE_PREFERENCE = "schedule_preference"
    ACCEPT_SLOT = "accept_slot"
    AMBIGUOUS = "ambiguous"
    OUT_OF_OFFICE = "out_of_office"
    REQUEST_HUMAN = "request_human"


class DraftPurpose(StrEnum):
    INITIAL = "initial"
    ANSWER = "answer"
    CLARIFY = "clarify"
    OFFER_SLOTS = "offer_slots"
    CONFIRM = "confirm"


class VerificationVerdict(StrEnum):
    PASS = "pass"
    REVISE = "revise"
    BLOCK = "block"


class ResolutionType(StrEnum):
    SUPPLY_FACT = "supply_fact"
    CLARIFY_TIME = "clarify_time"
    CONFIRM_IDENTITY = "confirm_identity"
    REAUTHORIZE_COMPLETE = "reauthorize_complete"
    STOP = "stop"


class CampaignControl(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"


class ExecutionLabel(StrEnum):
    """Provenance shown in UI, logs and video. Only LIVE counts toward P0 acceptance."""

    LIVE = "LIVE"
    CACHED = "CACHED"
    FIXTURE = "FIXTURE"
    SIMULATED_BUYER = "SIMULATED_BUYER"


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    DOMAIN_INVALID = "DOMAIN_INVALID"
    RECIPIENT_NOT_ALLOWED = "RECIPIENT_NOT_ALLOWED"
    RATE_LIMITED = "RATE_LIMITED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL = "INTERNAL"
