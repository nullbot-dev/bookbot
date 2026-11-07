import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from .config import load_config
from .db import Database
from .handlers import build_router
from .reminders import reminder_loop

COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="book", description="Записаться"),
    BotCommand(command="my", description="Мои записи"),
    BotCommand(command="cancel", description="Отменить действие"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = load_config()
    db = Database(config.db_path)
    await db.connect()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage(), db=db, config=config)
    dp.include_router(build_router())

    await bot.set_my_commands(COMMANDS)
    reminders = asyncio.create_task(reminder_loop(bot, db))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        reminders.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reminders
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
