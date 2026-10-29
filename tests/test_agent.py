import json
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden
from app.models import Expense, User
from app.services.agent import AgentService
from app.services.bot import (
    ensure_bot_user,
    panel_link,
    start_bot_user,
)
from app.services.families import get_membership
from tests.factories import add_member, make_head


class ScriptedLLM:
    def __init__(self, replies: list[dict]):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    async def chat(self, messages, tools=None):
        self.calls.append(messages)
        return self.replies.pop(0)


def tool_call(name: str, arguments: dict, call_id: str = "call-1") -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        ],
    }


def final(text: str = "Готово") -> dict:
    return {"role": "assistant", "content": text}


async def test_agent_adds_expense_for_current_user(db: AsyncSession):
    _, family = await make_head(db)
    member = await add_member(db, family)

    llm = ScriptedLLM(
        [
            tool_call(
                "add_expense",
                {"amount": 350, "category": "еда", "spent_at": "2026-10-01"},
            ),
            final("Записал кофе"),
        ]
    )
    reply = await AgentService(db, llm).handle(member, "кофе 350")

    assert reply == "Записал кофе"
    rows = list(await db.scalars(select(Expense).where(Expense.user_id == member.id)))
    assert len(rows) == 1
    assert rows[0].amount == Decimal("350.00")
    assert rows[0].category == "еда"


async def test_agent_cannot_touch_another_users_expense(db: AsyncSession):
    head, family = await make_head(db)
    member = await add_member(db, family)

    head_expense = Expense(
        user_id=head.id,
        amount=Decimal("500"),
        category="еда",
        spent_at=date(2026, 10, 1),
        comment="обед",
    )
    db.add(head_expense)
    await db.commit()

    llm = ScriptedLLM(
        [
            tool_call(
                "update_expense",
                {"id": str(head_expense.id), "amount": 1},
            ),
            final(),
        ]
    )
    await AgentService(db, llm).handle(member, "исправь обед на 1 рубль")

    tool_message = llm.calls[1][-1]
    assert tool_message["role"] == "tool"
    assert "не найдена" in tool_message["content"]

    await db.refresh(head_expense)
    assert head_expense.amount == Decimal("500.00")


async def test_agent_total_is_scoped_to_user(db: AsyncSession):
    head, family = await make_head(db)
    member = await add_member(db, family)

    db.add_all(
        [
            Expense(
                user_id=head.id,
                amount=Decimal("500"),
                category="еда",
                spent_at=date(2026, 10, 1),
            ),
            Expense(
                user_id=member.id,
                amount=Decimal("350"),
                category="еда",
                spent_at=date(2026, 10, 2),
            ),
        ]
    )
    await db.commit()

    llm = ScriptedLLM([tool_call("get_total", {}), final()])
    await AgentService(db, llm).handle(member, "сколько я потратил")

    tool_message = llm.calls[1][-1]
    assert "350" in tool_message["content"]
    assert "500" not in tool_message["content"]


async def test_bot_start_and_join_flow(db: AsyncSession):
    head = await ensure_bot_user(db, telegram_id=7001, username="head", full_name="Глава Семьи")
    started = await start_bot_user(db, head, "")
    assert started.outcome == "head"

    member = await ensure_bot_user(
        db, telegram_id=7002, username="member", full_name="Участник Семьи"
    )
    joined = await start_bot_user(db, member, started.family.invite_code.lower())
    assert joined.outcome == "joined"

    membership = await get_membership(db, member.id)
    assert membership is not None
    assert membership.family_id == started.family.id
    assert membership.role == "member"

    with_own_members = await ensure_bot_user(
        db, telegram_id=7003, username="other", full_name="Другая Семья"
    )
    own = await start_bot_user(db, with_own_members, "")
    await ensure_bot_user(db, telegram_id=7004, username="child", full_name="Ребёнок")
    child = await db.scalar(select(User).where(User.telegram_id == 7004))
    await start_bot_user(db, child, own.family.invite_code)

    refused = await start_bot_user(db, with_own_members, started.family.invite_code)
    assert refused.outcome == "head_has_members"


async def test_panel_link_only_for_head(db: AsyncSession):
    head, family = await make_head(db)
    member = await add_member(db, family)

    link = await panel_link(db, head)
    assert link is not None
    assert "/login?code=" in link

    try:
        await panel_link(db, member)
    except Forbidden:
        pass
    else:  # pragma: no cover
        raise AssertionError("member must not receive a panel link")
