"""AES-GCM sealing for Google OAuth tokens stored in connections.encrypted_tokens.

The key comes from TOKEN_ENCRYPTION_KEY (64 hex chars or base64 of 32 bytes; any other value is stretched with
SHA-256). TOKEN_ENCRYPTION_KEY_VERSION is stored next to the blob so keys can rotate.
"""

import base64
import binascii
import hashlib
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_AAD = b"outcome.google.tokens.v1"
_NONCE_BYTES = 12


class TokenKeyMissing(RuntimeError):
    pass


def _key() -> bytes:
    raw = os.environ.get("TOKEN_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise TokenKeyMissing("TOKEN_ENCRYPTION_KEY is not set")
    try:
        key = bytes.fromhex(raw)
        if len(key) == 32:
            return key
    except ValueError:
        pass
    try:
        key = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_" if "-" in raw or "_" in raw else None, validate=True)
        if len(key) == 32:
            return key
    except (binascii.Error, ValueError):
        pass
    return hashlib.sha256(raw.encode()).digest()


def key_version() -> int:
    value = os.environ.get("TOKEN_ENCRYPTION_KEY_VERSION", "").strip()
    return int(value) if value else 1


def seal_tokens(tokens: dict[str, Any]) -> tuple[bytes, int]:
    nonce = os.urandom(_NONCE_BYTES)
    sealed = AESGCM(_key()).encrypt(nonce, json.dumps(tokens, separators=(",", ":")).encode(), _AAD)
    return nonce + sealed, key_version()


def open_tokens(blob: bytes, version: int | None) -> dict[str, Any]:
    if version is not None and version != key_version():
        raise TokenKeyMissing(f"tokens sealed with key version {version}, current is {key_version()}")
    data = bytes(blob)
    return json.loads(AESGCM(_key()).decrypt(data[:_NONCE_BYTES], data[_NONCE_BYTES:], _AAD))
