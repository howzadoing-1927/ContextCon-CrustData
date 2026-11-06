"""Live Google pieces that run without a network or database: token sealing, the recipient guard, reply parsing,
the display-only email lookup, and the reply classifier's keyword fallback."""

import base64
import hashlib
from uuid import uuid4

import httpx2
import pytest

from services.adapters.crustdata.client import CrustdataClient
from services.adapters.crustdata.contact import lookup_business_email
from services.adapters.google import adapter as live
from services.adapters.google.tokens import TokenKeyMissing, open_tokens, seal_tokens
from services.core.contracts.google_adapter import GoogleAdapterError, GoogleConnectionRef, OutboundEmail
from services.worker.converse import _classify


@pytest.fixture
def token_key(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "11" * 32)
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY_VERSION", "3")


def test_tokens_round_trip_and_never_appear_in_the_blob(token_key):
    tokens = {"access_token": "ya29.secret-access", "refresh_token": "1//secret-refresh", "expires_at": "2030-01-01T00:00:00+00:00"}

    blob, version = seal_tokens(tokens)

    assert version == 3
    assert b"secret-access" not in blob and b"secret-refresh" not in blob
    assert open_tokens(blob, version) == tokens


def test_tampered_blob_or_wrong_key_version_is_rejected(token_key):
    blob, version = seal_tokens({"access_token": "a"})
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])

    with pytest.raises(Exception):
        open_tokens(tampered, version)
    with pytest.raises(TokenKeyMissing):
        open_tokens(blob, version + 1)


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY", raising=False)
    with pytest.raises(TokenKeyMissing):
        seal_tokens({"access_token": "a"})


def _adapter(monkeypatch, allowed):
    monkeypatch.setenv("LIVE_EFFECTS_ENABLED", "true")
    adapter = live.LiveGoogleAdapter()
    sent = []
    monkeypatch.setattr(adapter, "_allowed_recipients", lambda ref: set(allowed))

    def request(op, ref, method, url, **kwargs):
        sent.append(kwargs["json"])
        return httpx2.Response(200, json={"id": "m1", "threadId": "t1"})

    monkeypatch.setattr(adapter, "_request", request)
    return adapter, sent


def _email(to):
    return OutboundEmail(action_id=uuid4(), action_key="send:1", request_hash=hashlib.sha256(b"x").hexdigest(),
                         rfc_message_id="<a@outcome>", from_email="seller@example.com", to_email=to, subject="Hello",
                         body_text="Hi there", provider_thread_id=None, in_reply_to=None, references=[])


REF = GoogleConnectionRef(organization_id=uuid4(), connection_id=uuid4(), account_email="seller@example.com")


def test_adapter_refuses_to_mail_anyone_outside_the_consented_inboxes(monkeypatch):
    adapter, sent = _adapter(monkeypatch, {"buyer@test.example", "seller@example.com"})

    with pytest.raises(GoogleAdapterError) as err:
        adapter.gmail_send(REF, _email("real.person@prospect.example"))

    assert err.value.failure.may_have_applied is False
    assert sent == []


def test_adapter_sends_one_recipient_mime_to_a_consented_inbox(monkeypatch):
    adapter, sent = _adapter(monkeypatch, {"buyer@test.example"})

    receipt = adapter.gmail_send(REF, _email("buyer@test.example"))

    raw = base64.urlsafe_b64decode(sent[0]["raw"]).decode()
    assert "To: buyer@test.example" in raw and "Cc:" not in raw and "Message-ID: <a@outcome>" in raw
    assert receipt.provider_thread_id == "t1"


def test_live_adapter_requires_the_live_flag(monkeypatch):
    monkeypatch.setenv("LIVE_EFFECTS_ENABLED", "false")
    with pytest.raises(RuntimeError):
        live.LiveGoogleAdapter()


def test_reply_parsing_keeps_only_the_new_text():
    body = base64.urlsafe_b64encode(b"Option 2 works.\n\nOn Fri, Nov 6 Seller wrote:\n> earlier").decode().rstrip("=")
    payload = {"mimeType": "multipart/alternative", "parts": [{"mimeType": "text/plain", "body": {"data": body}}]}

    assert live._strip_quoted(live._plain_text(payload)) == "Option 2 works."


def _crustdata(body):
    def handler(request):
        return httpx2.Response(200, json=body, headers={"x-request-id": "r1", "x-credits-used": "2"})

    return CrustdataClient(api_key="k", transport=httpx2.MockTransport(handler), sleep=lambda s: None, clock=lambda: 0.0)


def test_email_lookup_prefers_a_verified_address():
    client = _crustdata([{"crustdata_person_id": 7, "contact": {"business_emails": [
        {"email": "guess@acme.example", "status": "risky"}, {"email": " Jane@Acme.example ", "status": "valid"}]}}])

    found = lookup_business_email(client, "crustdata:person:7")

    assert found["email"] == "jane@acme.example" and found["status"] == "valid"
    assert found["source"] == "crustdata:/person/enrich"


def test_email_lookup_reports_not_found_and_never_raises():
    assert lookup_business_email(_crustdata([{"crustdata_person_id": 7}]), "crustdata:person:7")["status"] == "not_found"
    assert lookup_business_email(_crustdata([]), "not-a-ref")["status"] == "lookup_failed"


@pytest.mark.parametrize(("reply", "intent", "slot"), [
    ("Option 2 works for me", "picks_slot", "S2"),
    ("Not interested, please remove me", "declines", None),
    ("Sure, happy to set up a call", "wants_meeting", None),
])
def test_reply_keyword_fallback(reply, intent, slot):
    slots = [{"id": f"S{i}", "label": f"slot {i}"} for i in (1, 2, 3)] if slot else []
    result, meta = _classify(None, reply, slots)
    assert (result["intent"], result["slot_id"], meta) == (intent, slot, None)
