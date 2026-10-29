import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.categories import Category
from app.core.deps import HeadContext, get_current_head
from app.core.errors import InvalidInput
from app.db.session import get_db
from app.schemas.expense import ExpenseCreate, ExpenseOut, ExpensePatch
from app.services import expenses as expense_service
from app.services.expenses import ExpenseFilter

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    user_id: uuid.UUID | None = Query(default=None),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    category: Category | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    ctx: HeadContext = Depends(get_current_head),
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseOut]:
    expense_filter = ExpenseFilter(
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
        category=category,
        limit=limit,
        offset=offset,
    )
    rows = await expense_service.list_family_expenses(db, ctx.family.id, expense_filter)
    return [ExpenseOut.model_validate(row) for row in rows]


@router.post("", response_model=ExpenseOut, status_code=201)
async def create_expense(
    payload: ExpenseCreate,
    ctx: HeadContext = Depends(get_current_head),
    db: AsyncSession = Depends(get_db),
) -> ExpenseOut:
    expense = await expense_service.create_family_expense(
        db,
        ctx.family.id,
        ctx.user.id,
        user_id=payload.user_id,
        amount=payload.amount,
        category=payload.category,
        spent_at=payload.spent_at,
        comment=payload.comment,
    )
    await db.commit()
    return ExpenseOut.model_validate(expense)


@router.get("/{expense_id}", response_model=ExpenseOut)
async def get_expense(
    expense_id: uuid.UUID,
    ctx: HeadContext = Depends(get_current_head),
    db: AsyncSession = Depends(get_db),
) -> ExpenseOut:
    expense = await expense_service.get_family_expense(db, ctx.family.id, expense_id)
    return ExpenseOut.model_validate(expense)


@router.patch("/{expense_id}", response_model=ExpenseOut)
async def update_expense(
    expense_id: uuid.UUID,
    payload: ExpensePatch,
    ctx: HeadContext = Depends(get_current_head),
    db: AsyncSession = Depends(get_db),
) -> ExpenseOut:
    expense = await expense_service.get_family_expense(db, ctx.family.id, expense_id)
    fields = payload.model_dump(exclude_unset=True)

    for required_field in ("amount", "category", "spent_at"):
        if required_field in fields and fields[required_field] is None:
            raise InvalidInput(f"Поле {required_field} не может быть пустым")

    expense_service.apply_patch(expense, fields)
    await db.commit()
    return ExpenseOut.model_validate(expense)


@router.delete("/{expense_id}", status_code=204)
async def delete_expense(
    expense_id: uuid.UUID,
    ctx: HeadContext = Depends(get_current_head),
    db: AsyncSession = Depends(get_db),
) -> Response:
    expense = await expense_service.get_family_expense(db, ctx.family.id, expense_id)
    await expense_service.delete_expense(db, expense)
    await db.commit()
    return Response(status_code=204)
