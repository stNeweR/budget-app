import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.errors import AppError


class TooManyRequests(AppError):
    status_code = 429
    default_message = "Слишком много попыток. Попробуйте немного позже"


_attempts: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


def rate_limit(name: str, limit: int, window_seconds: int):
    """Simple per-process limiter for credential endpoints."""

    def dependency(request: Request) -> None:
        key = f"{name}:{_client_ip(request)}"
        now = time.monotonic()
        bucket = _attempts[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            raise TooManyRequests()
        bucket.append(now)

    return dependency
