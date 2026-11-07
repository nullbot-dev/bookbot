"""Расчёт свободного времени. Чистые функции без базы и Telegram — их легко проверять тестами.

Время везде «наивное» (без часового пояса) и считается в часовом поясе салона."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import salon

Interval = tuple[datetime, datetime]


def now() -> datetime:
    return datetime.now(ZoneInfo(salon.TIMEZONE)).replace(tzinfo=None, second=0, microsecond=0)


def overlaps(start: datetime, end: datetime, busy: list[Interval]) -> bool:
    return any(start < b_end and end > b_start for b_start, b_end in busy)


def free_slots(
    day: date,
    minutes: int,
    busy_by_master: dict[str, list[Interval]],
    masters: list[str],
    current: datetime,
) -> dict[datetime, list[str]]:
    """Возвращает {время начала: [мастера, свободные на всю длительность услуги]} в порядке времени."""
    hours = salon.WORK_HOURS.get(day.weekday())
    if not hours:
        return {}

    opening = datetime.combine(day, hours[0])
    closing = datetime.combine(day, hours[1])
    earliest = current + timedelta(minutes=salon.MIN_LEAD_MIN)
    duration = timedelta(minutes=minutes)
    step = timedelta(minutes=salon.SLOT_STEP_MIN)

    result: dict[datetime, list[str]] = {}
    start = opening
    while start + duration <= closing:
        if start >= earliest:
            free = [m for m in masters if not overlaps(start, start + duration, busy_by_master.get(m, []))]
            if free:
                result[start] = free
        start += step
    return result
