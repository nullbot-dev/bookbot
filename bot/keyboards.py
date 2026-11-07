from datetime import date, datetime, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import salon, texts

BTN_BOOK = "📅 Записаться"
BTN_MY = "🗓 Мои записи"
BTN_PRICES = "💈 Услуги и цены"
BTN_CONTACTS = "📍 Контакты"
BTN_ADMIN = "🛠 Админ-панель"
BTN_CANCEL = "❌ Отмена"
BTN_SEND_CONTACT = "📱 Отправить мой номер"


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_BOOK)],
        [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_PRICES)],
        [KeyboardButton(text=BTN_CONTACTS)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_SEND_CONTACT, request_contact=True)], [KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def services() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code, s in salon.SERVICES.items():
        b.button(text=f"{s.title} · {texts.rub(s.price)}", callback_data=f"svc:{code}")
    b.button(text="✖️ Закрыть", callback_data="bk:no")
    b.adjust(1)
    return b.as_markup()


def masters() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎲 Любой свободный", callback_data="mst:any")
    for code, name in salon.MASTERS.items():
        b.button(text=name, callback_data=f"mst:{code}")
    b.button(text="◀️ Назад", callback_data="back:service")
    b.adjust(1, 2, 1)
    return b.as_markup()


def days(available: list[date], today: date) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for day in available:
        b.button(text=texts.day_short(day, today), callback_data=f"day:{day.isoformat()}")
    b.adjust(3)
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back:master"))
    return b.as_markup()


def slots(times: list[datetime]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in times:
        b.button(text=f"{t:%H:%M}", callback_data=f"slot:{t:%H%M}")
    b.adjust(4)
    b.row(InlineKeyboardButton(text="◀️ Другой день", callback_data="back:day"))
    return b.as_markup()


def confirm() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Записаться", callback_data="bk:ok")
    b.button(text="◀️ Другое время", callback_data="back:day")
    b.button(text="❌ Отменить", callback_data="bk:no")
    b.adjust(1)
    return b.as_markup()


def my_bookings(bookings: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for item in bookings:
        b.button(text=f"❌ Отменить №{item['id']} ({item['start']:%d.%m %H:%M})", callback_data=f"my:cancel:{item['id']}")
    b.adjust(1)
    return b.as_markup()


def reminder(booking_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Приду", callback_data=f"rem:ok:{booking_id}")
    b.button(text="❌ Отменить запись", callback_data=f"my:cancel:{booking_id}")
    b.adjust(2)
    return b.as_markup()


def schedule(day: date, bookings: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for item in bookings:
        b.button(text=f"❌ Отменить №{item['id']} · {item['start']:%H:%M}", callback_data=f"adm:cancel:{item['id']}")
    b.adjust(1)
    b.row(
        InlineKeyboardButton(text="◀️", callback_data=f"sch:{(day - timedelta(days=1)).isoformat()}"),
        InlineKeyboardButton(text="Сегодня", callback_data="sch:today"),
        InlineKeyboardButton(text="▶️", callback_data=f"sch:{(day + timedelta(days=1)).isoformat()}"),
    )
    return b.as_markup()


def admin_booking(booking_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=f"❌ Отменить №{booking_id}", callback_data=f"adm:cancel:{booking_id}")
    return b.as_markup()
