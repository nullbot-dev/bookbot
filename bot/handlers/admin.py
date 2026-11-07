import csv
import io
from datetime import date

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message, TelegramObject

from .. import keyboards as kb
from .. import salon, texts
from ..config import Config
from ..db import Database
from ..slots import now


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, config: Config) -> bool:
        user = getattr(event, "from_user", None)
        return user is not None and user.id in config.admin_ids


router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

STATUS = {"active": "Активна", "cancelled": "Отменена", "done": "Проведена"}


@router.message(Command("admin"))
@router.message(F.text == kb.BTN_ADMIN)
async def admin_help(message: Message) -> None:
    await message.answer(texts.ADMIN_HELP)


@router.message(Command("schedule"))
async def schedule(message: Message, db: Database) -> None:
    day = now().date()
    bookings = await db.day_bookings(day)
    await message.answer(texts.day_schedule(day, bookings), reply_markup=kb.schedule(day, bookings))


async def show_day(callback: CallbackQuery, db: Database, day: date) -> None:
    bookings = await db.day_bookings(day)
    try:
        await callback.message.edit_text(texts.day_schedule(day, bookings), reply_markup=kb.schedule(day, bookings))
    except TelegramBadRequest:
        pass  # содержимое не изменилось


@router.callback_query(F.data.startswith("sch:"))
async def schedule_nav(callback: CallbackQuery, db: Database) -> None:
    value = callback.data.split(":", 1)[1]
    await show_day(callback, db, now().date() if value == "today" else date.fromisoformat(value))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cancel:"))
async def admin_cancel(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    booking = await db.get_booking(int(callback.data.rsplit(":", 1)[1]))
    if booking is None or booking["status"] != "active":
        await callback.answer("Запись уже отменена или прошла", show_alert=True)
        return

    await db.cancel(booking["id"])
    try:
        await bot.send_message(
            booking["user_id"],
            "😔 К сожалению, ваша запись отменена салоном.\n\n" + texts.booking_card(booking)
            + "\n\nПриносим извинения! Выберите другое время: «📅 Записаться».",
        )
        note = "Запись отменена, клиент уведомлён"
    except TelegramAPIError:
        note = "Запись отменена, но клиент заблокировал бота — позвоните ему"

    if callback.message.text and callback.message.text.startswith("Расписание"):
        await show_day(callback, db, booking["start"].date())
    else:
        await callback.message.edit_text(
            "🚫 <b>Отменена администратором</b>\n\n" + texts.booking_card(booking, with_client=True)
        )
    await callback.answer(note, show_alert=True)


@router.message(Command("stats"))
async def stats(message: Message, db: Database) -> None:
    await message.answer(texts.stats_text(await db.stats(now())))


@router.message(Command("export"))
async def export(message: Message, db: Database) -> None:
    bookings = await db.all_bookings()
    if not bookings:
        await message.answer("Записей пока нет.")
        return

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")  # ';' — чтобы Excel с русской локалью сразу разбил по колонкам
    writer.writerow(["№", "Статус", "Дата", "Время", "Услуга", "Мастер", "Цена", "Клиент", "Телефон", "Telegram"])
    for b in bookings:
        service = salon.SERVICES.get(b["service"])
        writer.writerow([
            b["id"],
            STATUS.get(b["status"], b["status"]),
            f"{b['start']:%d.%m.%Y}",
            f"{b['start']:%H:%M}–{b['end']:%H:%M}",
            service.title if service else b["service"],
            salon.MASTERS.get(b["master"], b["master"]),
            b["price"],
            b["full_name"],
            b.get("phone") or "",
            f"@{b['username']}" if b.get("username") else b["user_id"],
        ])

    file = BufferedInputFile(buffer.getvalue().encode("utf-8-sig"), filename="bookings.csv")
    await message.answer_document(file, caption=f"Всего записей: {len(bookings)}")
