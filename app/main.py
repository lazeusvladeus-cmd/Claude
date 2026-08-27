"""Entry point: wires up the bot, middleware, routers, and background scheduler."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import settings
from app.handlers import callbacks, commands, text, voice
from app.logging_config import setup_logging
from app.scheduler import start_scheduler
from app.security import AllowlistMiddleware

logger = logging.getLogger(__name__)

_BOT_COMMANDS = [
    BotCommand(command="stats", description="Spending in the last 7 days"),
    BotCommand(command="month", description="Last 30 days, vs the month before"),
    BotCommand(command="advice", description="Personalized savings suggestions"),
    BotCommand(command="today", description="Remaining calendar events today"),
    BotCommand(command="budget", description="Check your monthly budget usage"),
    BotCommand(command="setbudget", description="Set or change your monthly budget"),
    BotCommand(command="undo", description="Remove the most recent transaction"),
    BotCommand(command="sheet", description="Link to your Google Sheet ledger"),
    BotCommand(command="help", description="What this bot can do"),
]


async def main() -> None:
    setup_logging()
    settings.ensure_secret_dirs_exist()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.message.middleware(AllowlistMiddleware())
    dp.callback_query.middleware(AllowlistMiddleware())

    # Order matters: commands before the catch-all text handler.
    dp.include_router(commands.router)
    dp.include_router(voice.router)
    dp.include_router(callbacks.router)
    dp.include_router(text.router)

    scheduler = start_scheduler(bot)

    logger.info("Bot starting. Allowed users: %s", settings.allowed_user_ids)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_my_commands(_BOT_COMMANDS)
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down.")
