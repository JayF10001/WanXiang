from __future__ import annotations

import hashlib

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _normalize_secret(secret: str) -> bytes:
    if not secret:
        raise ValueError("缺少 QQ_APP_SECRET，无法进行 webhook 验签")
    return hashlib.sha256(str(secret).encode("utf-8")).digest()


def build_callback_response(*, event_ts: str, plain_token: str, app_secret: str) -> dict[str, str]:
    private_key = Ed25519PrivateKey.from_private_bytes(_normalize_secret(app_secret))
    signature = private_key.sign(f"{event_ts}{plain_token}".encode("utf-8")).hex()
    return {
        "plain_token": plain_token,
        "signature": signature,
    }


def verify_qq_signature(*, timestamp: str, body: bytes, app_secret: str, provided_signature: str) -> bool:
    if not provided_signature:
        return False
    private_key = Ed25519PrivateKey.from_private_bytes(_normalize_secret(app_secret))
    public_key = private_key.public_key()
    try:
        public_key.verify(bytes.fromhex(provided_signature), f"{timestamp}{body.decode('utf-8')}".encode("utf-8"))
    except (InvalidSignature, ValueError):
        return False
    return True
