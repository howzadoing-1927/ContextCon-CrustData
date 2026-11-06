import type { BookingReceipt, ConversationView, MessageView, Slot } from "@/lib/contracts";

export const SELLER = "seller@toastinc.in";
export const BUYER = "consenting-buyer@example.invalid";
export const TZ = "Asia/Kolkata";

const SLOT_A: Slot = {
  id: "slot-fri",
  start: "2026-11-07T10:00:00.000Z",
  end: "2026-11-07T10:30:00.000Z",
  timezone: TZ,
  freebusy_checked_at: "2026-11-06T01:12:00.000Z",
};

const SLOT_B: Slot = {
  id: "slot-mon",
  start: "2026-11-10T05:30:00.000Z",
  end: "2026-11-10T06:00:00.000Z",
  timezone: TZ,
  freebusy_checked_at: "2026-11-06T01:12:00.000Z",
};

export const BOOKING: BookingReceipt = {
  action_id: "8c2e1a44-6b11-4d0a-9f3c-2a7b0e4d91c0",
  event_id: "toast-demo-indroneil-20261107",
  calendar_id: "primary",
  start: SLOT_A.start,
  end: SLOT_A.end,
  timezone: TZ,
  html_link: "https://calendar.google.com/calendar/event?eid=toast-demo",
  verified_at: "2026-11-06T01:18:40.000Z",
  attendee_acceptance: "not_verified",
  mode: "simulation",
  execution_label: "SIMULATED_BUYER",
};

function msg(id: string, partial: Omit<MessageView, "id">): MessageView {
  return { id, ...partial };
}

const INDRONEIL_OUT = msg("out-ind", {
  direction: "outbound",
  status: "sent",
  sent_at: "2026-11-06T00:48:12.000Z",
  received_at: null,
  provider_message_id: "gmail:sent-ind-01",
  subject: "Exploring restaurant management for Speciality Restaurants",
  body_text:
    "We researched Speciality Restaurants Pvt. Ltd as a possible fit because it runs 62 food and beverage outlets in important Indian cities. Toast Inc is a comprehensive restaurant management partner.\n\nIn this test you are playing the buyer. Would a short demo be useful?",
  execution_label: "SIMULATED_BUYER",
});

const INDRONEIL_Q = msg("in-ind-q", {
  direction: "inbound",
  status: "received",
  sent_at: null,
  received_at: "2026-11-06T00:56:20.000Z",
  provider_message_id: "gmail:in-ind-01",
  subject: "Re: Exploring restaurant management for Speciality Restaurants",
  body_text: "Interesting. How long is the call, and do you have time Thursday or Friday afternoon IST?",
  execution_label: "SIMULATED_BUYER",
});

const INDRONEIL_OFFER = msg("out-ind-offer", {
  direction: "outbound",
  status: "sent",
  sent_at: "2026-11-06T01:12:08.000Z",
  received_at: null,
  provider_message_id: "gmail:sent-ind-02",
  subject: "Re: Exploring restaurant management for Speciality Restaurants",
  body_text:
    "The call is 30 minutes. I can walk through how Toast Inc partners with restaurant operators.\n\nEither of these work?\n\n• Fri 7 Nov, 3:30–4:00 PM IST\n• Mon 10 Nov, 11:00–11:30 AM IST",
  execution_label: "SIMULATED_BUYER",
});

const INDRONEIL_YES = msg("in-ind-yes", {
  direction: "inbound",
  status: "received",
  sent_at: null,
  received_at: "2026-11-06T01:16:44.000Z",
  provider_message_id: "gmail:in-ind-02",
  subject: "Re: Exploring restaurant management for Speciality Restaurants",
  body_text: "Friday at 3:30 works. Please send the invite.",
  execution_label: "SIMULATED_BUYER",
});

const INDRONEIL_CONFIRM = msg("out-ind-ok", {
  direction: "outbound",
  status: "sent",
  sent_at: "2026-11-06T01:18:40.000Z",
  received_at: null,
  provider_message_id: "gmail:sent-ind-03",
  subject: "Re: Exploring restaurant management for Speciality Restaurants",
  body_text: "Booked. You will get a calendar invitation for Fri 7 Nov, 3:30–4:00 PM IST. Talk then.",
  execution_label: "SIMULATED_BUYER",
});

const SALMAN_OUT = msg("out-sal", {
  direction: "outbound",
  status: "sent",
  sent_at: "2026-11-06T00:48:40.000Z",
  received_at: null,
  provider_message_id: "gmail:sent-sal-01",
  subject: "Burger Singh as a possible fit for restaurant management",
  body_text:
    "We researched Burger Singh as a possible fit because it is a quick-service restaurant brand with outlets across India. Toast Inc is a comprehensive restaurant management partner.\n\nIn this test you are playing the buyer. Would a short demo be useful?",
  execution_label: "SIMULATED_BUYER",
});

const SALMAN_NO = msg("in-sal-no", {
  direction: "inbound",
  status: "received",
  sent_at: null,
  received_at: "2026-11-06T01:02:11.000Z",
  provider_message_id: "gmail:in-sal-01",
  subject: "Re: Burger Singh as a possible fit for restaurant management",
  body_text: "Not looking at new tools this quarter. Please don't follow up.",
  execution_label: "SIMULATED_BUYER",
});

function thread(
  state: ConversationView["state"],
  messages: MessageView[],
  extra: Partial<ConversationView> = {},
): ConversationView {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    state,
    version: messages.length,
    buyer_role_label: "simulated buyer",
    buyer_test_email: BUYER,
    provider_thread_id: extra.provider_thread_id ?? "gmail:thread-ind",
    messages,
    offered_slots: extra.offered_slots ?? [],
    booking: extra.booking ?? null,
  };
}

export type Beat = {
  slug: string;
  title: string;
  person: string;
  company: string;
  place: string;
  email: string | null;
  conversation: ConversationView;
  leftAlone?: boolean;
};

export const BEATS: Beat[] = [
  {
    slug: "sent",
    title: "The agent sends the first email",
    person: "Indroneil Chatterjee",
    company: "Speciality Restaurants Pvt. Ltd",
    place: "Andheri, Mumbai",
    email: "indroneil@speciality.co.in",
    conversation: thread("waiting_reply", [INDRONEIL_OUT]),
  },
  {
    slug: "reply",
    title: "The buyer replies. The agent answers.",
    person: "Indroneil Chatterjee",
    company: "Speciality Restaurants Pvt. Ltd",
    place: "Andheri, Mumbai",
    email: "indroneil@speciality.co.in",
    conversation: thread("waiting_slot_acceptance", [INDRONEIL_OUT, INDRONEIL_Q, INDRONEIL_OFFER], {
      offered_slots: [SLOT_A, SLOT_B],
    }),
  },
  {
    slug: "booked",
    title: "One person books the demo",
    person: "Indroneil Chatterjee",
    company: "Speciality Restaurants Pvt. Ltd",
    place: "Andheri, Mumbai",
    email: "indroneil@speciality.co.in",
    conversation: thread("booked", [INDRONEIL_OUT, INDRONEIL_Q, INDRONEIL_OFFER, INDRONEIL_YES, INDRONEIL_CONFIRM], {
      offered_slots: [SLOT_A, SLOT_B],
      booking: BOOKING,
    }),
  },
  {
    slug: "declined",
    title: "Another person says no",
    person: "Salman Rahman",
    company: "Burger Singh",
    place: "Gurgaon, Haryana",
    email: null,
    conversation: thread("declined", [SALMAN_OUT, SALMAN_NO], { provider_thread_id: "gmail:thread-sal" }),
    leftAlone: true,
  },
];
