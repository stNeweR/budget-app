import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.categories import Category
from app.core.clock import utcnow
from app.core.errors import NotFound
from app.models import Expense, FamilyMember
from app.services.families import list_family_user_ids


@dataclass
class ExpenseFilter:
    user_id: uuid.UUID | None = None
    from_date: date | None = None
    to_date: date | None = None
    category: Category | None = None
    limit: int = 100
    offset: int = 0


def _apply_filter(stmt: Select, expense_filter: ExpenseFilter) -> Select:
    if expense_filter.user_id is not None:
        stmt = stmt.where(Expense.user_id == expense_filter.user_id)
    if expense_filter.from_date is not None:
        stmt = stmt.where(Expense.spent_at >= expense_filter.from_date)
    if expense_filter.to_date is not None:
        stmt = stmt.where(Expense.spent_at <= expense_filter.to_date)
    if expense_filter.category is not None:
        stmt = stmt.where(Expense.category == expense_filter.category.value)
    return stmt


def _page(stmt: Select, expense_filter: ExpenseFilter) -> Select:
    limit = expense_filter.limit if 0 < expense_filter.limit <= 500 else 100
    offset = max(expense_filter.offset, 0)
    return (
        stmt.order_by(Expense.spent_at.desc(), Expense.created_at.desc())
        .limit(limit)
        .offset(offset)
    )


async def list_user_expenses(
    db: AsyncSession, user_id: uuid.UUID, expense_filter: ExpenseFilter
) -> list[Expense]:
    expense_filter = ExpenseFilter(
        user_id=user_id,
        from_date=expense_filter.from_date,
        to_date=expense_filter.to_date,
        category=expense_filter.category,
        limit=expense_filter.limit,
        offset=expense_filter.offset,
    )
    stmt = _page(_apply_filter(select(Expense), expense_filter), expense_filter)
    rows = await db.scalars(stmt)
    return list(rows)


async def list_family_expenses(
    db: AsyncSession, family_id: uuid.UUID, expense_filter: ExpenseFilter
) -> list[Expense]:
    user_ids = await list_family_user_ids(db, family_id)
    if not user_ids:
        return []
    stmt = select(Expense).where(Expense.user_id.in_(user_ids))
    stmt = _apply_filter(stmt, expense_filter)
    stmt = _page(stmt, expense_filter)
    rows = await db.scalars(stmt)
    return list(rows)


async def get_family_expense(
    db: AsyncSession, family_id: uuid.UUID, expense_id: uuid.UUID
) -> Expense:
    expense = await db.scalar(
        select(Expense)
        .join(FamilyMember, FamilyMember.user_id == Expense.user_id)
        .where(Expense.id == expense_id, FamilyMember.family_id == family_id)
    )
    if expense is None:
        raise NotFound("Трата не найдена")
    return expense


async def get_user_expense(db: AsyncSession, user_id: uuid.UUID, expense_id: uuid.UUID) -> Expense:
    expense = await db.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.user_id == user_id)
    )
    if expense is None:
        raise NotFound("Трата не найдена")
    return expense


async def create_family_expense(
    db: AsyncSession,
    family_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    amount: Decimal,
    category: Category,
    spent_at: date | None = None,
    comment: str = "",
) -> Expense:
    target_id = user_id or actor_id
    member = await db.scalar(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id, FamilyMember.user_id == target_id
        )
    )
    if member is None:
        raise NotFound("Участник семьи не найден")

    expense = Expense(
        user_id=target_id,
        amount=amount,
        category=category.value,
        spent_at=spent_at or utcnow().date(),
        comment=comment.strip(),
    )
    db.add(expense)
    await db.flush()
    return expense


async def create_user_expense(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    amount: Decimal,
    category: Category,
    spent_at: date | None = None,
    comment: str = "",
) -> Expense:
    expense = Expense(
        user_id=user_id,
        amount=amount,
        category=category.value,
        spent_at=spent_at or utcnow().date(),
        comment=comment.strip(),
    )
    db.add(expense)
    await db.flush()
    return expense


def apply_patch(expense: Expense, fields: dict) -> Expense:
    if "amount" in fields and fields["amount"] is not None:
        expense.amount = fields["amount"]
    if "category" in fields and fields["category"] is not None:
        category = fields["category"]
        expense.category = category.value if isinstance(category, Category) else str(category)
    if "spent_at" in fields and fields["spent_at"] is not None:
        expense.spent_at = fields["spent_at"]
    if "comment" in fields:
        expense.comment = (fields["comment"] or "").strip()
    expense.updated_at = utcnow()
    return expense


async def delete_expense(db: AsyncSession, expense: Expense) -> None:
    await db.delete(expense)
    await db.flush()


async def sum_user_expenses(
    db: AsyncSession, user_id: uuid.UUID, expense_filter: ExpenseFilter
) -> tuple[Decimal, int]:
    expense_filter = ExpenseFilter(
        user_id=user_id,
        from_date=expense_filter.from_date,
        to_date=expense_filter.to_date,
        category=expense_filter.category,
    )
    stmt = _apply_filter(select(func.sum(Expense.amount), func.count()), expense_filter)
    total, count = (await db.execute(stmt)).one()
    return total or Decimal("0"), int(count or 0)
