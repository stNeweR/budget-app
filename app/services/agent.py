import json
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.categories import ALL_CATEGORIES, normalize_category
from app.core.clock import utcnow
from app.core.errors import NotFound
from app.models import User
from app.services import expenses as expense_service
from app.services.expenses import ExpenseFilter
from app.services.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)

MAX_STEPS = 6
DATE_FORMAT = "%Y-%m-%d"

TOOL_ADD_EXPENSE = "add_expense"
TOOL_LIST_EXPENSES = "list_expenses"
TOOL_GET_TOTAL = "get_total"
TOOL_UPDATE_EXPENSE = "update_expense"
TOOL_DELETE_EXPENSE = "delete_expense"


def _schema_object(properties: dict, required: list[str] | None = None) -> dict:
    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _schema_string(description: str) -> dict:
    return {"type": "string", "description": description}


def _schema_number(description: str) -> dict:
    return {"type": "number", "description": description}


def _schema_integer(description: str) -> dict:
    return {"type": "integer", "description": description}


def _schema_enum(description: str, values: list[str]) -> dict:
    return {"type": "string", "description": description, "enum": values}


def build_tools() -> list[dict]:
    categories = sorted(ALL_CATEGORIES)
    return [
        {
            "type": "function",
            "function": {
                "name": TOOL_ADD_EXPENSE,
                "description": "Добавить новую трату пользователя.",
                "parameters": _schema_object(
                    {
                        "amount": _schema_number("Сумма траты в рублях, положительное число."),
                        "category": _schema_enum("Категория траты.", categories),
                        "spent_at": _schema_string(
                            "Дата траты в формате YYYY-MM-DD. Если не указана — сегодня."
                        ),
                        "comment": _schema_string("Необязательный короткий комментарий."),
                    },
                    ["amount", "category"],
                ),
            },
        },
        {
            "type": "function",
            "function": {
                "name": TOOL_LIST_EXPENSES,
                "description": (
                    "Показать список трат пользователя. Используй, чтобы найти id траты "
                    "перед изменением или удалением."
                ),
                "parameters": _schema_object(
                    {
                        "from": _schema_string("Начало периода YYYY-MM-DD (включительно)."),
                        "to": _schema_string("Конец периода YYYY-MM-DD (включительно)."),
                        "category": _schema_enum("Фильтр по категории.", categories),
                        "limit": _schema_integer(
                            "Сколько последних трат вернуть (по умолчанию 20)."
                        ),
                    }
                ),
            },
        },
        {
            "type": "function",
            "function": {
                "name": TOOL_GET_TOTAL,
                "description": "Посчитать сумму трат за период, опционально по категории.",
                "parameters": _schema_object(
                    {
                        "from": _schema_string("Начало периода YYYY-MM-DD (включительно)."),
                        "to": _schema_string("Конец периода YYYY-MM-DD (включительно)."),
                        "category": _schema_enum("Фильтр по категории.", categories),
                    }
                ),
            },
        },
        {
            "type": "function",
            "function": {
                "name": TOOL_UPDATE_EXPENSE,
                "description": (
                    "Изменить существующую трату по её id. Сначала найди id через list_expenses."
                ),
                "parameters": _schema_object(
                    {
                        "id": _schema_string(
                            "Идентификатор траты (UUID), полученный из list_expenses."
                        ),
                        "amount": _schema_number("Новая сумма."),
                        "category": _schema_enum("Новая категория.", categories),
                        "spent_at": _schema_string("Новая дата YYYY-MM-DD."),
                        "comment": _schema_string("Новый комментарий."),
                    },
                    ["id"],
                ),
            },
        },
        {
            "type": "function",
            "function": {
                "name": TOOL_DELETE_EXPENSE,
                "description": "Удалить трату по её id. Сначала найди id через list_expenses.",
                "parameters": _schema_object(
                    {
                        "id": _schema_string(
                            "Идентификатор траты (UUID), полученный из list_expenses."
                        )
                    },
                    ["id"],
                ),
            },
        },
    ]


def parse_date(value: str | None, fallback: date) -> date:
    raw = (value or "").strip()
    if not raw:
        return fallback
    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError(f"не удалось разобрать дату {raw!r}, ожидается YYYY-MM-DD") from exc


