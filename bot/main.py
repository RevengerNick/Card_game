import json, os
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from datetime import datetime, timedelta

from bot.dev import router as router_development
from bot.handlers.mainMenu import dp as router_main_menu, menu_pass

from bot.card_database import db

from bot.card_generator import generate_random_cards

# Загрузка конфигурации
file_path = os.getenv('python_conf')
with open(file_path, 'r') as file:
    config = json.load(file)
TOKEN = config.get("bot_translator")

# Инициализация бота и БД
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()
dp.include_router(router_development)
dp.include_router(router_main_menu)
# Главное меню


def main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🃏 Получить карточку")],
            [KeyboardButton(text="💼 Мои карты")],
            [KeyboardButton(text="⚙️ Настройки")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )
    return keyboard


# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    db.register_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"Добро пожаловать в PoTi Cards MLBB, {message.from_user.first_name}!\n\n"
        "🃏 Собирай уникальные карточки и пополняй свою коллекцию!\n\n"
        "🌍 Новые карты и улучшения будут регулярно добавляться, чтобы твоя коллекция оставалась на пике!",
        reply_markup=main_menu()
    )

# Получение случайной карточки
@dp.message(F.text == "🃏 Получить карточку")
async def get_card(message: Message):
    user_id = message.from_user.id
    if db.can_receive_card(user_id):
        card = db.get_random_card(user_id=user_id, exclude_received=True)
        if card:
            db.give_card_to_user(user_id, card['id'])
            caption = (
                f"{message.from_user.first_name}, ты получил новую карточку! 🃏\n"
                f"\n✨ <b>{card['name']}</b>\n"
                f"⚜️ Редкость: {card['rarity'].capitalize()}\n"
                f"🔪 Атака: {card['attack']}\n"
                f"❤️ Здоровье: {card['health']}\n"
                f"\n💠 Ценность: {card['value']} pts"
            )
            if card["image_path"]:
                await message.answer_photo(photo=card['image_path'], caption=caption, parse_mode="HTML", reply_markup=main_menu())
            else:
                await message.answer(caption, parse_mode="HTML", reply_markup=main_menu())
        else:
            await message.answer("Ты уже собрал все доступные карточки! ")
    else:
        result = db.conn.execute(
            "SELECT last_received FROM user_card_cooldowns WHERE user_id = ?",
            (user_id,)).fetchone()
        last_time = datetime.fromisoformat(result['last_received'])
        remaining = timedelta(hours=4) - (datetime.utcnow() - last_time)
        remaining_str = str(remaining).split(".")[0]  # Оставляем только часы, минуты и секунды

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Купить 1 прокрут за PoTi Coin", callback_data="buy_spin")]
        ])

        # Отправка сообщения с оставшимся временем и кнопкой
        await message.answer(
            f"🃏🙅‍♂ {message.from_user.first_name}, получать карточки можно раз в 4 часа. Приходи через:\n"
            "➖➖➖➖➖➖\n"
            f"   ⏳ {remaining_str}",
            reply_markup=keyboard
        )


@dp.message(F.text == "💼 Мои карты")
async def my_cards(message: Message):
    user_id = message.from_user.id

    counts = db.conn.execute(
        """
        SELECT rarity, COUNT(*) as count FROM cards 
        WHERE id IN (SELECT card_id FROM user_cards WHERE user_id = ?)
        GROUP BY rarity
        """, (user_id,)).fetchall()

    rarity_counts = {r['rarity']: r['count'] for r in counts}
    rarities = ["common", "uncommon", "rare", "epic", "legendary"]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{r.capitalize()}: {rarity_counts.get(r, 0)}", callback_data=f"show_rarity:{r}")] for r in rarities
    ] + [[InlineKeyboardButton(text="🌟 Все карты", callback_data="show_rarity:all")]])

    await message.answer(
        f"{ message.from_user.first_name}, какие карты ты хочешь посмотреть?",
        reply_markup=keyboard
    )

# Обработчик кнопки "Настройки"
@dp.message(F.text == "⚙️ Настройки")
async def settings(message: Message):
    await message.answer(
        f"{message.from_user.first_name}, здесь ты можешь изменить настройки бота.\n\n"
        "Пока что настройки недоступны."
    )

