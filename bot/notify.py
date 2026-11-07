import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from .config import Config

log = logging.getLogger(__name__)


async def notify_admins(bot: Bot, config: Config, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Шлёт сообщение в админ-чат, а если он не задан — каждому администратору лично."""
    targets = [config.admin_chat_id] if config.admin_chat_id else sorted(config.admin_ids)
    if not targets:
        log.warning("Некому отправить уведомление: не заданы ни ADMIN_CHAT_ID, ни ADMIN_IDS")
    for chat_id in targets:
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
        except TelegramAPIError as exc:
            log.error("Не удалось уведомить %s: %s", chat_id, exc)
