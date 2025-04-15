from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram import Router
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.card_database import db

def action_button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)

def back_button(data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text="⬅ Назад", callback_data=data)

def create_back_button(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [back_button(callback_data)]
        ]
    )

def get_pagination_keyboard(position, current_page: int, total_pages: int, buttons=None) -> InlineKeyboardMarkup:
    keyboard = []

    # Верхний ряд — пагинация
    pagination_buttons = []
    if current_page > 1:
        pagination_buttons.append(InlineKeyboardButton(text="⬅", callback_data=f"{position}:{current_page - 1}"))
    if current_page < total_pages:
        pagination_buttons.append(InlineKeyboardButton(text="➡", callback_data=f"{position}:{current_page + 1}"))

    if pagination_buttons:
        keyboard.append(pagination_buttons)

    # Нижние ряды — пользовательские кнопки по 2 в ряд
    if buttons:
        for i in range(0, len(buttons), 2):
            keyboard.append(buttons[i:i + 2])

    return InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None

dp = Router()

def user_main_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Pass", callback_data="pass"),
         InlineKeyboardButton(text="🏆 Рейтинг", callback_data="rating")],
        [InlineKeyboardButton(text="🔮 Магазин", callback_data="shop:1"),
         InlineKeyboardButton(text="♻️ Крафт", callback_data="craft")],
        [InlineKeyboardButton(text="🎕️ Кланы", callback_data="clans"),
         InlineKeyboardButton(text="🎯 Арена", callback_data="arena")],
        [InlineKeyboardButton(text="🌙 Задания", callback_data="quests"),
         InlineKeyboardButton(text="🔗 Рефералка", callback_data="referral")],
        [InlineKeyboardButton(text="🎁 Бонусы за крутки", callback_data="spin_bonus")]
    ])
    return keyboard

@dp.callback_query(F.data == "menu")
async def show_main_menu(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.first_name

    # Получение информации из БД
    user_data = db.get_user_info(user_id)
    if not user_data:
        await call.answer("Вы не зарегистрированы. Введите /start")
        return

    total_cards = user_data.total_cards
    cards_owned = user_data.cards_owned
    season_points = user_data.season_points
    coins = user_data.coins

    text = (
        f"Ник: {username}\n"
        f"Всего карт: {cards_owned} из {total_cards}\n"
        f"Сезонные очки: {season_points} pts\n"
        f"Коины: {coins} 🪙"
    )
    await call.message.edit_text(text, reply_markup=user_main_menu())


@dp.message(F.text == "☁️ Меню")
async def show_main_menu(message: Message):
    user_id = message.from_user.id
    username = message.from_user.first_name

    # Получение информации из БД
    user_data = db.get_user_info(user_id)
    if not user_data:
        await message.answer("Вы не зарегистрированы. Введите /start")
        return

    total_cards = user_data.total_cards
    cards_owned = user_data.cards_owned
    season_points = user_data.season_points
    coins = user_data.coins

    text = (
        f"Ник: {username}\n"
        f"Всего карт: {cards_owned} из {total_cards}\n"
        f"Сезонные очки: {season_points} pts\n"
        f"Коины: {coins} 🪙"
    )
    await message.answer(text, reply_markup=user_main_menu())


# Обработчики пунктов меню (заглушки для будущей логики)

@dp.callback_query(F.data == "pass")
async def menu_pass(call: CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="🌠 Купить пропуск", callback_data="buy_pass")],
        [back_button("menu")],
    ]

    builder = InlineKeyboardBuilder()
    for row in kb:
        builder.row(*row)
    await call.answer()

    await call.message.edit_text(
        "💼 Pass - 🔒 <b>Что даст тебе PoTi Pass?</b>\n\n"
        "⛺ <b>Создай собственный клан</b>\n"
        "⏳ <b>Получай карточки каждые 3 часа</b> вместо 4\n"
        "🏟 <b>Сражайся на арене каждый час</b> вместо 2\n"
        "🕒 <b>Уведомления о завершении времени ожидания</b> карт и арены\n"
        "👾 <b>Уведомления о времени сражений с боссом</b>\n"
        "👻 <b>Повышенная вероятность</b> выпадения легендарных, эпических и мифических карт\n"
        "🧍 <b>Используй смайлики в никнейме</b>\n"
        "🌀 <b>+3 крутки</b>\n"
        "🗓 <b>Срок действия:</b> 30 дней\n"
        "🔑 <b>Стоимость:</b> 159 рублей", reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "rating:season")
async def menu_rating(call: CallbackQuery):
    await call.message.edit_text("hello")

