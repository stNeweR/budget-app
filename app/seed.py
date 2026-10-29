import argparse
import asyncio
import random
import sys
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select

from app.core.categories import Category
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionFactory, engine
from app.models import Expense, Family, FamilyMember, LoginCode, RefreshToken, User
from app.services.auth import issue_login_code
from app.services.families import create_family

DEMO_HEAD_EMAIL = "head@example.com"
DEMO_HEAD_PASSWORD = "password123"
DEMO_INVITE_CODE = "DEMO2026"

PROFILES: list[tuple[Category, list[str], int, int]] = [
    (Category.FOOD, ["кофе", "обед в кафе", "продукты на неделю", "пицца", "завтрак"], 150, 4000),
    (Category.TRANSPORT, ["такси", "проездной", "бензин", "метро"], 60, 3500),
    (Category.HOUSING, ["квартплата", "интернет", "электричество", "ремонт розетки"], 500, 12000),
    (Category.FUN, ["кино", "настольная игра", "подписка", "концерт"], 300, 5000),
    (Category.HEALTH, ["аптека", "зубной врач", "витамины", "анализы"], 300, 8000),
    (Category.SHOPPING, ["футболка", "книга", "посуда", "зарядка для телефона"], 400, 9000),
    (Category.OTHER, ["подарок", "непредвиденное", "бытовая мелочь"], 200, 3000),
]

DEMO_MEMBERS: list[dict] = [
    {
        "telegram_id": 1000000001,
        "tg_username": "mama",
        "full_name": "Анна Петрова",
        "head": True,
    },
    {
        "telegram_id": 1000000002,
        "tg_username": "papa",
        "full_name": "Игорь Петров",
    },
    {
        "telegram_id": 1000000003,
        "tg_username": "masha",
        "full_name": "Маша Петрова",
    },
    {
        "telegram_id": 1000000004,
        "tg_username": "ded",
        "full_name": "Виктор Петров",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo family budget data")
    parser.add_argument("--reset", action="store_true", help="truncate tables first")
    parser.add_argument("--members", type=int, default=3, help="number of family members")
    parser.add_argument("--per-user", type=int, default=40, help="expenses per member")
    parser.add_argument("--days", type=int, default=90, help="spread expenses over last N days")
    parser.add_argument("--seed", type=int, default=1, help="random seed")
    return parser.parse_args()


async def reset_tables(session) -> None:
    for model in (RefreshToken, LoginCode, Expense, FamilyMember, Family, User):
        await session.execute(delete(model))


async def run(reset: bool, members_count: int, per_user: int, days: int, seed: int) -> None:
    settings = get_settings()
    rng = random.Random(seed)

    async with SessionFactory() as session:
        if reset:
            await reset_tables(session)
        else:
            existing = await session.scalar(select(func.count()).select_from(User))
            if existing:
                print(
                    f"already seeded ({existing} users). Run with --reset to start over.",
                    file=sys.stderr,
                )
                return

        selected = DEMO_MEMBERS[: max(members_count, 1)]
        if members_count > len(DEMO_MEMBERS):
            for index in range(len(DEMO_MEMBERS), members_count):
                selected.append(
                    {
                        "telegram_id": 1000000001 + index,
                        "tg_username": f"member{index + 1}",
                        "full_name": f"Член семьи {index + 1}",
                    }
                )

        head_user: User | None = None
        users: list[User] = []
        for index, member in enumerate(selected):
            user = User(
                email=DEMO_HEAD_EMAIL if index == 0 else None,
                password_hash=hash_password(DEMO_HEAD_PASSWORD) if index == 0 else None,
                full_name=member["full_name"],
                tg_username=member["tg_username"],
                telegram_id=member["telegram_id"],
            )
            session.add(user)
            await session.flush()
            users.append(user)
            if index == 0:
                head_user = user

        assert head_user is not None
        family = await create_family(session, head_user, "Петровы")
        family.invite_code = DEMO_INVITE_CODE
        await session.flush()

        for user in users[1:]:
            session.add(FamilyMember(family_id=family.id, user_id=user.id, role="member"))
        await session.flush()

        today = utcnow().date()
        created = 0
        for user in users:
            for _ in range(per_user):
                category, comments, minimum, maximum = rng.choice(PROFILES)
                amount = Decimal(rng.randint(minimum, maximum))
                spent_at = today - timedelta(days=rng.randint(0, max(days, 1)))
                session.add(
                    Expense(
                        user_id=user.id,
                        amount=amount,
                        category=category.value,
                        spent_at=spent_at,
                        comment=rng.choice(comments),
                    )
                )
                created += 1

        login_code = await issue_login_code(session, head_user)
        await session.commit()

        print(f"seeded {len(users)} members and {created} expenses (seed={seed})")
        print(f"head: {DEMO_HEAD_EMAIL} / {DEMO_HEAD_PASSWORD}")
        print(f"invite code: {DEMO_INVITE_CODE}")
        print(f"panel: {settings.panel_url_normalized}/login?code={login_code}")

    await engine.dispose()


def main() -> None:
    args = parse_args()
    asyncio.run(run(args.reset, args.members, args.per_user, args.days, args.seed))


if __name__ == "__main__":
    main()
