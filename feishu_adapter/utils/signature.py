from __future__ import annotations

import base64
import hashlib
import hmac


def verify_lark_signature(timestamp: str, nonce: str, body: bytes, encrypt_key: str, provided_signature: str) -> bool:
    content = f"{timestamp}{nonce}{encrypt_key}".encode("utf-8") + body
    digest = hmac.new(encrypt_key.encode("utf-8"), content, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, provided_signature or "")
