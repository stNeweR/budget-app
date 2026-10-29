from enum import StrEnum


class Category(StrEnum):
    FOOD = "еда"
    TRANSPORT = "транспорт"
    HOUSING = "жильё"
    FUN = "развлечения"
    HEALTH = "здоровье"
    SHOPPING = "покупки"
    OTHER = "другое"


ALL_CATEGORIES: tuple[str, ...] = tuple(category.value for category in Category)


def normalize_category(value: str | None) -> Category:
    """Map free-form LLM output to one of the known categories."""
    raw = (value or "").strip().lower()
    if not raw:
        return Category.OTHER

    for category in Category:
        if raw == category.value:
            return category
    for category in Category:
        if category.value in raw:
            return category
    return Category.OTHER