@dp.message(F.text.startswith("/generate"))
async def cmd_generate(message: Message):
    try:
        amount = message.text.split()[1]
        print(amount)
        generate_random_cards(int(amount))
        await message.answer(f"✅ Успешно сгенерировано {amount} случайных карт!")
    except (ValueError, TypeError) as e:
        await message.answer("❌ Пожалуйста, укажи количество карт. Пример: /generate 30" + str(e))



@dp.callback_query(F.data.startswith("show_rarity:"))
async def show_rarity_cards(call: CallbackQuery):
    user_id = call.from_user.id
    await call.answer()
    rarity = call.data.split(":")[1]
    if rarity == "all":
        cards = db.conn.execute(
            "SELECT * FROM cards WHERE id IN (SELECT card_id FROM user_cards WHERE user_id = ?) ORDER BY value DESC",
            (user_id,)).fetchall()
    else:
        cards = db.conn.execute(
            "SELECT * FROM cards WHERE id IN (SELECT card_id FROM user_cards WHERE user_id = ?) AND rarity = ?",
            (user_id, rarity)).fetchall()

    if not cards:
        await call.message.edit_text(f"Нет карт с редкостью '{rarity}'.")
        return

    for card in cards:
        text = (
            f"✨ <b>{card['name']}</b>\n"
            f"⚜️ Редкость: {card['rarity'].capitalize()}\n"
            f"🔪 Атака: {card['attack']}\n"
            f"❤️ Здоровье: {card['health']}\n"
            f"💠 Ценность: {card['value']} pts"
        )
        if card["image_path"]:
            await call.message.answer_photo(photo=card['image_path'], caption=text, parse_mode="HTML")
        else:
            await call.message.answer(text, parse_mode="HTML")


@dp.callback_query(F.data == "buy_spin")
async def buy_spin(call: CallbackQuery):
    user_id = call.from_user.id
    # Инициализация PoTi Coin для нового пользователя (если это необходимо)
    db.initialize_user_poti_coins(user_id)

    # Проверяем баланс PoTi Coin у пользователя
    user_coins = db.get_user_poti_coins(user_id)

    if user_coins >= 1:  # Если у пользователя достаточно монет
        db.spend_poti_coin(user_id, 1)  # Списываем 1 PoTi Coin

        # Отправляем сообщение о успешной покупке
        await call.message.edit_text(
            f"🎉 {call.from_user.first_name}, ты купил 1 прокрут за PoTi Coin! 🃏\n\n"
            "Ты можешь получить новую карточку."
        )

        # Логика получения карточки или другого действия (например, получения случайной карточки)
        card = db.get_random_card(user_id=user_id, exclude_received=True)
        if card:
            db.give_card_to_user(user_id, card['id'])
            caption = (
                f"{call.from_user.first_name}, ты получил новую карточку! 🃏\n"
                f"\n✨ <b>{card['name']}</b>\n"
                f"⚜️ Редкость: {card['rarity'].capitalize()}\n"
                f"🔪 Атака: {card['attack']}\n"
                f"❤️ Здоровье: {card['health']}\n"
                f"\n💠 Ценность: {card['value']} pts"
            )
            if card["image_path"]:
                await call.message.answer_photo(photo=card['image_path'], caption=caption, parse_mode="HTML",
                                                reply_markup=main_menu())
            else:
                await call.message.answer(caption, parse_mode="HTML", reply_markup=main_menu())
        else:
            await call.message.edit_text("Ты уже собрал все доступные карточки!")
    else:
        # Если у пользователя недостаточно монет
        await call.message.edit_text(
            f"❌ У тебя недостаточно PoTi Coin для покупки прокрута. Попробуй снова позже!",
        )

@dp.callback_query(F.data == "⬅ Назад")
async def go_back(callback: CallbackQuery):
    prev_menu = pop_menu(callback.from_user.id)
    if prev_menu == "main":
        await main_menu(callback.message)
    elif prev_menu == "pass":
        await menu_pass(callback)
    elif prev_menu == "shop":
        await handle_shop(callback)
    elif prev_menu == "top":
        await handle_top(callback)
    else:
        await main_menu(callback.message)


async def main() -> None:
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())