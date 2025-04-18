import asyncio
import logging
import sys

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage # Или RedisStorage для продакшена

from bot.handlers.arena import arena_handler

# Хранилище для состояний (в памяти для простоты, лучше Redis для масштабирования)
fsm_storage = MemoryStorage()

class BattleState(StatesGroup):
    InBattle = State()

from bot.common import bot

from aiogram import Bot, Dispatcher, F

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from datetime import datetime, timedelta, timezone

from bot.dev.dev import router as router_development
from bot.dev.task_utils import generate_task_variations
from bot.handlers.mainMenu import dp as router_main_menu, create_back_button, back_button
from bot.handlers.clans import clan as clan_handler

from bot.Classes.db_manager import card_manager, user_manager, task_manager, db
from bot.card_database import rarity_translate, DatabaseManager

from bot.dev.card_generator import generate_random_cards
from bot.keyboards.main_keyboard import main_menu

dp = Dispatcher(storage=fsm_storage)
dp.include_router(arena_handler)
dp.include_router(router_development)
dp.include_router(router_main_menu)
dp.include_router(clan_handler)

# Получение случайной карточки
@dp.message(F.text == "🃏 Получить карточку")
async def get_card(message: Message):
    user_id = message.from_user.id
    if card_manager.can_receive_card(user_id):
        card = card_manager.get_random_card(user_id=user_id, exclude_received=True)
        if card:
            card_manager.give_card_to_user(user_id, card['id'])
            caption = (
                f"{message.from_user.first_name}, ты получил новую карточку! 🃏\n"
                f"\n✨ <b>{card['name']}</b>\n"
                f"⚜️ Редкость: {rarity_translate[card['rarity']]}\n"
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
        last_time = user_manager.get_last_card_time(user_id)
        remaining = timedelta(hours=4) - (datetime.now(timezone.utc) - last_time)
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

    rarity_counts = card_manager.get_user_card_counts_by_rarity(user_id)
    rarities = ["common", "rare", "epic", "legendary", "mythical"]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{rarity_translate[r]}: {rarity_counts.get(r, 0)}", callback_data=f"show_rarity:{r}:0")] for r in rarities
    ] + [[InlineKeyboardButton(text="🌟 Все карты", callback_data="show_rarity:all:0")]])

    await message.answer(
        f"{message.from_user.first_name}, какие карты ты хочешь посмотреть?",
        reply_markup=keyboard
    )

# Обработчик кнопки "Настройки"
@dp.message(F.text == "⚙️ Настройки")
async def show_settings(message: Message):
    user_id = message.from_user.id
    user_data = await user_manager.get_user_info(user_id)

    if not user_data:
        await message.answer("⚠️ Пользователь не найден.")
        return

    nickname = user_data.nickname
    total_cards_received = user_data.total_cards_received
    #reg_date = user_data['registration_date']

    #reg_datetime = reg_date.strftime("%d.%m.%Y в %H:%M") if isinstance(reg_date, datetime) else reg_date

    text = (
        f"🪪 *Твой ник:* {nickname}\n"
        "🆔 *Твой айди:* 254119336\n"
        f"🥡 *Количество круток:* {total_cards_received}\n"
        #"🗓 *Регистрация:* 13.04.2025 в 16:29\n\n"
        "📝 *Помощь*\n"
        "➢ Изменить ник можно командой:\n"
        "`Сменить ник [новый_ник]`\n\n"
        "💡 Просто скопируй и вставь, заменив на свой ник!"
    )


    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")]
        ]
    )

    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("show_rarity:"))
