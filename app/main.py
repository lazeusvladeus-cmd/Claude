"""Entry point: wires up the bot, middleware, routers, and background scheduler."""
from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import settings
from app.handlers import callbacks, commands, text, voice
from app.logging_config import setup_logging
from app.scheduler import start_scheduler
from app.security import AllowlistMiddleware
from app.webapp.server import app as webapp

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
    BotCommand(command="dashboard", description="Open the visual dashboard"),
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

    web_config = uvicorn.Config(
        webapp, host="0.0.0.0", port=settings.port, log_level=settings.log_level.lower()
    )
    web_server = uvicorn.Server(web_config)
    # uvicorn installs its own SIGINT/SIGTERM handlers by default, which would let a
    # Ctrl+C stop only the web server while bot polling kept running — the manual
    # wait/cancel below handles a clean shutdown of both instead.
    web_config.install_signal_handlers = False

    logger.info("Bot starting. Allowed users: %s", settings.allowed_user_ids)
    if settings.miniapp_url:
        logger.info("Dashboard enabled at %s (serving on port %s)", settings.miniapp_url, settings.port)
    else:
        logger.info("MINIAPP_URL not set — dashboard button hidden, but the server still runs on port %s", settings.port)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_my_commands(_BOT_COMMANDS)

        bot_task = asyncio.create_task(dp.start_polling(bot))
        web_task = asyncio.create_task(web_server.serve())

        # If either side stops (error, or the process receiving SIGINT/SIGTERM causes
        # asyncio.run to raise), tear the other down too instead of leaving it running.
        done, pending = await asyncio.wait({bot_task, web_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down.")
