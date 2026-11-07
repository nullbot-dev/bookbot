"""Всё, что описывает конкретный салон: услуги, мастера, график, правила записи.
Чтобы адаптировать бота под другого клиента, достаточно поменять этот файл."""

from dataclasses import dataclass
from datetime import date, time, timedelta

NAME = "Барбершоп «Борода»"
TIMEZONE = "Europe/Moscow"

CONTACTS = (
    f"<b>{NAME}</b>\n\n"
    "📍 ул. Примерная, 10\n"
    "🕘 Пн–Сб 10:00–21:00, Вс 11:00–18:00\n"
    "📞 +7 (900) 000-00-00"
)


@dataclass(frozen=True)
class Service:
    title: str
    minutes: int
    price: int


# код услуги -> услуга
SERVICES: dict[str, Service] = {
    "cut": Service("Мужская стрижка", 60, 1500),
    "beard": Service("Оформление бороды", 30, 800),
    "combo": Service("Стрижка + борода", 90, 2100),
    "kids": Service("Детская стрижка", 45, 1000),
}

# код мастера -> имя
MASTERS: dict[str, str] = {
    "alex": "Алексей",
    "ivan": "Иван",
}

# день недели (0 — понедельник) -> часы работы; None — выходной
WORK_HOURS: dict[int, tuple[time, time] | None] = {
    0: (time(10), time(21)),
    1: (time(10), time(21)),
    2: (time(10), time(21)),
    3: (time(10), time(21)),
    4: (time(10), time(21)),
    5: (time(10), time(21)),
    6: (time(11), time(18)),
}

SLOT_STEP_MIN = 30        # шаг сетки времени
DAYS_AHEAD = 14           # на сколько дней вперёд можно записаться
MIN_LEAD_MIN = 60         # не раньше чем через час от текущего момента
CANCEL_LIMIT_MIN = 120    # клиент может отменить запись не позже чем за 2 часа


def booking_days(today: date) -> list[date]:
    """Рабочие дни, на которые открыта запись."""
    days = (today + timedelta(days=i) for i in range(DAYS_AHEAD))
    return [d for d in days if WORK_HOURS.get(d.weekday())]
