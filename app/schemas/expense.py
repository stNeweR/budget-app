import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.core.categories import Category


class ExpenseCreate(BaseModel):
    user_id: uuid.UUID | None = None
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    category: Category
    spent_at: date | None = None
    comment: str = Field(default="", max_length=500)


class ExpensePatch(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    category: Category | None = None
    spent_at: date | None = None
    comment: str | None = Field(default=None, max_length=500)


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    amount: Decimal
    category: Category
    spent_at: date
    comment: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("amount")
    def serialize_amount(self, value: Decimal) -> float:
        return float(value)
