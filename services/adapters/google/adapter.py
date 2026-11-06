"""Live GoogleAdapter over the Gmail and Calendar REST APIs.

Tokens are loaded from the sealed connections row and refreshed here; they never leave this module.
Second guard: Gmail send and Calendar invites only go to the organization's consented buyer_test inboxes and the
seller itself. A researched person's address can never be a recipient.
"""

import base64
import os
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, parseaddr
from typing import Any
from uuid import UUID

import httpx2

from services.core import db
from services.core.contracts.base import normalize_email
from services.core.contracts.enums import ExecutionLabel
from services.core.contracts.google_adapter import (
    BusyRange,
    CalendarEventLookup,
    CalendarEventReceipt,
    CalendarEventRequest,
    ConnectionSummary,
    FailurePhase,
    FreeBusyResult,
    GmailSendReceipt,
    GoogleAdapterError,
    GoogleConnectionRef,
    GoogleFailure,
    GoogleOperation,
    OAuthStart,
    OAuthStartResult,
    OutboundEmail,
    PolledMessage,
    ReconcileResult,
    Retryability,
    ThreadPoll,
)

from . import oauth
from .tokens import open_tokens, seal_tokens

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR = "https://www.googleapis.com/calendar/v3"
LABEL = ExecutionLabel.LIVE


def _failure(op: GoogleOperation, phase: FailurePhase, retry: Retryability, *, applied: bool = False,
             rejected: bool = False, status: int | None = None, detail: str = "") -> GoogleAdapterError:
    return GoogleAdapterError(
        GoogleFailure(operation=op, phase=phase, retryability=retry, may_have_applied=applied,
                      explicit_rejection=rejected, provider_status=status, redacted_detail=detail[:500])
    )


def _header(headers: list[dict[str, str]], name: str) -> str | None:
    return next((h["value"] for h in headers if h["name"].lower() == name.lower()), None)


def _plain_text(payload: dict[str, Any]) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _plain_text(part)
        if text:
            return text
    return ""


def _strip_quoted(text: str) -> str:
    """Keep the new reply; drop the quoted history Gmail appends below 'On ... wrote:'."""
    kept = []
    for line in text.splitlines():
        if line.startswith(">") or (line.startswith("On ") and line.rstrip().endswith("wrote:")):
            break
        kept.append(line)
    return "\n".join(kept).strip() or text.strip()


