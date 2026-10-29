import logging
from contextlib import asynccontextmanager

from aiogram import Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.core.errors import Forbidden
from app.db.session import SessionFactory
from app.services.agent import AgentService
from app.services.bot import (
    commands_help,
    ensure_bot_user,
    format_start_result,
    invite_info,
    panel_link,
    start_bot_user,
)

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000
ALLOWED_UPDATES = ["message", "edited_message"]


@asynccontextmanager
async def session_scope():
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _telegram_name(message: Message) -> tuple[int, str, str]:
    sender = message.from_user
    if sender is None:
        raise ValueError("message has no sender")
    full_name = " ".join(part for part in (sender.first_name, sender.last_name) if part)
    return sender.id, sender.username or "", full_name


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_MESSAGE_LENGTH else text[: MAX_MESSAGE_LENGTH - 1] + "…"


async def _reply(message: Message, text: str) -> None:
    try:
        await message.reply(_truncate(text))
    except TelegramBadRequest:
        logger.exception("failed to send Telegram reply")


async def _replace(placeholder: Message, text: str) -> None:
    try:
        await placeholder.edit_text(_truncate(text))
    except TelegramBadRequest:
        logger.warning("failed to edit placeholder, sending a new message")
        await _reply(placeholder, text)


async def _current_user(db, message: Message):
    telegram_id, username, full_name = _telegram_name(message)
    return await ensure_bot_user(
        db,
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
    )


async def handle_start(message: Message, command: CommandObject) -> None:
    if message.from_user is None:
        return
    async with session_scope() as db:
        user = await _current_user(db, message)
        result = await start_bot_user(db, user, command.args or "")
        reply = format_start_result(result)
    await _reply(message, reply)


async def handle_invite(message: Message) -> None:
    if message.from_user is None or message.bot is None:
        return
    async with session_scope() as db:
        user = await _current_user(db, message)
        info = await invite_info(db, user)
        bot_me = await message.bot.me()
        link = f"https://t.me/{bot_me.username}?start={info.family.invite_code}"
        if info.head.id == user.id:
            reply = f"Отправьте эту ссылку тем, кого хотите добавить в вашу семью:\n{link}"
        else:
            reply = (
                f"Отправьте эту ссылку тем, кого хотите добавить в семью "
                f"(глава — {info.head.display_name}):\n{link}"
            )
    await _reply(message, reply)


async def handle_panel(message: Message) -> None:
    if message.from_user is None:
        return
    async with session_scope() as db:
        user = await _current_user(db, message)
        try:
            link = await panel_link(db, user)
        except Forbidden:
            link = None
    if link:
        reply = (
            "Веб-панель расходов:\n"
            f"{link}\n\n"
            "Ссылка одноразовая и действует несколько минут. После входа задайте "
            "email и пароль, чтобы входить обычным способом."
        )
    else:
        reply = "Веб-панель доступна только главе семьи. Вы можете пользоваться ботом."
    await _reply(message, reply)


async def handle_text(message: Message) -> None:
    if message.from_user is None or not message.text:
        return

    text = message.text.strip()
    if text.startswith("/"):
        await _reply(message, commands_help())
        return

    try:
        placeholder = await message.answer(
            "Запрос в обработке...",
            reply_to_message_id=message.message_id,
        )
    except TelegramBadRequest:
        logger.exception("failed to send processing placeholder")
        placeholder = None

    try:
        async with session_scope() as db:
            user = await _current_user(db, message)
            reply = await AgentService(db).handle(user, text)
    except Exception:
        logger.exception("agent failed to process message")
        reply = "Извините, не удалось обработать запрос. Попробуйте ещё раз."

    if placeholder is not None:
        await _replace(placeholder, reply)
    else:
        await _reply(message, reply)


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.register(handle_start, Command("start"))
    dispatcher.message.register(handle_invite, Command("invite"))
    dispatcher.message.register(handle_panel, Command("panel"))
    dispatcher.message.register(handle_text, F.text)
    dispatcher.edited_message.register(handle_text, F.text)
    return dispatcher
