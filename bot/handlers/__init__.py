from aiogram import Router

from . import admin, user


def build_router() -> Router:
    root = Router(name="root")
    # админский роутер первым: его команды не должны попадать в клиентский fallback
    root.include_routers(admin.router, user.router)
    return root
