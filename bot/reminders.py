"""Фоновая задача: напоминания клиентам и закрытие прошедших записей."""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from . import keyboards as kb
from . import texts
from .db import Database, parse
from .slots import now

log = logging.getLogger(__name__)

CHECK_EVERY_SEC = 60


def due_kind(booking: dict, current: datetime) -> str | None:
    """Какое напоминание пора отправить: '24', '2' или ничего.

    Напоминание за сутки не шлём, если клиент записался меньше чем за сутки до визита, — он и так помнит.
    То же для напоминания за 2 часа."""
    left = booking["start"] - current
    lead = booking["start"] - parse(booking["created_at"])
    if not booking["reminded_2"] and left <= timedelta(hours=2) and lead > timedelta(hours=2):
        return "2"
    if not booking["reminded_24"] and timedelta(hours=2) < left <= timedelta(hours=24) and lead > timedelta(hours=24):
        return "24"
    return None


async def tick(bot: Bot, db: Database, current: datetime) -> None:
    await db.mark_done(current)
    for booking in await db.pending_reminders(current):
        kind = due_kind(booking, current)
        if kind is None:
            continue
        try:
            await bot.send_message(booking["user_id"], texts.reminder(booking, kind), reply_markup=kb.reminder(booking["id"]))
        except TelegramAPIError as exc:
            log.warning("Не удалось напомнить о записи %s: %s", booking["id"], exc)
        # помечаем даже при ошибке, чтобы не слать повторно каждую минуту
        await db.mark_reminded(booking["id"], kind)
        if kind == "2":
            await db.mark_reminded(booking["id"], "24")


async def reminder_loop(bot: Bot, db: Database) -> None:
    while True:
        try:
            await tick(bot, db, now())
        except Exception:
            log.exception("Ошибка в цикле напоминаний")
        await asyncio.sleep(CHECK_EVERY_SEC)