def _parse_uuid(value: str | None) -> uuid.UUID:
    try:
        return uuid.UUID((value or "").strip())
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"некорректный id траты {value!r}") from exc


def _parse_amount(value: object) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("не удалось разобрать сумму") from exc
    if amount <= 0:
        raise ValueError("сумма должна быть положительной")
    return amount


def _clip(value: str, limit: int = 200) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[:limit] + "..."


class AgentService:
    def __init__(
        self,
        db: AsyncSession,
        llm: LLMClient | None = None,
    ) -> None:
        self.db = db
        self.llm = llm or LLMClient()

    async def handle(self, user: User, text: str) -> str:
        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt(user)},
            {"role": "user", "content": text},
        ]

        for step in range(MAX_STEPS):
            message = await self.llm.chat(messages, build_tools())
            tool_calls = message.get("tool_calls") or []
            logger.info("agent step %d: tool calls=%d", step + 1, len(tool_calls))

            if not tool_calls:
                content = (message.get("content") or "").strip()
                return content or "Не удалось понять запрос. Уточните, пожалуйста."

            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or None,
                    "tool_calls": tool_calls,
                }
            )

            for call in tool_calls:
                function = call.get("function") or {}
                name = function.get("name") or ""
                raw_arguments = function.get("arguments") or "{}"
                logger.info("agent tool %s args=%s", name, _clip(str(raw_arguments)))

                try:
                    result = await self._execute_tool(user, name, raw_arguments)
                except Exception as exc:  # tool errors are reported back to the model
                    logger.warning("agent tool %s failed: %s", name, exc)
                    result = f"Ошибка при выполнении {name}: {exc}"

                logger.info("agent tool %s result=%s", name, _clip(result))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": result,
                    }
                )

        return "Слишком много шагов обработки. Сформулируйте запрос проще."

    def _system_prompt(self, user: User) -> str:
        name = user.full_name or user.tg_username or "пользователь"
        categories = ", ".join(sorted(ALL_CATEGORIES))
        return (
            "Ты — ассистент семейного бюджета. Ты управляешь тратами одного "
            "пользователя через функции.\n\n"
            f"Сегодняшняя дата: {utcnow().date().isoformat()}.\n"
            f"Пользователь: {name} (id={user.id}).\n"
            f"Категории: {categories}.\n\n"
            "Правила:\n"
            "- Понимай обычную речь на русском и вызывай нужную функцию.\n"
            '- Суммы в рублях. Если категория неясна — используй "другое".\n'
            '- "вчера", "сегодня", "позавчера" и подобное переводи в дату YYYY-MM-DD.\n'
            "- Чтобы изменить или удалить трату, сначала вызови list_expenses и "
            "найди её id, затем update_expense/delete_expense.\n"
            "- Ты работаешь только с тратами этого пользователя; чужих трат не "
            "существует.\n"
            "- После действий дай краткий ответ на русском: что сделано и итог."
        )

    async def _execute_tool(self, user: User, name: str, raw_arguments: str | dict) -> str:
        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments or "{}")
            except json.JSONDecodeError as exc:
                raise ValueError(f"не удалось разобрать аргументы: {exc}") from exc
        else:
            arguments = raw_arguments
        if not isinstance(arguments, dict):
            raise ValueError("аргументы инструмента должны быть объектом")

        if name == TOOL_ADD_EXPENSE:
            return await self._tool_add(user, arguments)
        if name == TOOL_LIST_EXPENSES:
            return await self._tool_list(user, arguments)
        if name == TOOL_GET_TOTAL:
            return await self._tool_total(user, arguments)
        if name == TOOL_UPDATE_EXPENSE:
            return await self._tool_update(user, arguments)
        if name == TOOL_DELETE_EXPENSE:
            return await self._tool_delete(user, arguments)
        raise ValueError(f"неизвестный инструмент {name!r}")

    async def _tool_add(self, user: User, arguments: dict) -> str:
        amount = _parse_amount(arguments.get("amount"))
        spent_at = parse_date(arguments.get("spent_at"), utcnow().date())
        category = normalize_category(arguments.get("category"))
        expense = await expense_service.create_user_expense(
            self.db,
            user.id,
            amount=amount,
            category=category,
            spent_at=spent_at,
            comment=str(arguments.get("comment") or ""),
        )
        return (
            f"Сохранено: id={expense.id}, {expense.amount:.2f} ₽, "
            f"{expense.category}, {expense.spent_at.isoformat()}, "
            f"комментарий={expense.comment!r}"
        )

    async def _tool_list(self, user: User, arguments: dict) -> str:
        limit = arguments.get("limit") or 20
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20
        if limit <= 0 or limit > 500:
            limit = 20

        expense_filter = self._build_filter(user, arguments, limit)
        rows = await expense_service.list_user_expenses(self.db, user.id, expense_filter)
        if not rows:
            return "Трат за указанный период не найдено."

        lines = ["Траты (новые сверху):"]
        total = Decimal("0")
        for expense in rows:
            total += expense.amount
            line = (
                f"- id={expense.id} | {expense.spent_at.isoformat()} | "
                f"{expense.amount:.2f} ₽ | {expense.category}"
            )
            if expense.comment:
                line += f" | {expense.comment}"
            lines.append(line)
        lines.append(f"Итого: {total:.2f} ₽ за {len(rows)} шт.")
        return "\n".join(lines)

    async def _tool_total(self, user: User, arguments: dict) -> str:
        expense_filter = self._build_filter(user, arguments, 500)
        total, count = await expense_service.sum_user_expenses(self.db, user.id, expense_filter)
        scope = "за весь период"
        if arguments.get("category"):
            scope = f"по категории {normalize_category(arguments.get('category')).value!r}"
        return f"Итого {scope}: {total:.2f} ₽ ({count} трат)."

    async def _tool_update(self, user: User, arguments: dict) -> str:
        expense_id = _parse_uuid(arguments.get("id"))
        try:
            expense = await expense_service.get_user_expense(self.db, user.id, expense_id)
        except NotFound:
            return (
                "Трата не найдена. Возможно, она принадлежит другому члену семьи или уже удалена."
            )

        fields: dict = {}
        if arguments.get("amount") is not None:
            fields["amount"] = _parse_amount(arguments["amount"])
        if arguments.get("category"):
            fields["category"] = normalize_category(arguments["category"])
        if arguments.get("spent_at"):
            fields["spent_at"] = parse_date(arguments["spent_at"], utcnow().date())
        if "comment" in arguments and arguments.get("comment") is not None:
            fields["comment"] = str(arguments["comment"])
        if not fields:
            return "Не указано, что именно изменить."

        expense_service.apply_patch(expense, fields)
        await self.db.flush()
        return (
            f"Обновлено: id={expense.id} | {expense.spent_at.isoformat()} | "
            f"{expense.amount:.2f} ₽ | {expense.category} | {expense.comment!r}"
        )

    async def _tool_delete(self, user: User, arguments: dict) -> str:
        expense_id = _parse_uuid(arguments.get("id"))
        try:
            expense = await expense_service.get_user_expense(self.db, user.id, expense_id)
        except NotFound:
            return (
                "Трата не найдена. Возможно, она принадлежит другому члену семьи или уже удалена."
            )
        snapshot = f"Удалено: id={expense.id} | {expense.amount:.2f} ₽ | {expense.category}"
        await expense_service.delete_expense(self.db, expense)
        return snapshot

    def _build_filter(self, user: User, arguments: dict, limit: int) -> ExpenseFilter:
        return ExpenseFilter(
            user_id=user.id,
            from_date=parse_date(arguments.get("from"), utcnow().date())
            if arguments.get("from")
            else None,
            to_date=parse_date(arguments.get("to"), utcnow().date())
            if arguments.get("to")
            else None,
            category=normalize_category(arguments.get("category"))
            if arguments.get("category")
            else None,
            limit=limit,
        )


async def not_found_message(error: Exception) -> str:
    if isinstance(error, NotFound):
        return "Трата не найдена. Возможно, она принадлежит другому члену семьи или уже удалена."
    return str(error)


__all__ = ["AgentService", "build_tools", "LLMError"]
