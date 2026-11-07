import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    admin_chat_id: int | None
    db_path: str


def _parse_ids(raw: str) -> frozenset[int]:
    return frozenset(int(part) for part in raw.replace(" ", "").split(",") if part)


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан: скопируйте .env.example в .env и заполните его")

    admin_chat = os.getenv("ADMIN_CHAT_ID", "").strip()
    return Config(
        bot_token=token,
        admin_ids=_parse_ids(os.getenv("ADMIN_IDS", "")),
        admin_chat_id=int(admin_chat) if admin_chat else None,
        db_path=os.getenv("DB_PATH", "bookings.db"),
    )