class LiveGoogleAdapter:
    def __init__(self, timeout: float = 20.0) -> None:
        if os.environ.get("LIVE_EFFECTS_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
            raise RuntimeError("LiveGoogleAdapter requires LIVE_EFFECTS_ENABLED=true")
        self._http = httpx2.Client(timeout=timeout)

    # ------------------------------------------------------------ tokens

    def _access_token(self, connection: GoogleConnectionRef, op: GoogleOperation) -> str:
        with db.connection() as conn:
            row = conn.execute(
                "select status, encrypted_tokens, token_key_version from connections where organization_id = %s and id = %s",
                (connection.organization_id, connection.connection_id),
            ).fetchone()
        if row is None or row["encrypted_tokens"] is None or row["status"] != "connected":
            raise _failure(op, FailurePhase.AUTH, Retryability.REAUTHORIZE, detail="seller connection has no usable tokens")
        tokens = open_tokens(row["encrypted_tokens"], row["token_key_version"])
        if datetime.fromisoformat(tokens["expires_at"]) > datetime.now(UTC) + timedelta(seconds=60):
            return tokens["access_token"]
        client_id, secret, _ = oauth._client()
        res = self._http.post(oauth.TOKEN_URL, data={"client_id": client_id, "client_secret": secret,
                                                     "refresh_token": tokens["refresh_token"], "grant_type": "refresh_token"})
        if res.status_code in (400, 401):
            with db.transaction() as conn:
                conn.execute("update connections set status = 'reauth_required' where id = %s", (connection.connection_id,))
            raise _failure(op, FailurePhase.AUTH, Retryability.REAUTHORIZE, status=res.status_code, detail="refresh token rejected")
        if res.status_code != 200:
            raise _failure(op, FailurePhase.AUTH, Retryability.SAFE_RETRY, status=res.status_code, detail="token refresh failed")
        grant = res.json()
        tokens.update(access_token=grant["access_token"],
                      expires_at=(datetime.now(UTC) + timedelta(seconds=int(grant.get("expires_in", 3600)))).isoformat())
        blob, version = seal_tokens(tokens)
        with db.transaction() as conn:
            conn.execute("update connections set encrypted_tokens = %s, token_key_version = %s, expires_at = %s where id = %s",
                         (blob, version, tokens["expires_at"], connection.connection_id))
        return tokens["access_token"]

    def _allowed_recipients(self, connection: GoogleConnectionRef) -> set[str]:
        with db.connection() as conn:
            org = conn.execute("select policy_json from organizations where id = %s", (connection.organization_id,)).fetchone()
        buyers = {normalize_email(r["email"]) for r in org["policy_json"].get("consented_recipients", [])
                  if r.get("consent_record") and r.get("consented_at")}
        return buyers | {normalize_email(connection.account_email)}

    def _request(self, op: GoogleOperation, connection: GoogleConnectionRef, method: str, url: str, *,
                 effect: bool = False, **kwargs: Any) -> httpx2.Response:
        token = self._access_token(connection, op)
        try:
            res = self._http.request(method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        except httpx2.TimeoutException as exc:
            if effect:
                raise _failure(op, FailurePhase.DISPATCH, Retryability.RECONCILE_FIRST, applied=True, detail=type(exc).__name__) from exc
            raise _failure(op, FailurePhase.DISPATCH, Retryability.SAFE_RETRY, detail=type(exc).__name__) from exc
        except httpx2.TransportError as exc:
            if effect:
                raise _failure(op, FailurePhase.DISPATCH, Retryability.RECONCILE_FIRST, applied=True, detail=type(exc).__name__) from exc
            raise _failure(op, FailurePhase.DISPATCH, Retryability.SAFE_RETRY, detail=type(exc).__name__) from exc
        if res.status_code == 401:
            raise _failure(op, FailurePhase.RESPONSE, Retryability.REAUTHORIZE, rejected=True, status=401, detail="unauthorized")
        return res

    def _check(self, op: GoogleOperation, res: httpx2.Response, *, effect: bool = False) -> dict[str, Any]:
        if 200 <= res.status_code < 300:
            return res.json() if res.content else {}
        detail = res.text[:300]
        if 400 <= res.status_code < 500:
            raise _failure(op, FailurePhase.RESPONSE, Retryability.NEVER, rejected=True, status=res.status_code, detail=detail)
        if effect:
            raise _failure(op, FailurePhase.RESPONSE, Retryability.RECONCILE_FIRST, applied=True, status=res.status_code, detail=detail)
        raise _failure(op, FailurePhase.RESPONSE, Retryability.SAFE_RETRY, status=res.status_code, detail=detail)

    # ------------------------------------------------------------ oauth

    def start_oauth(self, request: OAuthStart) -> OAuthStartResult:
        with db.transaction() as conn:
            url, expires = oauth.start(conn, organization_id=request.organization_id, user_id=request.initiator_user_id)
        return OAuthStartResult(authorization_url=url, expires_at=expires)

    def complete_oauth(self, connection_id: UUID, code: str, state: str) -> ConnectionSummary:
        with db.transaction() as conn:
            oauth.complete(conn, code=code, state=state)
            row = conn.execute("select id, status, account_email, granted_scopes, calendar_id from connections where id = %s",
                               (connection_id,)).fetchone()
        return ConnectionSummary(connection_id=row["id"], status=row["status"], account_email=row["account_email"],
                                 granted_scopes=row["granted_scopes"], calendar_id=row["calendar_id"])

    # ------------------------------------------------------------ gmail

    def gmail_send(self, connection: GoogleConnectionRef, message: OutboundEmail) -> GmailSendReceipt:
        op = GoogleOperation.GMAIL_SEND
        if normalize_email(message.to_email) not in self._allowed_recipients(connection):
            raise _failure(op, FailurePhase.PREFLIGHT, Retryability.NEVER, detail="recipient is not a consented test inbox")
        mime = EmailMessage()
        mime["From"] = message.from_email
        mime["To"] = message.to_email
        mime["Subject"] = message.subject
        mime["Message-ID"] = message.rfc_message_id
        mime["Date"] = format_datetime(datetime.now(UTC))
        if message.in_reply_to:
            mime["In-Reply-To"] = message.in_reply_to
        if message.references:
            mime["References"] = " ".join(message.references)
        mime.set_content(message.body_text)
        body: dict[str, Any] = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}
        if message.provider_thread_id:
            body["threadId"] = message.provider_thread_id
        sent = self._check(op, self._request(op, connection, "POST", f"{GMAIL}/messages/send", effect=True, json=body), effect=True)
        return GmailSendReceipt(provider_message_id=sent["id"], provider_thread_id=sent["threadId"],
                                rfc_message_id=message.rfc_message_id, sent_at=datetime.now(UTC), execution_label=LABEL)

    def gmail_poll_thread(self, connection: GoogleConnectionRef, provider_thread_id: str, after: datetime | None) -> ThreadPoll:
        op = GoogleOperation.GMAIL_POLL_THREAD
        thread = self._check(op, self._request(op, connection, "GET", f"{GMAIL}/threads/{provider_thread_id}", params={"format": "full"}))
        messages = []
        for m in thread.get("messages", []):
            headers = m.get("payload", {}).get("headers", [])
            received = datetime.fromtimestamp(int(m["internalDate"]) / 1000, UTC)
            if after is not None and received <= after:
                continue
            sender = parseaddr(_header(headers, "From") or "")[1]
            if not sender:
                continue
            to = [normalize_email(parseaddr(a)[1]) for a in (_header(headers, "To") or "").split(",") if parseaddr(a)[1]]
            messages.append(PolledMessage(
                provider_message_id=m["id"], provider_thread_id=m["threadId"], rfc_message_id=_header(headers, "Message-ID"),
                in_reply_to=_header(headers, "In-Reply-To"), from_email=normalize_email(sender), to_emails=to,
                subject=_header(headers, "Subject") or "", body_text=_strip_quoted(_plain_text(m.get("payload", {}))),
                received_at=received,
            ))
        return ThreadPoll(provider_thread_id=provider_thread_id, messages=messages, polled_at=datetime.now(UTC), execution_label=LABEL)

    def gmail_reconcile_send(self, connection: GoogleConnectionRef, rfc_message_id: str, provider_thread_id: str | None) -> ReconcileResult:
        op = GoogleOperation.GMAIL_RECONCILE_SEND
        found = self._check(op, self._request(op, connection, "GET", f"{GMAIL}/messages",
                                              params={"q": f"rfc822msgid:{rfc_message_id.strip('<>')}", "includeSpamTrash": "true"}))
        hit = (found.get("messages") or [None])[0]
        now = datetime.now(UTC)
        if not hit:
            return ReconcileResult(status="unresolved", receipt=None, checked_at=now, execution_label=LABEL)
        receipt = GmailSendReceipt(provider_message_id=hit["id"], provider_thread_id=hit["threadId"],
                                   rfc_message_id=rfc_message_id, sent_at=now, execution_label=LABEL)
        return ReconcileResult(status="matched", receipt=receipt, checked_at=now, execution_label=LABEL)

    # ------------------------------------------------------------ calendar

    def calendar_freebusy(self, connection: GoogleConnectionRef, calendar_id: str, time_min: datetime,
                          time_max: datetime, timezone: str) -> FreeBusyResult:
        op = GoogleOperation.CALENDAR_FREEBUSY
        data = self._check(op, self._request(op, connection, "POST", f"{CALENDAR}/freeBusy", json={
            "timeMin": time_min.isoformat(), "timeMax": time_max.isoformat(), "timeZone": timezone,
            "items": [{"id": calendar_id}],
        }))
        cal = data.get("calendars", {}).get(calendar_id, {})
        now = datetime.now(UTC)
        if cal.get("errors"):
            return FreeBusyResult(calendar_id=calendar_id, time_min=time_min, time_max=time_max, status="error", busy=[],
                                  error_reasons=[e.get("reason", "unknown") for e in cal["errors"]], checked_at=now, execution_label=LABEL)
        busy = [BusyRange(start=datetime.fromisoformat(b["start"]), end=datetime.fromisoformat(b["end"])) for b in cal.get("busy", [])]
        return FreeBusyResult(calendar_id=calendar_id, time_min=time_min, time_max=time_max, status="ok", busy=busy,
                              error_reasons=[], checked_at=now, execution_label=LABEL)

    def _receipt(self, event: dict[str, Any], calendar_id: str, timezone: str) -> CalendarEventReceipt:
        return CalendarEventReceipt(
            event_id=event["id"], calendar_id=calendar_id,
            start=datetime.fromisoformat(event["start"]["dateTime"]), end=datetime.fromisoformat(event["end"]["dateTime"]),
            timezone=event["start"].get("timeZone") or timezone,
            attendees=[normalize_email(a["email"]) for a in event.get("attendees", [])],
            booking_fingerprint=(event.get("extendedProperties", {}).get("private", {}) or {}).get("booking_fingerprint"),
            html_link=event.get("htmlLink"), status=event.get("status", "confirmed"), read_at=datetime.now(UTC),
            execution_label=LABEL,
        )

    def calendar_insert(self, connection: GoogleConnectionRef, event: CalendarEventRequest) -> CalendarEventReceipt:
        op = GoogleOperation.CALENDAR_INSERT
        allowed = self._allowed_recipients(connection)
        if any(normalize_email(a) not in allowed for a in event.attendees):
            raise _failure(op, FailurePhase.PREFLIGHT, Retryability.NEVER, detail="attendee is not a consented test inbox")
        body = {
            "id": event.event_id, "summary": event.summary, "description": event.description,
            "start": {"dateTime": event.start.isoformat(), "timeZone": event.timezone},
            "end": {"dateTime": event.end.isoformat(), "timeZone": event.timezone},
            "attendees": [{"email": a} for a in event.attendees],
            "extendedProperties": {"private": {"booking_fingerprint": event.booking_fingerprint}},
        }
        res = self._request(op, connection, "POST", f"{CALENDAR}/calendars/{event.calendar_id}/events", effect=True,
                            params={"sendUpdates": "all"}, json=body)
        if res.status_code == 409:
            lookup = self.calendar_get(connection, event.calendar_id, event.event_id)
            if lookup.event:
                return lookup.event
        return self._receipt(self._check(op, res, effect=True), event.calendar_id, event.timezone)

    def calendar_get(self, connection: GoogleConnectionRef, calendar_id: str, event_id: str) -> CalendarEventLookup:
        op = GoogleOperation.CALENDAR_GET
        res = self._request(op, connection, "GET", f"{CALENDAR}/calendars/{calendar_id}/events/{event_id}")
        if res.status_code in (404, 410):
            return CalendarEventLookup(found=False, event=None, execution_label=LABEL)
        return CalendarEventLookup(found=True, event=self._receipt(self._check(op, res), calendar_id, "UTC"), execution_label=LABEL)