async def show_rarity_cards(call: CallbackQuery):
    user_id = call.from_user.id
    await call.answer()

    # Разбираем callback_data
    parts = call.data.split(":")
    rarity = parts[1]
    page = int(parts[2])

    # Получаем карты пользователя
    if rarity == "all":
        cards = card_manager.get_user_cards_ordered_by_value(user_id)
    else:
        cards = card_manager.get_user_cards_by_rarity(user_id, rarity)

    if not cards:
        await call.message.edit_text(f"Нет карт с редкостью '{rarity}'.")
        return

    # Отображаем карту с пагинацией
    total_cards = len(cards)
    if page >= total_cards:
        page = 0
    elif page < 0:
        page = total_cards - 1

    card = cards[page]

    # Формируем текст для карты
    text = (
        f"✨ <b>{card['name']}</b>\n\n"
        f"⚜️ Редкость: {rarity_translate[card['rarity']]}\n"
        f"🔪 Атака: {card['attack']}\n"
        f"❤️ Здоровье: {card['health']}\n\n"
        f"💠 Ценность: {card['value']} pts\n"
    )

    # Создаем клавиатуру для навигации
    buttons = []

    # Кнопка "назад" только если не первая страница
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"show_rarity:{rarity}:{page - 1}"))

    # Кнопка с текущей позицией всегда показывается
    buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_cards}", callback_data=f"card_position"))

    # Кнопка "вперед" только если не последняя страница
    if page < total_cards - 1:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"show_rarity:{rarity}:{page + 1}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])

    # Проверяем, является ли это первым отображением карт или обновлением
    is_first_display = ":" in call.data and len(parts) == 3 and parts[2] == "0" and not hasattr(call.message, 'photo')

    if card["image_path"]:
        if is_first_display:
            # Отправляем первую карту как новое сообщение
            await call.message.answer_photo(photo=card['image_path'], caption=text, reply_markup=keyboard,
                                            parse_mode="HTML")
        else:
            try:
                # Редактируем существующее сообщение
                media = InputMediaPhoto(
                    media=card['image_path'],
                    caption=text,
                    parse_mode="HTML"
                )
                await call.message.edit_media(media=media, reply_markup=keyboard)
            except TelegramBadRequest:
                # Если редактирование не удалось, отправляем новое сообщение
                await call.message.delete()
                await call.message.answer_photo(photo=card['image_path'], caption=text, reply_markup=keyboard,
                                                parse_mode="HTML")
    else:
        # Для карт без изображений просто обновляем текст
        try:
            await call.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest:
            await call.message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@dp.message(F.text.regexp(r"^Сменить ник\s+(.+)$"))
async def change_nickname(message: Message):
    new_nick = message.text.split(" ", 2)[2].strip()
    user_id = message.from_user.id

    if len(new_nick) > 30:
        await message.reply("⚠️ Ник не должен превышать 30 символов.")
        return

    user_manager.update_username(user_id, new_nick)
    await message.reply(f"✅ Ник успешно изменён на: <b>{new_nick}</b>")

@dp.callback_query(F.data == "buy_spin")
async def buy_spin(call: CallbackQuery):
    user_id = call.from_user.id
    # Инициализация PoTi Coin для нового пользователя (если это необходимо)

    # Проверяем баланс PoTi Coin у пользователя
    user_coins = user_manager.get_coins(user_id)

    if user_coins >= 1:  # Если у пользователя достаточно монет
        user_manager.spend_coins(user_id, 1)  # Списываем 1 PoTi Coin

        # Отправляем сообщение о успешной покупке
        await call.message.edit_text(
            f"🎉 {call.from_user.first_name}, ты купил 1 прокрут за PoTi Coin! 🃏\n\n"
            "Ты можешь получить новую карточку."
        )

        # Логика получения карточки или другого действия (например, получения случайной карточки)
        card = card_manager.get_random_card(user_id=user_id)
        if card:
            card_manager.give_card_to_user(user_id, card['id'])
            caption = (
                f"{call.from_user.first_name}, ты получил новую карточку! 🃏\n"
                f"\n✨ <b>{card['name']}</b>\n"
                f"⚜️ Редкость: {rarity_translate[card['rarity']]}\n"
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
            "💸 <b>Недостаточно PoTi Coin!</b>\n\n"
            "Похоже, у тебя не хватает монет для прокрута 🎰\n\n"
            "🔄 Если ты уже оплатил — подожди немного, иногда бывают задержки.\n"
            "🛍️ Если ещё не пополнял — ты можешь сделать это прямо сейчас по кнопке ниже!",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔮 Магазин", callback_data="shop")],
                    [back_button("menu")]  # Твоя кнопка "назад"
                ]
            )
        )


async def main() -> None:
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
