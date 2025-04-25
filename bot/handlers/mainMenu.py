from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F, Bot # Import Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram import Router
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging # Import logging
from typing import Optional, List

from bot.card_database import rarity_translate
from bot.keyboards.main_keyboard import main_menu
# Import case_manager
from bot.Classes.db_manager import task_manager, command_manager, user_manager, clan_manager, card_manager #, case_manager

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

def get_pagination_keyboard(
    position: str,
    current_page: int,
    total_pages: int,
    extra_buttons: Optional[List[List[InlineKeyboardButton]]] = None,
    back_callback: str = "menu" # Default back button goes to main menu
    ) -> InlineKeyboardMarkup:
    """Creates pagination keyboard with optional extra buttons and a back button."""
    builder = InlineKeyboardBuilder()
    nav_row = []

    # Previous Page Button
    if current_page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"{position}:{current_page - 1}"))
    else: # Add a placeholder or spacer if you want consistent button width
         nav_row.append(InlineKeyboardButton(text=" ", callback_data="noop")) # No operation

    # Page Indicator Button
    nav_row.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="noop"))

    # Next Page Button
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"{position}:{current_page + 1}"))
    else: # Placeholder/spacer
         nav_row.append(InlineKeyboardButton(text=" ", callback_data="noop"))

    # Add the navigation row if it contains actual buttons (prevents empty row if total_pages=1)
    if any(b.callback_data != "noop" for b in nav_row):
         builder.row(*nav_row)

    # Add extra buttons (like item buttons in shop)
    if extra_buttons:
        for row in extra_buttons:
            builder.row(*row)

    # Add the back button at the bottom
    builder.row(back_button(back_callback))

    return builder.as_markup()

dp = Router()


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
            reply_markup=get_pagination_keyboard(position, current_page, total_pages, extra_buttons=[[back_button("menu")]])
        )
    elif current_page == 2:
        await callback.message.edit_text(
            f"{callback.from_user.first_name}, ты можешь купить прокрут за PoTi Coin:\n\n"
        "5 карт ➻ 549 PoTi Coin\n"
        "10 карт ➻ 1449 PoTi Coin\n"
        "30 карт ➻ 3000 PoTi Coin\n"
        "100 карт ➻ 10000 PoTi Coin\n",
            reply_markup=get_pagination_keyboard(position, current_page, total_pages, extra_buttons=[[back_button("menu")]])
        )
    else:
        await callback.message.edit_text(
            f"{callback.from_user.first_name}, здесь ты можешь приобрести за PoTi Coin наши кейсы (эксклюзивные карточки):\n\n"
            "Кейс 1 - $$$\nКейс 2 - $$$\nКейс 3 - $$$",
            reply_markup=get_pagination_keyboard(position, current_page, total_pages, extra_buttons=[[back_button("menu")]])
        )


@dp.callback_query(F.data == "craft")
async def menu_craft(call: CallbackQuery):
    user_data = await  user_manager.get_user_info(call.from_user.id)
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
        f"┏⚡ Редкие— {user_data.shards_rare}\n"
        f"┠✨ Эпические — {user_data.shards_epic}\n"
        f"┠🐉 Легендарные — {user_data.shards_legendary}\n"
        f"┗🧱 Осколки — {user_data.shards}\n\n"
        f"<b>🍬 Стоимость крафтов</b>\n"
        f"┏10 ⚡ карт ➠ 1 попытка\n"
        f"┠10 ✨ карт ➠ 2 попытки\n"
        f"┠10 🐉 карт ➠ 4 попытки\n"
        f"┗10 🧱 оск. ➠ 1 попытка\n\n"
        f"🛢 Чтобы скрафтить сразу из всех материалов, пиши команду\n"
        f"<code>Крафт всех [Осколков/обычных/редких/эпических]</code>"
    )
    await call.message.edit_text(text=text, reply_markup=craft_keyboard)


@dp.callback_query(F.data == "craft_shard")
async def craft_shard(call: CallbackQuery):
    user_id = call.from_user.id
    if user_manager.spend_shards(user_id, 10):
        card = card_manager.get_random_card(user_id, exclude_received=False)
        if card:
            card_manager.give_card_to_user(user_id, card['id'], card['rarity'])
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
            task_manager.update_task_progress(
                user_id=user_id,
                event_type='GET_CARD',
                rarity=card['rarity']  # Передаем редкость полученной карты
            )

        else:
            await call.message.answer(caption, parse_mode="HTML", reply_markup=main_menu())


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

SHOP_ITEMS_PER_PAGE = 5 # Adjust as needed

