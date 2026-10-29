from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Forbidden
from app.models import Family, FamilyMember, User
from app.services.auth import issue_login_code
from app.services.families import (
    count_other_members,
    create_family,
    get_family,
    get_membership,
)

CAPABILITIES = """Просто пиши мне обычным текстом, например:
- «кофе 350» — запишу трату
- «такси 1200 вчера» — учту дату
- «сколько потратил на еду за месяц» — покажу статистику
- «покажи траты за неделю» — список за период
- «последнее было не 350, а 450» — исправлю
- «удали такси» — удалю запись"""

COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Зарегистрироваться и создать семью"),
    ("invite", "Ссылка-приглашение в семью"),
    ("panel", "Веб-панель расходов"),
)


@dataclass
class StartResult:
    outcome: str
    user: User
    family: Family
    head: User | None = None
    member_count: int = 0


@dataclass
class InviteInfo:
    family: Family
    head: User


def greeting(user: User) -> str:
    name = user.full_name or user.tg_username
    return f"Привет, {name}" if name else "Привет"


def commands_help() -> str:
    lines = ["Я понимаю обычный текст про траты и команды:"]
    lines.extend(f"/{name} — {description}" for name, description in COMMANDS)
    return "\n".join(lines)


def head_welcome(user: User) -> str:
    return (
        f"{greeting(user)}! Я бот семейного бюджета. Вы — глава семьи.\n\n"
        f"{CAPABILITIES}\n\n"
        "Семейные команды:\n"
        "/invite — ссылка, чтобы добавить близких в вашу семью\n"
        "/panel — веб-панель с расходами семьи"
    )


def member_welcome(user: User, head: User) -> str:
    return (
        f"{greeting(user)}! Я бот семейного бюджета. Вы в семье, глава — "
        f"{head.display_name}.\n\n"
        f"{CAPABILITIES}\n\n"
        "/invite — ссылка, чтобы позвать в семью ещё кого-нибудь."
    )


async def ensure_bot_user(
    db: AsyncSession,
    *,
    telegram_id: int,
    username: str,
    full_name: str,
) -> User:
    """Upsert a Telegram user and make sure they belong to a family."""
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        user = User(
            telegram_id=telegram_id,
            tg_username=username or "",
            full_name=full_name or "",
        )
        db.add(user)
        await db.flush()
        await create_family(db, user)
        return user

    changed = False
    if username and user.tg_username != username:
        user.tg_username = username
        changed = True
    if full_name and user.full_name != full_name:
        user.full_name = full_name
        changed = True
    if changed:
        await db.flush()
    return user


async def start_bot_user(db: AsyncSession, user: User, code: str) -> StartResult:
    membership = await get_membership(db, user.id)
    if membership is None:
        await create_family(db, user)
        membership = await get_membership(db, user.id)
    if membership is None:  # pragma: no cover - defensive
        raise RuntimeError("failed to create family membership")

    family = await get_family(db, membership.family_id)
    raw_code = (code or "").strip().upper()

    if not raw_code:
        if membership.role == "head":
            return StartResult("head", user, family)
        head = await db.get(User, family.created_by) if family.created_by else None
        return StartResult("member", user, family, head=head)

    invited_family = await db.scalar(select(Family).where(Family.invite_code == raw_code))
    if invited_family is None:
        head = (
            await db.get(User, family.created_by)
            if membership.role != "head" and family.created_by
            else None
        )
        return StartResult("invalid_code", user, family, head=head)

    if invited_family.created_by == user.id:
        return StartResult("own_code", user, family, head=user)

    if membership.family_id == invited_family.id:
        head = await db.get(User, invited_family.created_by) if invited_family.created_by else None
        return StartResult("already_member", user, invited_family, head=head)

    if membership.role == "head":
        others = await count_other_members(db, membership.family_id, user.id)
        if others > 0:
            head = (
                await db.get(User, invited_family.created_by) if invited_family.created_by else None
            )
            return StartResult(
                "head_has_members",
                user,
                family,
                head=head,
                member_count=others,
            )

    old_family_id = membership.family_id
    await db.delete(membership)
    await db.flush()

    # A head joining another family leaves their empty family behind.
    old_membership = await db.scalar(
        select(func.count())
        .select_from(FamilyMember)
        .where(FamilyMember.family_id == old_family_id)
    )
    if old_membership == 0:
        old_family = await db.get(Family, old_family_id)
        if old_family is not None:
            await db.delete(old_family)
            await db.flush()

    db.add(
        FamilyMember(
            family_id=invited_family.id,
            user_id=user.id,
            role="member",
        )
    )
    await db.flush()

    head = await db.get(User, invited_family.created_by) if invited_family.created_by else None
    return StartResult("joined", user, invited_family, head=head)


def format_start_result(result: StartResult) -> str:
    if result.outcome == "head":
        return head_welcome(result.user)
    if result.outcome == "member" and result.head is not None:
        return member_welcome(result.user, result.head)
    if result.outcome == "invalid_code":
        welcome = (
            member_welcome(result.user, result.head)
            if result.head is not None
            else head_welcome(result.user)
        )
        return "Ссылка приглашения недействительна или устарела.\n\n" + welcome
    if result.outcome == "own_code":
        return "Это ваша собственная ссылка — вы и так глава этой семьи."
    if result.outcome == "already_member" and result.head is not None:
        return f"Вы уже в семье — глава {result.head.display_name}."
    if result.outcome == "head_has_members" and result.head is not None:
        return (
            "Вы глава семьи, в которой уже есть участники, поэтому присоединиться "
            f"к семье {result.head.display_name} нельзя."
        )
    if result.outcome == "joined" and result.head is not None:
        return f"Готово! Теперь вы в семье — глава {result.head.display_name}.\n\n{CAPABILITIES}"
    return commands_help()


async def invite_info(db: AsyncSession, user: User) -> InviteInfo:
    membership = await get_membership(db, user.id)
    if membership is None:
        family = await create_family(db, user)
        return InviteInfo(family=family, head=user)

    family = await get_family(db, membership.family_id)
    head = await db.get(User, family.created_by) if family.created_by else user
    return InviteInfo(family=family, head=head or user)


async def invite_link(db: AsyncSession, user: User, bot_username: str) -> str:
    info = await invite_info(db, user)
    return f"https://t.me/{bot_username}?start={info.family.invite_code}"


async def panel_link(db: AsyncSession, user: User) -> str | None:
    """Return a one-time panel login link for the head of the family."""
    settings = get_settings()
    memberships = await get_membership(db, user.id)
    if memberships is None or memberships.role != "head":
        raise Forbidden("Панель доступна только главе семьи")
    code = await issue_login_code(db, user)
    return f"{settings.panel_url_normalized}/login?code={code}"


__all__ = [
    "CAPABILITIES",
    "COMMANDS",
    "InviteInfo",
    "StartResult",
    "commands_help",
    "ensure_bot_user",
    "format_start_result",
    "invite_info",
    "invite_link",
    "panel_link",
    "start_bot_user",
]
