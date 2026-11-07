import asyncio
from datetime import date, datetime

import aiosqlite
from aiogram.types import User

from .slots import Interval

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    username    TEXT,
    full_name   TEXT NOT NULL,
    phone       TEXT,
    created_at  TEXT NOT NULL
);

-- start/end хранятся как 'YYYY-MM-DDTHH:MM' по времени салона: такие строки правильно сравниваются как текст.
CREATE TABLE IF NOT EXISTS bookings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    service      TEXT NOT NULL,
    master       TEXT NOT NULL,
    price        INTEGER NOT NULL,
    start        TEXT NOT NULL,
    end          TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'done')),
    reminded_24  INTEGER NOT NULL DEFAULT 0,
    reminded_2   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bookings_start ON bookings(status, start);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id, status);
"""


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def parse(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


def _booking(row: aiosqlite.Row) -> dict:
    data = dict(row)
    data["start"] = parse(data["start"])
    data["end"] = parse(data["end"])
    return data


BOOKING_SELECT = """
    SELECT bookings.*, users.full_name, users.username, users.phone
    FROM bookings JOIN users ON users.id = bookings.user_id
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        # между проверкой «время свободно» и записью не должно вклиниться другое бронирование
        self._booking_lock = asyncio.Lock()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("База не подключена: вызовите connect()")
        return self._conn

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ---------- пользователи ----------

    async def upsert_user(self, user: User, now: datetime) -> None:
        await self.conn.execute(
            """
            INSERT INTO users (id, username, full_name, created_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET username = excluded.username, full_name = excluded.full_name
            """,
            (user.id, user.username, user.full_name, iso(now)),
        )
        await self.conn.commit()

    async def get_user(self, user_id: int) -> dict | None:
        async with self.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def set_phone(self, user_id: int, phone: str) -> None:
        await self.conn.execute("UPDATE users SET phone = ? WHERE id = ?", (phone, user_id))
        await self.conn.commit()

    # ---------- записи ----------

    async def busy(self, day: date) -> dict[str, list[Interval]]:
        """Занятое время мастеров в этот день."""
        async with self.conn.execute(
            "SELECT master, start, end FROM bookings WHERE status = 'active' AND start LIKE ?",
            (f"{day.isoformat()}%",),
        ) as cursor:
            rows = await cursor.fetchall()
        result: dict[str, list[Interval]] = {}
        for row in rows:
            result.setdefault(row["master"], []).append((parse(row["start"]), parse(row["end"])))
        return result

    async def create_booking(
        self, user_id: int, service: str, master: str, price: int, start: datetime, end: datetime, now: datetime
    ) -> dict | None:
        """Создаёт запись. Возвращает None, если у мастера это время уже занято."""
        async with self._booking_lock:
            async with self.conn.execute(
                "SELECT 1 FROM bookings WHERE status = 'active' AND master = ? AND start < ? AND end > ?",
                (master, iso(end), iso(start)),
            ) as cursor:
                if await cursor.fetchone():
                    return None
            cursor = await self.conn.execute(
                """
                INSERT INTO bookings (user_id, service, master, price, start, end, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, service, master, price, iso(start), iso(end), iso(now)),
            )
            await self.conn.commit()
        return await self.get_booking(cursor.lastrowid)

    async def get_booking(self, booking_id: int) -> dict | None:
        async with self.conn.execute(f"{BOOKING_SELECT} WHERE bookings.id = ?", (booking_id,)) as cursor:
            row = await cursor.fetchone()
        return _booking(row) if row else None

    async def upcoming_for_user(self, user_id: int, now: datetime) -> list[dict]:
        async with self.conn.execute(
            f"{BOOKING_SELECT} WHERE bookings.user_id = ? AND status = 'active' AND start > ? ORDER BY start",
            (user_id, iso(now)),
        ) as cursor:
            return [_booking(row) for row in await cursor.fetchall()]

    async def day_bookings(self, day: date) -> list[dict]:
        async with self.conn.execute(
            f"{BOOKING_SELECT} WHERE status = 'active' AND start LIKE ? ORDER BY start, master",
            (f"{day.isoformat()}%",),
        ) as cursor:
            return [_booking(row) for row in await cursor.fetchall()]

    async def cancel(self, booking_id: int) -> None:
        await self.conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
        await self.conn.commit()

    async def mark_done(self, now: datetime) -> None:
        await self.conn.execute("UPDATE bookings SET status = 'done' WHERE status = 'active' AND end <= ?", (iso(now),))
        await self.conn.commit()

    async def pending_reminders(self, now: datetime) -> list[dict]:
        async with self.conn.execute(
            f"{BOOKING_SELECT} WHERE status = 'active' AND start > ? AND (reminded_24 = 0 OR reminded_2 = 0)",
            (iso(now),),
        ) as cursor:
            return [_booking(row) for row in await cursor.fetchall()]

    async def mark_reminded(self, booking_id: int, kind: str) -> None:
        column = {"24": "reminded_24", "2": "reminded_2"}[kind]
        await self.conn.execute(f"UPDATE bookings SET {column} = 1 WHERE id = ?", (booking_id,))
        await self.conn.commit()

    async def all_bookings(self) -> list[dict]:
        async with self.conn.execute(f"{BOOKING_SELECT} ORDER BY start") as cursor:
            return [_booking(row) for row in await cursor.fetchall()]

    async def stats(self, now: datetime) -> dict:
        today = now.date().isoformat()

        async def scalar(sql: str, *params) -> int:
            async with self.conn.execute(sql, params) as cursor:
                return (await cursor.fetchone())[0] or 0

        return {
            "users": await scalar("SELECT COUNT(*) FROM users"),
            "upcoming": await scalar("SELECT COUNT(*) FROM bookings WHERE status = 'active' AND start > ?", iso(now)),
            "today": await scalar("SELECT COUNT(*) FROM bookings WHERE status != 'cancelled' AND start LIKE ?", f"{today}%"),
            "done": await scalar("SELECT COUNT(*) FROM bookings WHERE status = 'done'"),
            "cancelled": await scalar("SELECT COUNT(*) FROM bookings WHERE status = 'cancelled'"),
            "revenue": await scalar("SELECT SUM(price) FROM bookings WHERE status = 'done'"),
        }
