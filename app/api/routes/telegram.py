import asyncio
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import Settings

logger = logging.getLogger(__name__)


def create_router(settings: Settings) -> APIRouter:
    router = APIRouter(tags=["telegram"])

    @router.post(settings.telegram_webhook_path, include_in_schema=False)
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict:
        runtime = getattr(request.app.state, "bot_runtime", None)
        if runtime is None:
            raise HTTPException(status_code=503, detail="Telegram bot is disabled")

        if (
            settings.telegram_webhook_secret
            and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
        ):
            raise HTTPException(status_code=401, detail="Invalid secret token")

        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON") from None

        task = asyncio.create_task(runtime.feed_update(payload))
        tasks: set[asyncio.Task] = request.app.state.bot_tasks
        tasks.add(task)
        task.add_done_callback(tasks.discard)

        return {"ok": True}

    return router
