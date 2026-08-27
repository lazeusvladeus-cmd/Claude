"""Entry point: wires up the bot, middleware, routers, and background scheduler."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.handlers import callbacks, commands, text, voice
from app.logging_config import setup_logging
from app.scheduler import start_scheduler
from app.security import AllowlistMiddleware

logger = logging.getLogger(__name__)


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
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down.")