@dp.callback_query(F.data == "rating")
async def menu_rating(call: CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="🌠 Топ-10 этого сезона", callback_data="rating:season")],
        [InlineKeyboardButton(text="🏆 Топ за всё время", callback_data="rating:all")],
        [
            InlineKeyboardButton(text="⭐ Топ кланов", callback_data="rating:clans"),
            InlineKeyboardButton(text="🛡 Топ арены", callback_data="rating:arena")
        ],
        [back_button("menu")]
    ]

    builder = InlineKeyboardBuilder()
    for row in kb:
        builder.row(*row)

    await call.message.edit_text(
        f"{call.from_user.first_name}, выбери категорию",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("shop:"))
async def menu_shop(callback: CallbackQuery):
    position = callback.data.split(":")[0]
    current_page = int(callback.data.split(":")[1])
    total_pages = 3
    if current_page == 1:
        await callback.message.edit_text(
            f"{callback.from_user.first_name}, ты можешь купить PoTi Coin за донат:\n\n"
            "500 PoTi Coin ➻ 50 руб\n"
            "1000 PoTi Coin ➻ 100 руб\n"
            "3000 PoTi Coin ➻ (300) 200 руб\n"
            "10000 PoTi Coin ➻ (1000) 600 руб\n",
            reply_markup=get_pagination_keyboard(position, current_page, total_pages, buttons=[back_button("menu")])
        )
    elif current_page == 2:
        await callback.message.edit_text(
            f"{callback.from_user.first_name}, ты можешь купить прокрут за PoTi Coin:\n\n"
        "5 карт ➻ 549 PoTi Coin\n"
        "10 карт ➻ 1449 PoTi Coin\n"
        "30 карт ➻ 3000 PoTi Coin\n"
        "100 карт ➻ 10000 PoTi Coin\n",
            reply_markup=get_pagination_keyboard(position, current_page, total_pages, buttons=[back_button("menu")])
        )
    else:
        await callback.message.edit_text(
            f"{callback.from_user.first_name}, здесь ты можешь приобрести за PoTi Coin наши кейсы (эксклюзивные карточки):\n\n"
            "Кейс 1 - $$$\nКейс 2 - $$$\nКейс 3 - $$$",
            reply_markup=get_pagination_keyboard(position, current_page, total_pages, buttons=[back_button("menu")])
        )


@dp.callback_query(F.data == "craft")
async def menu_craft(call: CallbackQuery):
    common_duplicates, rare_duplicates, epic_duplicates, shards = "0000"
    craft_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Скрафтить из ⚡", callback_data="craft_common"),
            InlineKeyboardButton(text="Скрафтить из ✨", callback_data="craft_rare")
        ],
        [
            InlineKeyboardButton(text="Скрафтить из 🐉", callback_data="craft_epic"),
            InlineKeyboardButton(text="Скрафтить из 🧱", callback_data="craft_shard")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")
        ]
    ])
    text = (
        f"<b>{call.from_user.first_name}</b>, ты можешь скрафтить попытки из повторок и осколков\n\n"
        f"<b>🌐 Твои повторки и осколки</b>\n"
        f"┏⚡ Обычные — {common_duplicates}\n"
        f"┠✨ Редкие — {rare_duplicates}\n"
        f"┠🐉 Эпические — {epic_duplicates}\n"
        f"┗🧱 Осколки — {shards}\n\n"
        f"<b>🍬 Стоимость крафтов</b>\n"
        f"┏10 ⚡ карт ➠ 1 попытка\n"
        f"┠10 ✨ карт ➠ 2 попытки\n"
        f"┠10 🐉 карт ➠ 4 попытки\n"
        f"┗10 🧱 оск. ➠ 1 попытка\n\n"
        f"🛢 Чтобы скрафтить сразу из всех материалов, пиши команду\n"
        f"<code>Крафт всех [Осколков/обычных/редких/эпических]</code>"
    )
    await call.message.edit_text(text=text, reply_markup=craft_keyboard)


@dp.callback_query(F.data == "clans")
async def menu_clans(call: CallbackQuery):
    await call.message.edit_text("Кланы — грядут большие битвы!", reply_markup=user_main_menu())


@dp.callback_query(F.data == "arena")
async def menu_arena(call: CallbackQuery):
    await call.message.edit_text("Арена будет доступна скоро.", reply_markup=user_main_menu())


@dp.callback_query(F.data == "quests")
async def menu_quests(call: CallbackQuery):
    await call.message.edit_text("Задания появятся с обновлением.", reply_markup=user_main_menu())


@dp.callback_query(F.data == "referral")
async def menu_referral(call: CallbackQuery):
    await call.message.edit_text("Приглашай друзей и получай бонусы!", reply_markup=user_main_menu())


@dp.callback_query(F.data == "spin_bonus")
async def menu_spin_bonus(call: CallbackQuery):
    await call.message.edit_text("Крути и выигрывай бонусы! Скоро...", reply_markup=user_main_menu())
