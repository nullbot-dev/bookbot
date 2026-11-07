from aiogram.fsm.state import State, StatesGroup


class Booking(StatesGroup):
    service = State()
    master = State()
    day = State()
    slot = State()
    phone = State()
    confirm = State()
