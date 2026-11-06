"""Deterministic reply-intent classifier. Ambiguous times never book; only an explicit accept or a clear yes does."""

import re

from services.core.contracts.enums import ReplyIntent

_OPT_OUT = re.compile(
    r"\b(unsubscribe|stop emailing|remove me|opt[-\s]?out|do not (?:email|contact)|stop contacting)\b",
    re.IGNORECASE,
)
_OOO = re.compile(r"\b(out of (?:the )?office|automatic reply|on leave|away from (?:the )?office)\b", re.IGNORECASE)
_HUMAN = re.compile(r"\b(talk to a (?:human|person)|speak to (?:someone|a human)|escalate|need a person)\b", re.IGNORECASE)
_DECLINE = re.compile(
    r"\b(not interested|no thanks|no thank you|pass for now|don'?t want|do not want|please stop)\b",
    re.IGNORECASE,
)
_ACCEPT = re.compile(
    r"\b(works for me|that (?:time|slot) works|let'?s do(?: it)?|book it|i'?ll take|see you then|"
    r"i accept|accepted|lock(?:ing)? (?:it|that) in)\b",
    re.IGNORECASE,
)
_SCHEDULE = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|morning|afternoon|"
    r"\d{1,2}:\d{2}|15[-\s]?minute)\b",
    re.IGNORECASE,
)
_INTERESTED = re.compile(r"\b(interested|sounds good|let'?s talk|happy to|yes|demo)\b", re.IGNORECASE)
_OR_RANGE = re.compile(r"\b(or|either|whenever|sometime|this week|next week)\b", re.IGNORECASE)


def classify_intent(body: str) -> ReplyIntent:
    text = (body or "").strip()
    if not text:
        return ReplyIntent.AMBIGUOUS
    if _OPT_OUT.search(text):
        return ReplyIntent.OPT_OUT
    if _OOO.search(text):
        return ReplyIntent.OUT_OF_OFFICE
    if _HUMAN.search(text):
        return ReplyIntent.REQUEST_HUMAN
    if _DECLINE.search(text):
        return ReplyIntent.DECLINE
    if _ACCEPT.search(text):
        return ReplyIntent.ACCEPT_SLOT
    question = "?" in text
    if question and _OR_RANGE.search(text) and _SCHEDULE.search(text):
        return ReplyIntent.AMBIGUOUS
    if _SCHEDULE.search(text) and _OR_RANGE.search(text) and not _ACCEPT.search(text):
        return ReplyIntent.SCHEDULE_PREFERENCE
    if question:
        return ReplyIntent.QUESTION
    if _INTERESTED.search(text):
        return ReplyIntent.INTERESTED
    if _SCHEDULE.search(text):
        return ReplyIntent.SCHEDULE_PREFERENCE
    return ReplyIntent.AMBIGUOUS
