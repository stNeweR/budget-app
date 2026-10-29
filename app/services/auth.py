import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.errors import Conflict, Forbidden, InvalidCredentials, InvalidInput
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import LoginCode, RefreshToken, User
from app.services.families import get_membership


@dataclass
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def ensure_head(db: AsyncSession, user: User) -> None:
    membership = await get_membership(db, user.id)
    if membership is None or membership.role != "head":
        raise Forbidden("Панель доступна только главе семьи")


async def issue_login_code(db: AsyncSession, user: User) -> str:
    await ensure_head(db, user)
    settings = get_settings()
    raw = generate_opaque_token()
    db.add(
        LoginCode(
            user_id=user.id,
            code_hash=hash_token(raw),
            expires_at=utcnow() + timedelta(seconds=settings.login_code_ttl_seconds),
        )
    )
    await db.flush()
    return raw


async def consume_login_code(db: AsyncSession, raw_code: str) -> User:
    code = await db.scalar(
        select(LoginCode)
        .where(
            LoginCode.code_hash == hash_token(raw_code.strip()),
            LoginCode.used_at.is_(None),
            LoginCode.expires_at > utcnow(),
        )
        .with_for_update()
    )
    if code is None:
        raise InvalidCredentials("Код недействителен или истёк")

    code.used_at = utcnow()
    user = await db.get(User, code.user_id)
    if user is None:
        raise InvalidCredentials("Код недействителен или истёк")
    await ensure_head(db, user)
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    normalized = normalize_email(email)
    user = await db.scalar(select(User).where(User.email == normalized))

    if user is None or not user.password_hash:
        # Keep the response time roughly constant whether the email exists or not.
        verify_password(password, DUMMY_PASSWORD_HASH)
        raise InvalidCredentials("Неверный email или пароль")

    if not verify_password(password, user.password_hash):
        raise InvalidCredentials("Неверный email или пароль")

    await ensure_head(db, user)
    return user


async def set_password(
    db: AsyncSession,
    user: User,
    email: str,
    password: str,
    current_password: str | None = None,
) -> User:
    normalized = normalize_email(email)
    existing = await db.scalar(select(User).where(User.email == normalized, User.id != user.id))
    if existing is not None:
        raise Conflict("Этот email уже используется")

    if user.password_hash:
        if not current_password or not verify_password(current_password, user.password_hash):
            raise InvalidInput("Неверный текущий пароль")

    user.email = normalized
    user.password_hash = hash_password(password)
    await db.flush()
    return user


async def issue_tokens(db: AsyncSession, user: User, user_agent: str | None = None) -> IssuedTokens:
    settings = get_settings()
    access_token, expires_in = create_access_token(user.id)
    refresh_raw = generate_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_raw),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
            user_agent=(user_agent or "")[:500],
        )
    )
    await db.flush()
    return IssuedTokens(
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=refresh_raw,
    )


async def rotate_refresh(
    db: AsyncSession, raw_refresh: str, user_agent: str | None = None
) -> tuple[User, IssuedTokens]:
    token = await db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_refresh))
        .with_for_update()
    )
    if token is None:
        raise InvalidCredentials("Сессия истекла, войдите снова")

    if token.revoked_at is not None:
        # A revoked token was replayed: invalidate every session of this user.
        await revoke_all_user_tokens(db, token.user_id)
        raise InvalidCredentials("Сессия истекла, войдите снова")

    if token.expires_at <= utcnow():
        raise InvalidCredentials("Сессия истекла, войдите снова")

    user = await db.get(User, token.user_id)
    if user is None:
        raise InvalidCredentials("Сессия истекла, войдите снова")
    await ensure_head(db, user)

    token.revoked_at = utcnow()
    tokens = await issue_tokens(db, user, user_agent)
    return user, tokens


async def revoke_refresh(db: AsyncSession, raw_refresh: str) -> None:
    if not raw_refresh:
        return
    token = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
    )
    if token is not None and token.revoked_at is None:
        token.revoked_at = utcnow()
        await db.flush()


async def revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
