from datetime import date, datetime, timedelta
from html import escape

from . import salon

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def rub(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"


def day_label(day: date) -> str:
    """«Пн, 10 ноября»"""
    return f"{WEEKDAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]}"


def day_short(day: date, today: date) -> str:
    """Подпись на кнопке: «Сегодня», «Завтра» или «Пн 10.11»."""
    delta = (day - today).days
    if delta == 0:
        return "Сегодня"
    if delta == 1:
        return "Завтра"
    return f"{WEEKDAYS[day.weekday()]} {day:%d.%m}"


def period(start: datetime, end: datetime) -> str:
    return f"{day_label(start.date())}, {start:%H:%M}–{end:%H:%M}"


def greeting(first_name: str) -> str:
    return (
        f"Здравствуйте, {escape(first_name)}! 👋\n\n"
        f"Это бот <b>{salon.NAME}</b>. Здесь можно записаться к мастеру в пару нажатий, "
        "посмотреть или отменить свои записи. Напомню о визите заранее."
    )


def price_list() -> str:
    lines = [f"• {s.title} — <b>{rub(s.price)}</b>, {s.minutes} мин" for s in salon.SERVICES.values()]
    masters = ", ".join(salon.MASTERS.values())
    return f"<b>Услуги и цены</b>\n\n" + "\n".join(lines) + f"\n\nМастера: {masters}"


def summary(service: str, master: str, start: datetime) -> str:
    s = salon.SERVICES[service]
    end = start + timedelta(minutes=s.minutes)
    return (
        "<b>Проверьте запись</b>\n\n"
        f"💈 {s.title}\n"
        f"👤 Мастер: {salon.MASTERS[master]}\n"
        f"📅 {period(start, end)}\n"
        f"💰 {rub(s.price)}"
    )


def booking_card(b: dict, with_client: bool = False) -> str:
    s = salon.SERVICES.get(b["service"])
    title = s.title if s else b["service"]
    text = (
        f"<b>Запись №{b['id']}</b>\n"
        f"💈 {title}\n"
        f"👤 Мастер: {salon.MASTERS.get(b['master'], b['master'])}\n"
        f"📅 {period(b['start'], b['end'])}\n"
        f"💰 {rub(b['price'])}"
    )
    if with_client:
        username = f" · @{b['username']}" if b.get("username") else ""
        text += f"\n\nКлиент: {escape(b['full_name'])}{escape(username)}\nТелефон: <code>{escape(b.get('phone') or '—')}</code>"
    return text


def reminder(b: dict, kind: str) -> str:
    when = "завтра" if kind == "24" else "через 2 часа"
    return f"⏰ Напоминаем: {when} у вас запись.\n\n" + booking_card(b) + f"\n\n{salon.CONTACTS}"


def day_schedule(day: date, bookings: list[dict]) -> str:
    head = f"<b>Расписание: {day_label(day)}</b>"
    if not salon.WORK_HOURS.get(day.weekday()):
        return f"{head}\n\nВыходной."
    if not bookings:
        return f"{head}\n\nЗаписей нет."
    lines = []
    for b in bookings:
        s = salon.SERVICES.get(b["service"])
        lines.append(
            f"<b>{b['start']:%H:%M}–{b['end']:%H:%M}</b> · {salon.MASTERS.get(b['master'], b['master'])}\n"
            f"   {s.title if s else b['service']} · №{b['id']}\n"
            f"   {escape(b['full_name'])}, <code>{escape(b.get('phone') or '—')}</code>"
        )
    total = sum(b["price"] for b in bookings)
    return f"{head}\n\n" + "\n\n".join(lines) + f"\n\nЗаписей: {len(bookings)} · на сумму {rub(total)}"


def stats_text(s: dict) -> str:
    return (
        "<b>Статистика</b>\n\n"
        f"Клиентов в боте: {s['users']}\n"
        f"Предстоящих записей: {s['upcoming']}\n"
        f"Записей на сегодня: {s['today']}\n"
        f"Проведено визитов: {s['done']}\n"
        f"Отменено: {s['cancelled']}\n"
        f"Выручка по проведённым визитам: {rub(s['revenue'])}"
    )


ADMIN_HELP = (
    "<b>Админ-панель</b>\n\n"
    "/schedule — расписание по дням, отмена записей\n"
    "/stats — статистика\n"
    "/export — все записи в CSV для Excel"
)
