import re
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import keyboards as kb
from .. import salon, texts
from ..config import Config
from ..db import Database
from ..notify import notify_admins
from ..slots import free_slots, now
from ..states import Booking

router = Router(name="user")
# Клиентская часть работает только в личке, чтобы бот не отвечал на сообщения в админ-чате.
router.message.filter(F.chat.type == "private")


def normalize_phone(raw: str) -> str | None:
    """Приводит номер к виду +79001234567. Возвращает None, если это не похоже на телефон."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "7" + digits
    elif len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if not 11 <= len(digits) <= 15:
        return None
    return "+" + digits


async def show_main_menu(message: Message, config: Config, text: str) -> None:
    await message.answer(text, reply_markup=kb.main_menu(message.chat.id in config.admin_ids))


async def slots_for(db: Database, data: dict, day: date) -> dict[datetime, list[str]]:
    masters = [data["master"]] if data.get("master") else list(salon.MASTERS)
    return free_slots(day, salon.SERVICES[data["service"]].minutes, await db.busy(day), masters, now())


async def available_days(db: Database, data: dict) -> list[date]:
    today = now().date()
    return [day for day in salon.booking_days(today) if await slots_for(db, data, day)]


# ---------- главное меню ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    await state.clear()
    await db.upsert_user(message.from_user, now())
    await show_main_menu(message, config, texts.greeting(message.from_user.first_name))


@router.message(StateFilter("*"), Command("cancel"))
@router.message(StateFilter("*"), F.text == kb.BTN_CANCEL)
async def cancel(message: Message, state: FSMContext, config: Config) -> None:
    await state.clear()
    await show_main_menu(message, config, "Запись отменена. Чем ещё помочь?")


@router.message(F.text == kb.BTN_PRICES)
async def prices(message: Message) -> None:
    await message.answer(texts.price_list())


@router.message(F.text == kb.BTN_CONTACTS)
async def contacts(message: Message) -> None:
    await message.answer(salon.CONTACTS)


@router.message(Command("my"))
@router.message(F.text == kb.BTN_MY)
async def my_bookings(message: Message, db: Database) -> None:
    bookings = await db.upcoming_for_user(message.from_user.id, now())
    if not bookings:
        await message.answer("У вас нет предстоящих записей. Нажмите «📅 Записаться», чтобы выбрать время.")
        return
    cards = "\n\n".join(texts.booking_card(b) for b in bookings)
    await message.answer(f"<b>Ваши записи</b>\n\n{cards}", reply_markup=kb.my_bookings(bookings))


@router.callback_query(F.data.startswith("my:cancel:"))
async def my_cancel(callback: CallbackQuery, db: Database, config: Config, bot: Bot) -> None:
    booking = await db.get_booking(int(callback.data.rsplit(":", 1)[1]))
    if booking is None or booking["user_id"] != callback.from_user.id:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    if booking["status"] != "active":
        await callback.answer("Эта запись уже отменена или прошла", show_alert=True)
        return
    if booking["start"] - now() < timedelta(minutes=salon.CANCEL_LIMIT_MIN):
        await callback.answer(
            "До визита меньше 2 часов, отменить через бота уже нельзя. Пожалуйста, позвоните нам.", show_alert=True
        )
        return

    await db.cancel(booking["id"])
    await callback.message.edit_text(f"Запись №{booking['id']} отменена. Будем рады видеть вас в другой раз!")
    await notify_admins(bot, config, "🚫 <b>Клиент отменил запись</b>\n\n" + texts.booking_card(booking, with_client=True))
    await callback.answer()


@router.callback_query(F.data.startswith("rem:ok:"))
async def reminder_ok(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Отлично, ждём вас!")


# ---------- запись ----------

@router.message(Command("book"))
@router.message(F.text == kb.BTN_BOOK)
async def book_start(message: Message, state: FSMContext, db: Database) -> None:
    await db.upsert_user(message.from_user, now())
    await state.clear()
    await state.set_state(Booking.service)
    await message.answer("Выберите услугу:", reply_markup=kb.services())


async def ask_service(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Booking.service)
    await callback.message.edit_text("Выберите услугу:", reply_markup=kb.services())


async def ask_master(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(Booking.master)
    await callback.message.edit_text(
        f"💈 {salon.SERVICES[data['service']].title}\n\nК какому мастеру записать?", reply_markup=kb.masters()
    )


async def ask_day(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    days = await available_days(db, data)
    await state.set_state(Booking.day)
    master = salon.MASTERS.get(data.get("master"), "любой свободный")
    head = f"💈 {salon.SERVICES[data['service']].title}\n👤 Мастер: {master}\n\n"
    if not days:
        await callback.message.edit_text(
            head + "К сожалению, в ближайшие две недели свободного времени нет. Попробуйте другого мастера.",
            reply_markup=kb.masters(),
        )
        await state.set_state(Booking.master)
        return
    await callback.message.edit_text(head + "Выберите день:", reply_markup=kb.days(days, now().date()))


async def ask_slot(callback: CallbackQuery, state: FSMContext, db: Database, day: date) -> None:
    data = await state.get_data()
    slots = await slots_for(db, data, day)
    if not slots:
        await callback.answer("На этот день свободного времени уже нет", show_alert=True)
        await ask_day(callback, state, db)
        return
    await state.update_data(day=day.isoformat())
    await state.set_state(Booking.slot)
    await callback.message.edit_text(
        f"📅 {texts.day_label(day)}\n\nВыберите время:", reply_markup=kb.slots(list(slots))
    )


async def ask_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(Booking.confirm)
    master = data.get("master") or data["auto_master"]
    await message.answer(
        texts.summary(data["service"], master, datetime.fromisoformat(data["start"])), reply_markup=kb.confirm()
    )


@router.callback_query(Booking.service, F.data.startswith("svc:"))
async def pick_service(callback: CallbackQuery, state: FSMContext) -> None:
    code = callback.data.split(":", 1)[1]
    if code not in salon.SERVICES:
        await callback.answer("Неизвестная услуга", show_alert=True)
        return
    await state.update_data(service=code)
    await ask_master(callback, state)
    await callback.answer()


@router.callback_query(Booking.master, F.data.startswith("mst:"))
async def pick_master(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    code = callback.data.split(":", 1)[1]
    if code != "any" and code not in salon.MASTERS:
        await callback.answer("Неизвестный мастер", show_alert=True)
        return
    await state.update_data(master=None if code == "any" else code)
    await ask_day(callback, state, db)
    await callback.answer()


@router.callback_query(Booking.day, F.data.startswith("day:"))
async def pick_day(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await ask_slot(callback, state, db, date.fromisoformat(callback.data.split(":", 1)[1]))
    await callback.answer()


@router.callback_query(Booking.slot, F.data.startswith("slot:"))
async def pick_slot(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    day = date.fromisoformat(data["day"])
    hhmm = callback.data.split(":", 1)[1]
    start = datetime.combine(day, datetime.strptime(hhmm, "%H%M").time())

    slots = await slots_for(db, data, day)
    if start not in slots:
        await callback.answer("Это время только что заняли, выберите другое", show_alert=True)
        await ask_slot(callback, state, db, day)
        return

    await state.update_data(start=start.isoformat(), auto_master=slots[start][0])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()

    user = await db.get_user(callback.from_user.id)
    if user and user.get("phone"):
        await ask_confirm(callback.message, state)
        return
    await state.set_state(Booking.phone)
    await callback.message.answer(
        "Оставьте номер телефона, чтобы мастер мог связаться с вами при необходимости.",
        reply_markup=kb.phone_kb(),
    )


@router.message(Booking.phone, F.contact)
@router.message(Booking.phone, F.text)
async def enter_phone(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    phone = normalize_phone(message.contact.phone_number if message.contact else message.text)
    if phone is None:
        await message.answer("Не похоже на номер телефона. Пример: +7 900 123-45-67")
        return
    await db.set_phone(message.from_user.id, phone)
    await show_main_menu(message, config, "Спасибо, номер сохранён.")
    await ask_confirm(message, state)


@router.callback_query(Booking.confirm, F.data == "bk:ok")
async def confirm_booking(callback: CallbackQuery, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    data = await state.get_data()
    service = salon.SERVICES[data["service"]]
    start = datetime.fromisoformat(data["start"])
    end = start + timedelta(minutes=service.minutes)

    # Если мастер «любой», пробуем всех свободных по очереди: пока клиент думал, кого-то могли занять.
    day = start.date()
    candidates = [data["master"]] if data.get("master") else (await slots_for(db, data, day)).get(start, [])
    booking = None
    for master in candidates:
        booking = await db.create_booking(callback.from_user.id, data["service"], master, service.price, start, end, now())
        if booking:
            break

    if booking is None:
        await callback.answer("Это время только что заняли, выберите другое", show_alert=True)
        await ask_slot(callback, state, db, day)
        return

    await state.clear()
    await callback.message.edit_text("✅ <b>Вы записаны!</b>\n\n" + texts.booking_card(booking) + "\n\nНапомню о визите заранее.")
    await notify_admins(
        bot, config, "🆕 <b>Новая запись</b>\n\n" + texts.booking_card(booking, with_client=True),
        reply_markup=kb.admin_booking(booking["id"]),
    )
    await callback.answer()


@router.callback_query(StateFilter(Booking), F.data.startswith("back:"))
async def go_back(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    target = callback.data.split(":", 1)[1]
    if target == "service":
        await ask_service(callback, state)
    elif target == "master":
        await ask_master(callback, state)
    else:
        await ask_day(callback, state, db)
    await callback.answer()


@router.callback_query(StateFilter(Booking), F.data == "bk:no")
async def booking_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Запись отменена. Если передумаете — нажмите «📅 Записаться».")
    await callback.answer()


@router.callback_query(F.data.regexp(r"^(svc|mst|day|slot|bk|back):"))
async def stale_button(callback: CallbackQuery) -> None:
    await callback.answer("Эта форма уже неактуальна. Начните запись заново из меню.", show_alert=True)


@router.message(StateFilter(Booking))
async def wrong_input(message: Message) -> None:
    await message.answer("Пожалуйста, выберите вариант кнопкой выше или нажмите «❌ Отмена».")


@router.message()
async def fallback(message: Message, config: Config) -> None:
    await show_main_menu(message, config, "Не понял вас. Воспользуйтесь меню ниже 👇")
