from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🃏 Получить карточку"), KeyboardButton(text="💼 Мои карты")],
            [KeyboardButton(text="☁️ Меню"), KeyboardButton(text="⚙️ Настройки")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )
    return keyboard