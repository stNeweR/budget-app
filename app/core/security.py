import hashlib
import secrets
import uuid
from datetime import timedelta

import jwt
from pwdlib import PasswordHash

from app.core.clock import utcnow
from app.core.config import get_settings

password_hasher = PasswordHash.recommended()

# Used to keep password verification timing roughly constant for unknown emails.
DUMMY_PASSWORD_HASH = password_hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password, password_hash)
    except Exception:
        return False


def hash_token(raw: str) -> str:
    """Refresh tokens and login codes are stored only as SHA-256 hashes."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    settings = get_settings()
    now = utcnow()
    expires_at = now + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int((expires_at - now).total_seconds())


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("unexpected token type")
    return payload
