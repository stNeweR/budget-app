import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import BotCommand, Update

from app.bot.handlers import ALLOWED_UPDATES, build_dispatcher
from app.core.config import Settings
from app.services.bot import COMMANDS

logger = logging.getLogger(__name__)

DEFAULT_API_BASE = "https://api.telegram.org"


class BotRuntime:
    """Owns the aiogram bot and dispatcher lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        session = None
        if settings.telegram_api_base_url.rstrip("/") != DEFAULT_API_BASE:
            session = AiohttpSession(
                api=TelegramAPIServer.from_base(settings.telegram_api_base_url)
            )
        self.bot = Bot(token=settings.telegram_bot_token, session=session)
        self.dispatcher: Dispatcher = build_dispatcher()
        self._polling_task: asyncio.Task | None = None

    async def start(self) -> None:
        await self._register_commands()

        if self.settings.telegram_webhook_mode:
            url = (
                self.settings.telegram_webhook_url.rstrip("/") + self.settings.telegram_webhook_path
            )
            await self.bot.set_webhook(
                url=url,
                secret_token=self.settings.telegram_webhook_secret or None,
                allowed_updates=ALLOWED_UPDATES,
                drop_pending_updates=True,
            )
            logger.info("telegram bot started in webhook mode: %s", url)
            return

        await self.bot.delete_webhook(drop_pending_updates=False)
        self._polling_task = asyncio.create_task(
            self.dispatcher.start_polling(
                self.bot,
                handle_signals=False,
                allowed_updates=ALLOWED_UPDATES,
            )
        )
        logger.info("telegram bot started in long polling mode")

    async def stop(self) -> None:
        if self._polling_task is not None:
            self._polling_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._polling_task
            self._polling_task = None
        await self.bot.session.close()

    async def feed_update(self, payload: dict) -> None:
        try:
            update = Update.model_validate(payload)
        except Exception:
            logger.exception("invalid telegram update payload")
            return
        try:
            await self.dispatcher.feed_update(self.bot, update)
        except Exception:
            logger.exception("failed to process telegram update")

    async def _register_commands(self) -> None:
        try:
            await self.bot.set_my_commands(
                [
                    BotCommand(command=name, description=description)
                    for name, description in COMMANDS
                ]
            )
        except Exception:
            logger.warning("failed to register telegram bot commands", exc_info=True)


def create_runtime(settings: Settings) -> BotRuntime:
    return BotRuntime(settings)
