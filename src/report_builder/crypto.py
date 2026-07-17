from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


def _fernet() -> Fernet:
    raw_key = settings.report_source_encryption_key
    if raw_key:
        key = raw_key.encode("ascii")
    else:
        digest = hashlib.sha256(settings.identity_secret_key.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Data source credentials cannot be decrypted") from exc

