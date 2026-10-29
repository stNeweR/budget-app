class AppError(Exception):
    """Base domain error translated into a JSON API response."""

    status_code = 400
    default_message = "Некорректный запрос"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class InvalidCredentials(AppError):
    status_code = 401
    default_message = "Неверные учётные данные"


class Forbidden(AppError):
    status_code = 403
    default_message = "Доступ запрещён"


class NotFound(AppError):
    status_code = 404
    default_message = "Не найдено"


class Conflict(AppError):
    status_code = 409
    default_message = "Конфликт данных"


class InvalidInput(AppError):
    status_code = 400
    default_message = "Некорректные данные"
