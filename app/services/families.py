import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.models import Family, FamilyMember, User

INVITE_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
INVITE_CODE_LENGTH = 10


def generate_invite_code() -> str:
    return "".join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))


async def unique_invite_code(db: AsyncSession) -> str:
    for _ in range(10):
        code = generate_invite_code()
        exists = await db.scalar(select(Family.id).where(Family.invite_code == code))
        if exists is None:
            return code
    raise RuntimeError("failed to generate a unique invite code")


async def create_family(db: AsyncSession, user: User, name: str | None = None) -> Family:
    family = Family(
        name=name or "Семья",
        invite_code=await unique_invite_code(db),
        created_by=user.id,
    )
    db.add(family)
    await db.flush()
    db.add(FamilyMember(family_id=family.id, user_id=user.id, role="head"))
    await db.flush()
    return family


async def get_membership(db: AsyncSession, user_id: uuid.UUID) -> FamilyMember | None:
    return await db.scalar(select(FamilyMember).where(FamilyMember.user_id == user_id))


async def get_family(db: AsyncSession, family_id: uuid.UUID) -> Family:
    family = await db.get(Family, family_id)
    if family is None:
        raise NotFound("Семья не найдена")
    return family


async def get_family_for_user(db: AsyncSession, user_id: uuid.UUID) -> tuple[Family, FamilyMember]:
    membership = await get_membership(db, user_id)
    if membership is None:
        raise NotFound("Пользователь не состоит в семье")
    family = await get_family(db, membership.family_id)
    return family, membership


async def list_family_members(
    db: AsyncSession, family_id: uuid.UUID
) -> list[tuple[User, FamilyMember]]:
    rows = await db.execute(
        select(User, FamilyMember)
        .join(FamilyMember, FamilyMember.user_id == User.id)
        .where(FamilyMember.family_id == family_id)
        .order_by(User.full_name, User.id)
    )
    return list(rows.all())


async def list_family_user_ids(db: AsyncSession, family_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await db.scalars(select(FamilyMember.user_id).where(FamilyMember.family_id == family_id))
    return list(rows)


async def list_family_users(db: AsyncSession, family_id: uuid.UUID) -> list[User]:
    rows = await db.scalars(
        select(User)
        .join(FamilyMember, FamilyMember.user_id == User.id)
        .where(FamilyMember.family_id == family_id)
        .order_by(User.full_name, User.id)
    )
    return list(rows)


async def rotate_invite_code(db: AsyncSession, family: Family) -> str:
    family.invite_code = await unique_invite_code(db)
    await db.flush()
    return family.invite_code


async def count_other_members(db: AsyncSession, family_id: uuid.UUID, user_id: uuid.UUID) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(FamilyMember)
        .where(FamilyMember.family_id == family_id, FamilyMember.user_id != user_id)
    )
    return int(count or 0)
