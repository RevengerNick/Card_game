from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram import Router
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.main_keyboard import main_menu
from bot.Classes.db_manager import task_manager, command_manager

reward_levels = [
        (10, 5, 0),
        (50, 10, 0),
        (100, 15, 0),
        (350, 20, 50),
        (500, 50, 300),
        (1000, 100, 1000),
        (5000, 300, 5000),
    ]

BOT_USERNAME = "translateevery_bot"

from bot.Classes.db_manager import card_manager, user_manager, clan_manager, promo_manager

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


@dp.message(CommandStart(deep_link=True))
async def cmd_start_ref(message: Message, command: CommandObject):
    user_manager.register_user(message.from_user.id, message.from_user.username)
    ref = command.args  # например: "ref_12345"
    user_id = message.from_user.id
    print(ref)

    if ref and ref.startswith("ref_"):
        referrer_id = int(ref.split("_")[1])
        if referrer_id != user_id:
            # Сохраняем в БД, если ещё не было привязки
            db_user = user_manager.get_user(user_id)
            if not db_user.referrer_id:
                user_manager.set_referrer(user_id, referrer_id)
                # Можно начислить бонус пригласившему
                # bonus_manager.add_bonus(referrer_id)


    await message.answer(
        f"Добро пожаловать в PoTi Cards MLBB, {message.from_user.first_name}!\n\n"
        "🃏 Собирай уникальные карточки и пополняй свою коллекцию!\n\n"
        "🌍 Новые карты и улучшения будут регулярно добавляться, чтобы твоя коллекция оставалась на пике!",
        reply_markup=main_menu()
    )

@dp.message(CommandStart(deep_link=False))
async def cmd_start_ref(message: Message, command: CommandObject):
    user_manager.register_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"Добро пожаловать в PoTi Cards MLBB, {message.from_user.first_name}!\n\n"
        "🃏 Собирай уникальные карточки и пополняй свою коллекцию!\n\n"
        "🌍 Новые карты и улучшения будут регулярно добавляться, чтобы твоя коллекция оставалась на пике!",
        reply_markup=main_menu()
    )

