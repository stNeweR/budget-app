import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, InvalidCredentials
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Family, FamilyMember, User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class HeadContext:
    user: User
    family: Family
    membership: FamilyMember


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise InvalidCredentials("Требуется авторизация")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise InvalidCredentials("Недействительный или истёкший токен") from None

    user = await db.get(User, user_id)
    if user is None:
        raise InvalidCredentials("Пользователь не найден")
    return user


async def get_current_head(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HeadContext:
    row = (
        await db.execute(
            select(FamilyMember, Family)
            .join(Family, Family.id == FamilyMember.family_id)
            .where(FamilyMember.user_id == user.id)
        )
    ).first()

    if row is None:
        raise Forbidden("Пользователь не состоит в семье")
    membership, family = row
    if membership.role != "head":
        raise Forbidden("Панель доступна только главе семьи")

    return HeadContext(user=user, family=family, membership=membership)
