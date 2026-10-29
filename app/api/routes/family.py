from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import HeadContext, get_current_head
from app.db.session import get_db
from app.models import FamilyMember, User
from app.schemas.auth import FamilyMemberOut, FamilyOut
from app.schemas.family import FamilyDetailOut
from app.services.families import (
    list_family_members,
    rotate_invite_code,
)

router = APIRouter(tags=["family"])


def _member_out(user: User, membership: FamilyMember) -> FamilyMemberOut:
    return FamilyMemberOut(
        id=user.id,
        full_name=user.full_name,
        tg_username=user.tg_username,
        telegram_id=user.telegram_id,
        role=membership.role,
    )


@router.get("/family", response_model=FamilyDetailOut)
async def get_family(
    ctx: HeadContext = Depends(get_current_head),
    db: AsyncSession = Depends(get_db),
) -> FamilyDetailOut:
    rows = await list_family_members(db, ctx.family.id)
    return FamilyDetailOut(
        family=FamilyOut.model_validate(ctx.family),
        members=[_member_out(user, membership) for user, membership in rows],
    )


@router.get("/family/members", response_model=list[FamilyMemberOut])
async def get_family_members(
    ctx: HeadContext = Depends(get_current_head),
    db: AsyncSession = Depends(get_db),
) -> list[FamilyMemberOut]:
    rows = await list_family_members(db, ctx.family.id)
    return [_member_out(user, membership) for user, membership in rows]


@router.post("/family/invite/rotate", response_model=FamilyOut)
async def rotate_invite(
    ctx: HeadContext = Depends(get_current_head),
    db: AsyncSession = Depends(get_db),
) -> FamilyOut:
    await rotate_invite_code(db, ctx.family)
    await db.commit()
    return FamilyOut.model_validate(ctx.family)


@router.get("/users", response_model=list[FamilyMemberOut])
async def legacy_users(
    ctx: HeadContext = Depends(get_current_head),
    db: AsyncSession = Depends(get_db),
) -> list[FamilyMemberOut]:
    """Compatibility alias for the original frontend contract."""
    rows = await list_family_members(db, ctx.family.id)
    return [_member_out(user, membership) for user, membership in rows]