@dp.callback_query(F.data == "menu")
async def show_main_menu(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.first_name

    # Получение информации из БД
    user_data = await user_manager.get_user_info(user_id)
    if not user_data:
        await call.answer("Вы не зарегистрированы. Введите /start")
        return

    total_cards = user_data.total_cards_in_game
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
    user_data = await user_manager.get_user_info(user_id)
    if not user_data:
        await message.answer("Вы не зарегистрированы. Введите /start")
        return

    total_cards = user_data.total_cards_in_game
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
    user_id = call.from_user.id
    username = call.from_user.first_name

    top_users = user_manager.get_top_users_by_season()
    user_rank = user_manager.get_user_season_rank(user_id)

    text = format_top_message("топ-10 игроков сезона", top_users, user_rank, username)

    await call.message.edit_text(text, reply_markup=create_back_button("rating"))
    await call.answer()

@dp.callback_query(F.data == "rating:all")
async def menu_rating(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.first_name

    top_users = user_manager.get_top_users_by_season()
    user_rank = user_manager.get_user_season_rank(user_id)

    text = format_top_message("топ-10 игроков за всё время", top_users, user_rank, username)

    await call.message.edit_text(text, reply_markup=create_back_button("rating"))
    await call.answer()

@dp.callback_query(F.data == "rating:clans")
async def menu_rating(call: CallbackQuery):
    await process_clan_callback(call)
    await call.message.answer("hello", reply_markup=create_back_button("rating"))

@dp.callback_query(F.data == "rating")
async def menu_rating(call: CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="🌠 Топ-10 этого сезона", callback_data="rating:season")],
        [InlineKeyboardButton(text="🏆 Топ за всё время", callback_data="rating:all")],
        [
            InlineKeyboardButton(text="⭐ Топ кланов", callback_data="rating:clans")
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



@dp.callback_query(F.data == "quests")
async def menu_quests(call: CallbackQuery):
    user_id = call.from_user.id
    # Получаем имя пользователя, экранируем HTML-символы на всякий случай

    try:
        # Вся логика получения, проверки и форматирования уже в этом методе!
        formatted_message = task_manager.format_tasks_message(user_id, call.from_user.first_name)

        # Отправляем отформатированное сообщение пользователю
        await call.message.edit_text(
            text=formatted_message
        )

    except Exception as e:
        # Логируем ошибку для отладки
        import traceback
        print(f"Ошибка при обработке /quest для user_id={user_id}: {e}\n{traceback.format_exc()}")
        # Отправляем сообщение пользователю
        await call.message.answer("😕 Произошла ошибка при получении ваших заданий. Попробуйте выполнить команду позже.")


@dp.callback_query(F.data == "referral")
async def menu_referral(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.first_name or "Друг"

    # Кол-во приглашённых и полученных попыток (пример, нужно получить из БД)
    invited_count = 0#user_manager.get_invited_count(user_id) or 0
    attempts_count = invited_count // 3

    # Проверка на доступность бонуса сегодня (пример)
    #can_receive_bonus = referral_manager.can_receive_today(user_id)
    status = "✅"# if can_receive_bonus else "❌"

    link = (
        f"🔗 *Нажми и скопируй ссылку:*\n"
        f"`https://t\\.me/{BOT_USERNAME}\\?start\\=ref_{user_id}`"
    )
   # link = f"[🔗 Нажми, чтобы скопировать](https://t\\.me/{BOT_USERNAME}?start\\=ref_{user_id})"

    text = (
        f"🔗 *{username}*, приводи друзей в игру по своей ссылке и получай за это приятные бонусы\n\n"
        f"🌅 За каждых *трёх* приведённых друзей ты получишь *1 попытку*\n\n"
        f"🍙 Привёл игроков: *{invited_count}*\n"
        f"🪄 Получил попыток: *{attempts_count}*\n"
        f"⌛️ До обновления: *{status}*\n"
        f"🤝 Твоя ссылка: {link}\n\n"
        f"📬 Такой возможностью можно воспользоваться *не больше одного раза в сутки*"
    )

    await call.answer()
    await call.message.edit_text(text, reply_markup=create_back_button("menu"), parse_mode="MarkdownV2")


@dp.callback_query(F.data == "spin_bonus")
async def menu_spin_bonus(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.first_name or "Игрок"

    total_received = user_manager.get_total_cards_received(user_id)

    # Уровни наград: (цель, награда_карты, награда_пыль)


    text = f"💖 <b>{username}</b>, получай карты и получай за это награды.\n\n"

    for goal, card_reward, dust_reward in reward_levels:
        status = "✅" if total_received >= goal else "❌"
        reward_line = f"{card_reward} 🃏"
        if dust_reward:
            reward_line += f" + {dust_reward} 🀄️"
        text += (
            f"{status} Получено {min(total_received, goal)} из {goal}\n"
            f"🫀 Награда: {reward_line}\n\n"
        )

    await call.message.edit_text(text, reply_markup=create_back_button("menu"))


def format_rating(points: int) -> str:
    if points >= 1_000_000:
        return f"{points / 1_000_000:.1f}m pts"
    elif points >= 1_000:
        return f"{points / 1_000:.1f}k pts"
    else:
        return f"{points} pts"


def format_top_message(title: str, top_rows: list, user_place: int, username: str) -> str:
    lines = [f"💫 {username}, вот {title}", "➖➖➖➖➖➖"]

    for i, row in enumerate(top_rows, start=1):
        name = row["username"] or "ᅠ"
        rating = row.get("season_rating") or row.get("rating") or 0
        lines.append(f"{i}. {name} - {format_rating(rating)}")

    lines.append("➖➖➖➖➖➖")
    lines.append(f"⏺️ Твоё место ➛ {user_place}")
    return "\n".join(lines)


from typing import Optional, List, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


async def display_clan_info( clan_id, page=0, total_clans=None):
    """
    Отображает информацию о клане с кнопками пагинации для переключения между кланами

    :param clan_manager: Экземпляр ClanManager
    :param clan_id: ID текущего клана для отображения
    :param page: Текущая страница (индекс в списке кланов)
    :param total_clans: Общее количество кланов (если None, будет получено из базы)
    :return: tuple(text, keyboard) - текст сообщения и разметка клавиатуры
    """
    # Получаем информацию о клане
    clan_info = clan_manager.get_clan_info(clan_id)
    if not clan_info:
        return "Клан не найден", None

    # Получаем список всех кланов для пагинации
    if total_clans is None:
        top_clans = clan_manager.get_top_clans(limit=100)  # Получаем до 100 кланов
        total_clans = len(top_clans)

    # Формируем текст сообщения
    text = (
        f"🏰 Клан - {clan_info['name']}\n\n"
        f"🌍 Вселенная: Истребитель демонов\n"
        f"⚪ Всего очков: {clan_info['points']} pts\n"
        f"👑 Глава клана: {clan_info['leader_username']}\n"
        f"👥 Всего участников: {clan_info['members_count']}\n"
        f"🏆 Место в топе: {clan_info['rank'] or '-'}\n"
    )

    # Добавляем заместителей, если они есть
    if clan_info['deputies']:
        deputy_names = [dep['username'] for dep in clan_info['deputies']]
        text += f"💎 Заместители: {', '.join(deputy_names)}\n\n"
    else:
        text += "💎 Заместители: отсутствуют\n\n"

    # Добавляем топ-7 участников
    text += "👨‍👩‍👧‍👦 Топ 7 участников клана\n"
    for member in clan_info['top7']:
        pts_formatted = f"{member['rating'] / 1000000:.1f}m" if member[
                                                                    'rating'] >= 1000000 else f"{member['rating'] / 1000:.1f}k"
        text += f"▹{member['username']} ({pts_formatted} pts)\n"

    # Добавляем описание клана
    text += f"\n📜 Описание клана\n{clan_info['description'] or 'Описание отсутствует'}"

    # Создаем кнопки пагинации
    buttons = []

    # Кнопка с текущей позицией
    page_text = f"{page + 1}/{total_clans}"
    buttons.append(InlineKeyboardButton(text=page_text, callback_data="clan_position"))

    # Создаем ряд с кнопками навигации
    nav_row = []

    # Кнопка назад (влево)
    if page > 0:
        nav_row.append(InlineKeyboardButton(
            text="⬅️",
            callback_data=f"show_clan:{page - 1}"
        ))

    # Кнопка вперед (вправо)
    if page < total_clans - 1:
        nav_row.append(InlineKeyboardButton(
            text="➡️",
            callback_data=f"show_clan:{page + 1}"
        ))

    # Кнопка вступить в клан (или другие действия)
    action_row = [InlineKeyboardButton(
        text="Вступить в клан",
        callback_data=f"join_clan:{clan_id}"
    )]

    # Кнопка назад (в меню)
    back_row = [InlineKeyboardButton(
        text="Назад",
        callback_data="back_to_menu"
    )]

    # Формируем клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_row, action_row, back_row])

    return text, keyboard


# Пример использования в обработчике callback
async def process_clan_callback(call):
    parts = call.data.split(":")
    command = parts[0]

    if command == "show_clan":
        page = int(parts[1]) if len(parts) > 1 else 0

        # Получаем список всех кланов
        top_clans = clan_manager.get_top_clans(limit=100)

        if not top_clans:
            await call.message.edit_text("Кланы не найдены", reply_markup=None)
            return

        # Проверяем граничные условия для пагинации
        total_clans = len(top_clans)
        if page >= total_clans:
            page = 0
        elif page < 0:
            page = total_clans - 1

        # Получаем ID клана для текущей страницы
        clan_id = top_clans[page]["id"]

        # Формируем сообщение
        text, keyboard = await display_clan_info(
            clan_id=clan_id,
            page=page,
            total_clans=total_clans
        )

        try:
            # Пробуем отредактировать сообщение
            await call.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            # Если не получается, отправляем новое
            print(f"Ошибка при редактировании сообщения: {e}")
            await call.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    elif command == "join_clan":
        # Обработка вступления в клан
        clan_id = int(parts[1])
        user_id = call.from_user.id

        success = clan_manager.add_user_to_clan(user_id, clan_id)

        if success:
            await call.answer("Вы успешно вступили в клан!")
        else:
            await call.answer("Не удалось вступить в клан. Возможно, вы уже состоите в клане.")