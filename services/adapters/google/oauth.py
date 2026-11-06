"""Google OAuth for the seller connection: consent URL with a hashed one-time state, code exchange, token storage."""

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx2
import psycopg

from services.core.admin import REQUIRED_GOOGLE_SCOPES
from services.core.contracts.base import normalize_email

from .tokens import seal_tokens

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
STATE_TTL = timedelta(minutes=10)


class OAuthError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _client() -> tuple[str, str, str]:
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    redirect = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if not (client_id and secret and redirect):
        raise OAuthError("google_not_configured")
    return client_id, secret, redirect


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start(conn: psycopg.Connection, *, organization_id: UUID, user_id: UUID) -> tuple[str, datetime]:
    """Must run in a transaction. Keeps an existing connected row usable until the new consent completes."""
    client_id, _, redirect = _client()
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + STATE_TTL
    conn.execute(
        """
        insert into connections (organization_id, provider, purpose, status, oauth_state_hash, oauth_expires_at,
                                 oauth_initiator_user_id, oauth_return_path)
        values (%(org)s, 'google', 'seller', 'pending', %(hash)s, %(exp)s, %(user)s, '/setup')
        on conflict (organization_id, provider, purpose) do update
        set oauth_state_hash = excluded.oauth_state_hash, oauth_expires_at = excluded.oauth_expires_at,
            oauth_initiator_user_id = excluded.oauth_initiator_user_id, oauth_return_path = '/setup', updated_at = now()
        """,
        {"org": organization_id, "hash": _hash(token), "exp": expires, "user": user_id},
    )
    query = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(REQUIRED_GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": token,
    }
    return f"{AUTH_URL}?{urlencode(query)}", expires


def complete(conn: psycopg.Connection, *, code: str, state: str, timeout: float = 20.0) -> dict[str, Any]:
    """Exchange the code, read the account email, and store sealed tokens. Must run in a transaction."""
    row = conn.execute(
        "select id, organization_id, oauth_expires_at from connections where oauth_state_hash = %s for update",
        (_hash(state),),
    ).fetchone()
    if row is None:
        raise OAuthError("unknown_state")
    if row["oauth_expires_at"] is None or row["oauth_expires_at"] < datetime.now(UTC):
        raise OAuthError("state_expired")

    client_id, secret, redirect = _client()
    with httpx2.Client(timeout=timeout) as http:
        res = http.post(TOKEN_URL, data={"code": code, "client_id": client_id, "client_secret": secret,
                                         "redirect_uri": redirect, "grant_type": "authorization_code"})
        if res.status_code != 200:
            raise OAuthError(f"token_exchange_{res.status_code}")
        grant = res.json()
        profile = http.get(PROFILE_URL, headers={"Authorization": f"Bearer {grant['access_token']}"})
        if profile.status_code != 200:
            raise OAuthError(f"profile_{profile.status_code}")
        email = normalize_email(profile.json()["emailAddress"])

    if not grant.get("refresh_token"):
        raise OAuthError("no_refresh_token")
    scopes = sorted(set(grant.get("scope", "").split()))
    expires_at = datetime.now(UTC) + timedelta(seconds=int(grant.get("expires_in", 3600)))
    blob, version = seal_tokens(
        {"refresh_token": grant["refresh_token"], "access_token": grant["access_token"], "expires_at": expires_at.isoformat()}
    )
    connected = set(REQUIRED_GOOGLE_SCOPES) <= set(scopes)
    conn.execute(
        """
        update connections
        set status = %s, account_email = %s, granted_scopes = %s, encrypted_tokens = %s, token_key_version = %s,
            expires_at = %s, calendar_id = coalesce(calendar_id, 'primary'),
            oauth_state_hash = null, oauth_expires_at = null, updated_at = now()
        where id = %s
        """,
        ("connected" if connected else "reauth_required", email, scopes, blob, version, expires_at, row["id"]),
    )
    return {"organization_id": row["organization_id"], "account_email": email, "connected": connected,
            "missing_scopes": sorted(set(REQUIRED_GOOGLE_SCOPES) - set(scopes))}