@dp.callback_query(F.data.startswith("shop:"))
async def menu_shop(callback: CallbackQuery):
    position = callback.data.split(":")[0] # Should be "shop"
    try:
        current_page = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        current_page = 1

    all_cases = case_manager.get_all_cases()
    total_cases = len(all_cases)
    total_pages = (total_cases + SHOP_ITEMS_PER_PAGE - 1) // SHOP_ITEMS_PER_PAGE
    if total_pages == 0: total_pages = 1 # At least one page even if empty

    # Clamp page number
    current_page = max(1, min(current_page, total_pages))

    start_index = (current_page - 1) * SHOP_ITEMS_PER_PAGE
    end_index = start_index + SHOP_ITEMS_PER_PAGE
    cases_on_page = all_cases[start_index:end_index]

    text = f"🔮 {callback.from_user.first_name}, добро пожаловать в магазин!\n\n"
    shop_buttons = []

    if not cases_on_page:
        text += "ℹ️ Кейсы пока не добавлены в магазин."
    else:
        text += "✨ **Доступные кейсы:**\n"
        for case in cases_on_page:
            price_str = ""
            buttons_row = []
            if case['price_coins'] > 0:
                 price_str += f"{case['price_coins']} 🪙"
                 buttons_row.append(InlineKeyboardButton(text=f"Купить за 🪙", callback_data=f"buy_case:coins:{case['id']}"))
            if case['price_shards'] > 0:
                 if price_str: price_str += " или "
                 price_str += f"{case['price_shards']} 🀄️"
                 buttons_row.append(InlineKeyboardButton(text=f"Купить за 🀄️", callback_data=f"buy_case:shards:{case['id']}"))

            if not price_str: price_str = "Бесплатно" # Or handle cases without price differently

            text += f"\n📦 **{case['name']}** ({case['card_count']} карт)\n"
            if case['description']:
                text += f"   📝 {case['description']}\n"
            text += f"   💰 Цена: {price_str}\n"

            if buttons_row: # Add buy buttons if case is purchasable
                shop_buttons.append(buttons_row)
            shop_buttons.append([InlineKeyboardButton(text="-"*20, callback_data="noop")]) # Separator

    # Add fixed items like PoTi Coin purchase (if desired) on every page? Or separate section?
    # For simplicity, let's keep them separate for now or integrate differently.

    # Add back button to the extra_buttons list
    extra_nav = [[back_button("menu")]]

    keyboard = get_pagination_keyboard("shop", current_page, total_pages, extra_buttons=shop_buttons + extra_nav)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    except TelegramBadRequest as e:
        # Handle potential "message is not modified" error if content is the same
        if "message is not modified" in str(e):
            await callback.answer() # Just acknowledge the button tap
        else:
            logging.error(f"Error editing shop message: {e}")
            await callback.answer("Произошла ошибка при обновлении магазина.")


@dp.callback_query(F.data.startswith("buy_case:"))
async def buy_case_handler(callback: CallbackQuery, bot: Bot): # Inject Bot instance
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка данных покупки.", show_alert=True)
        return

    currency_type = parts[1] # 'coins' or 'shards'
    try:
        case_id = int(parts[2])
    except ValueError:
        await callback.answer("Неверный ID кейса.", show_alert=True)
        return

    # --- Attempt to open the case ---
    await callback.answer(f"Открываем кейс...") # Indicate processing

    obtained_cards, status_message = case_manager.open_case(user_id, case_id)

    if obtained_cards is None:
        # Failed to open (insufficient funds, case empty, DB error)
        await callback.message.answer(f"🚫 Не удалось открыть кейс: {status_message}", reply_markup=create_back_button("shop:1")) # Go back to shop page 1
        return

    # --- Success! Format and display the obtained cards ---
    result_text = f"🎉 {status_message}\n\n**Ты получил:**\n"
    media_group = []
    text_fallback_lines = [] # For cards without images

    for i, card in enumerate(obtained_cards):
        rar_emoji = rarity_translate.get(card['rarity'], "<?>")[0:3]
        card_line = f"{i+1}. {rar_emoji} **{card['name']}** (А:{card['attack']}/З:{card['health']})"
        result_text += card_line + "\n"
        text_fallback_lines.append(card_line)

        if card.get('image_path'):
             media_group.append(InputMediaPhoto(media=card['image_path'], caption=card_line if len(obtained_cards) <= 10 else None)) # Add caption only for few cards
        else:
             # Handle cards without images - maybe add to text description?
             pass # Already added to result_text

    # Send results
    if media_group:
        try:
            # Send as media group if multiple images exist
            if len(media_group) > 1:
                 await bot.send_media_group(chat_id=user_id, media=media_group[:10]) # Max 10 per group
                 # Send the text summary separately if media group was used
                 await callback.message.answer(f"🎉 {status_message}\n\n**Полный список полученного:**\n" + "\n".join(text_fallback_lines), reply_markup=create_back_button("shop:1"), parse_mode="Markdown")
            elif len(media_group) == 1:
                 # Send single photo with full caption
                 await bot.send_photo(chat_id=user_id, photo=media_group[0].media, caption=result_text, reply_markup=create_back_button("shop:1"), parse_mode="Markdown")

        except Exception as e:
            logging.error(f"Error sending case results media group/photo for user {user_id}: {e}")
            # Fallback to text message if media sending failed
            await callback.message.answer(result_text, reply_markup=create_back_button("shop:1"), parse_mode="Markdown")
    else:
        # Send as plain text if no images
        await callback.message.answer(result_text, reply_markup=create_back_button("shop:1"), parse_mode="Markdown")


# No operation callback handler for pagination display button
@dp.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()

