import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models import Family, FamilyMember, User
from app.services.families import create_family

DEFAULT_PASSWORD = "password123"


async def make_user(
    db: AsyncSession,
    *,
    email: str | None = None,
    password: str | None = None,
    full_name: str = "Тестовый пользователь",
    tg_username: str = "tester",
    telegram_id: int | None = None,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password) if password else None,
        full_name=full_name,
        tg_username=tg_username,
        telegram_id=telegram_id if telegram_id is not None else uuid.uuid4().int % 1_000_000_000,
    )
    db.add(user)
    await db.flush()
    return user


async def make_head(
    db: AsyncSession,
    *,
    email: str = "head@example.com",
    password: str = DEFAULT_PASSWORD,
) -> tuple[User, Family]:
    user = await make_user(
        db,
        email=email,
        password=password,
        full_name="Анна Петрова",
        tg_username="mama",
        telegram_id=1000000001,
    )
    family = await create_family(db, user, "Петровы")
    await db.commit()
    return user, family


async def add_member(
    db: AsyncSession,
    family: Family,
    *,
    full_name: str = "Игорь Петров",
    tg_username: str = "papa",
    telegram_id: int = 1000000002,
) -> User:
    user = await make_user(
        db,
        full_name=full_name,
        tg_username=tg_username,
        telegram_id=telegram_id,
    )
    db.add(FamilyMember(family_id=family.id, user_id=user.id, role="member"))
    await db.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    token, _ = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}
