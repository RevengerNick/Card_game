# bot\handlers\mainMenu.py
import asyncio # Необходим для await
import os # Импорт для получения BOT_USERNAME
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, User
from aiogram import F, Router, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from typing import Optional, List, Dict, Any
from aiogram.exceptions import TelegramBadRequest

# Импортируем необходимые компоненты
from bot.card_database import rarity_translate, reward_levels, SUPER_ADMIN_ID
from bot.keyboards.main_keyboard import main_menu
# Импортируем все менеджеры, включая case_manager
from bot.Classes.db_manager import (
    task_manager, command_manager, user_manager, clan_manager, card_manager, case_manager
)
from bot.utils.Filters import IsSuperAdminFilter

# Импортируем фильтр IsSuperAdminFilter для проверки прав в меню админки

# TODO: Получать из конфига или окружения
BOT_USERNAME = os.getenv("BOT_USERNAME", "translateevery_bot")

# --- Keyboard Helpers ---

def action_button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)

def back_button(data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text="⬅ Назад", callback_data=data)

def create_back_button(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_button(callback_data)]])

SHOP_ITEMS_PER_PAGE = 3 # Сколько кейсов показывать на странице магазина

def get_pagination_keyboard(
    position_prefix: str, # Префикс для callback_data пагинации (напр., "shop")
    current_page: int,
    total_pages: int,
    item_buttons: Optional[List[List[InlineKeyboardButton]]] = None, # Кнопки для элементов (кейсов)
    back_callback: str = "menu" # Callback для кнопки "Назад"
    ) -> InlineKeyboardMarkup:
    """Создает клавиатуру пагинации с кнопками элементов и кнопкой Назад."""
    builder = InlineKeyboardBuilder()

    if item_buttons:
        for row in item_buttons:
            builder.row(*row)

    nav_row = []
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"{position_prefix}:{current_page - 1}") if current_page > 1 else InlineKeyboardButton(text=" ", callback_data="noop"))
        nav_row.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="noop"))
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"{position_prefix}:{current_page + 1}") if current_page < total_pages else InlineKeyboardButton(text=" ", callback_data="noop"))
        builder.row(*nav_row)

    builder.row(back_button(back_callback))

    return builder.as_markup()


dp = Router() # Инициализируем Router здесь

# --- Command Handlers ---

@dp.message(CommandStart(deep_link=True))
async def cmd_start_ref(message: Message, command: CommandObject):
    user_id = message.from_user.id
    username = message.from_user.username
    user_manager.register_user(user_id, username)
    ref_arg = command.args

    logging.info(f"User {user_id} started with deep link: {ref_arg}")

    if ref_arg and ref_arg.startswith("ref_"):
        try:
            referrer_id = int(ref_arg.split("_")[1])
            if referrer_id != user_id:
                rows_affected = user_manager.set_referrer(user_id, referrer_id)
                if rows_affected == 1:
                     logging.info(f"User {user_id} successfully set referrer to {referrer_id}")
                     user_manager.add_referral(referrer_id)
                     try:
                          await message.bot.send_message(referrer_id, f"🎉 Ваш друг {message.from_user.full_name} присоединился по вашей ссылке!")
                     except Exception as e:
                          logging.warning(f"Не удалось уведомить реферера {referrer_id}: {e}")
                elif rows_affected == 0:
                     logging.info(f"User {user_id} already had a referrer or same ID.")
            else:
                logging.warning(f"User {user_id} tried to refer themselves.")
        except (IndexError, ValueError) as e:
            logging.error(f"Ошибка разбора реферальной ссылки '{ref_arg}': {e}")

    await message.answer(
        f"Добро пожаловать в PoTi Cards MLBB, {message.from_user.first_name}!\n\n"
        "🃏 Собирай уникальные карточки и пополняй свою коллекцию!\n\n"
        "🌍 Новые карты и улучшения будут регулярно добавляться, чтобы твоя коллекция оставалась на пике!",
        reply_markup=main_menu()
    )
    # Отправляем инлайн меню отдельно
    await show_main_menu_message(message)


@dp.message(CommandStart(deep_link=False))
async def cmd_start_no_ref(message: Message):
    user_manager.register_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"Добро пожаловать в PoTi Cards MLBB, {message.from_user.first_name}!\n\n"
        "🃏 Собирай уникальные карточки и пополняй свою коллекцию!\n\n"
        "🌍 Новые карты и улучшения будут регулярно добавляться, чтобы твоя коллекция оставалась на пике!",
        reply_markup=main_menu()
    )
    # Отправляем инлайн меню отдельно
    await show_main_menu_message(message)


# --- Callback Handlers ---

@dp.callback_query(F.data == "menu")
async def show_main_menu_callback(call: CallbackQuery):
    # ----- ИЗМЕНЕНИЕ ЗДЕСЬ: передаем message и user -----
    await show_main_menu_message(call.message, call.from_user) # Передаем Message и User
    # ----- Удаляем старое сообщение, если оно существует -----
    try:
        await call.message.delete() # Удаляем предыдущее сообщение с инлайн-кнопками (откуда пришел callback)
    except Exception as e:
         logging.warning(f"Не удалось удалить сообщение при переходе в меню: {e}")
    await call.answer()

@dp.message(F.text == "☁️ Меню")
async def show_main_menu_message(message: Message, from_user: Optional[User] = None):
    """Показывает главное меню пользователю."""
    # Определяем пользователя - либо из аргумента (если вызван колбэком), либо из самого сообщения
    user = from_user or message.from_user
    user_id = user.id
    username = user.first_name

    # ----- ИЗМЕНЕНИЕ ЗДЕСЬ: Использование await для get_user_info -----
    user_data = user_manager.get_user_info(user_id)
    if not user_data:
        # Определяем цель для ответа - если вызван колбэком, отвечаем на исходное сообщение колбэка
        # Если вызван сообщением, отвечаем на это сообщение
        target_message_obj = from_user.message if from_user and hasattr(from_user, 'message') else message
        await target_message_obj.answer("Вы не зарегистрированы или ваш аккаунт заблокирован. Введите /start")
        return

    text = (
        f"👤 Ник: <b>{user_data.nickname}</b>\n"
        f"🃏 Собрано карт: {user_data.cards_owned} из {user_data.total_cards_in_game}\n"
        f"✨ Сезонные очки: {user_data.season_points} pts\n"
        f"💰 Монеты: {user_data.coins} 🪙\n"
        f"🧊 Осколки: {user_data.shards} 🀄️"
    )

    # Определяем, является ли пользователь админом
    is_admin_status = user_manager.is_admin(user_id)
    # Генерируем клавиатуру с учетом статуса админа
    keyboard = user_main_menu_inline(is_admin=is_admin_status if user_id not in SUPER_ADMIN_ID else True)

    # Отправляем или редактируем сообщение
    # Если вызвана из message handler, всегда отправляем новое сообщение с inline клавиатурой
    # Если вызвана из callback handler, message является исходным сообщением callback'а.
    # В show_main_menu_callback мы УЖЕ УДАЛИЛИ старое сообщение.
    # Поэтому в обоих случаях нужно ОТПРАВИТЬ НОВОЕ сообщение с inline клавиатурой.
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# --- Клавиатура главного меню (инлайн) ---
def user_main_menu_inline(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Генерирует инлайн-клавиатуру главного меню с опциональной кнопкой админки."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔑 Pass", callback_data="pass"),
        InlineKeyboardButton(text="🏆 Рейтинг", callback_data="rating")
    )
    builder.row(
        InlineKeyboardButton(text="🔮 Магазин", callback_data="shop:1"),
        InlineKeyboardButton(text="♻️ Крафт", callback_data="craft")
    )
    builder.row(
        InlineKeyboardButton(text="🏰 Кланы", callback_data="clans"),
        InlineKeyboardButton(text="⚔️ Арена", callback_data="arena")
    )
    builder.row(
        InlineKeyboardButton(text="🌙 Задания", callback_data="quests"),
        InlineKeyboardButton(text="🔗 Рефералка", callback_data="referral")
    )
    builder.row(
        InlineKeyboardButton(text="🎁 Бонусы", callback_data="spin_bonus")
    )

    if is_admin:
        builder.row(
            InlineKeyboardButton(text="⚙️ Админ панель", callback_data="admin_panel")
        )

    return builder.as_markup()

# --- НОВЫЙ ОБРАБОТЧИК: Кнопка Админ панели ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel_callback(call: CallbackQuery):
    # Проверяем права еще раз на всякий случай
    if not user_manager.is_admin(call.from_user.id):
        await call.answer("Доступ запрещен.", show_alert=True)
        return

    # Создаем простое меню админки
    admin_kb = InlineKeyboardBuilder()
    # Команды управления пользователями
    admin_kb.button(text="Бан", callback_data="admin_ban_user_start") # Заглушки, нужна реализация FSM или другой логики
    admin_kb.button(text="Разбан", callback_data="admin_unban_user_start")
    admin_kb.button(text="Сброс", callback_data="admin_reset_user_start")
    admin_kb.adjust(3)
    # Команды управления картами/кейсами/промо
    admin_kb.button(text="Создать карту", callback_data="admin_cmd_createcard") # Ссылка на команду FSM
    admin_kb.button(text="Создать кейс", callback_data="admin_cmd_createcase")
    admin_kb.button(text="Создать промо", callback_data="admin_cmd_createpromo")
    admin_kb.adjust(3)
    # Команды управления админами (только Super Admin)
    # ----- ИСПРАВЛЕНО ЗДЕСЬ: Использование await для фильтра -----
    if await IsSuperAdminFilter()(call): # Проверяем права суперадмина
         admin_kb.button(text="Добавить админа", callback_data="admin_add_admin_start")
         admin_kb.button(text="Удалить админа", callback_data="admin_del_admin_start")
         admin_kb.adjust(2)
    # Статистика и рассылка
    admin_kb.button(text="Статистика", callback_data="admin_cmd_stats")
    admin_kb.button(text="Рассылка", callback_data="admin_cmd_broadcast")
    admin_kb.adjust(2)
    # Кнопка назад в главное меню
    admin_kb.row(back_button("menu"))

    text = "⚙️ <b>Админ панель</b>\nВыберите действие:"
    await call.message.edit_text(text, reply_markup=admin_kb.as_markup(), parse_mode="HTML")
    await call.answer()


# --- Обработчики для кнопок админки (заглушки/ссылки на команды) ---
# Эти обработчики нужны, чтобы кнопки админки что-то делали.

@dp.callback_query(F.data == "admin_cmd_createcard")
async def admin_panel_create_card(call: CallbackQuery):
    await call.message.edit_text("Для создания карты используйте команду <code>/createcard</code>", reply_markup=create_back_button("admin_panel"), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "admin_cmd_createcase")
async def admin_panel_create_case(call: CallbackQuery):
    await call.message.edit_text("Для создания кейса используйте команду <code>/createcase</code>", reply_markup=create_back_button("admin_panel"), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "admin_cmd_createpromo")
async def admin_panel_create_promo(call: CallbackQuery):
    await call.message.edit_text("Для создания промокода используйте команду <code>/createpromo</code>", reply_markup=create_back_button("admin_panel"), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "admin_cmd_stats")
async def admin_panel_stats(call: CallbackQuery):
    # Можно либо вызвать функцию cmd_stats, либо перенаправить на команду
    # Вызов функции напрямую чище, если она не требует объекта Message
    # await cmd_stats(call.message) # Передать message - не очень хорошо
    await call.message.edit_text("Для просмотра статистики используйте команду <code>/stats</code>", reply_markup=create_back_button("admin_panel"), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "admin_cmd_broadcast")
async def admin_panel_broadcast(call: CallbackQuery):
    await call.message.edit_text("Для запуска рассылки используйте команду <code>/broadcast</code>", reply_markup=create_back_button("admin_panel"), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.endswith("_user_start"))
async def admin_panel_user_action_info(call: CallbackQuery):
    action = call.data.split('_')[1]
    command_map = {
        "ban": "/ban",
        "unban": "/unban",
        "reset": "/resetuser"
    }
    command = command_map.get(action, "/help")
    await call.message.edit_text(
        f"Для выполнения действия '{action}' используйте команду <code>{command} ID</code> или ответьте командой <code>{command}</code> на сообщение пользователя.",
        reply_markup=create_back_button("admin_panel"),
        parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data.endswith("_admin_start"))
async def admin_panel_admin_action_info(call: CallbackQuery):
    # Требуется SuperAdmin права
    # ----- ИСПРАВЛЕНО ЗДЕСЬ: Использование await для фильтра -----
    if not await IsSuperAdminFilter()(call):
         await call.answer("Доступ запрещен.", show_alert=True)
         return
    action = call.data.split('_')[1]
    command_map = {
        "add": "/addadmin",
        "del": "/deladmin",
    }
    command = command_map.get(action, "/help")
    await call.message.edit_text(
        f"Для выполнения действия '{action} admin' используйте команду <code>{command} ID</code> или ответьте командой <code>{command}</code> на сообщение пользователя.",
        reply_markup=create_back_button("admin_panel"),
        parse_mode="HTML"
    )
    await call.answer()


# --- Shop Handler ---
@dp.callback_query(F.data.startswith("shop:"))
async def menu_shop(callback: CallbackQuery):
    """Отображает страницу магазина с кейсами."""
    try:
        current_page = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        current_page = 1

    all_cases = case_manager.get_all_cases()
    total_cases = len(all_cases)
    total_pages = (total_cases + SHOP_ITEMS_PER_PAGE - 1) // SHOP_ITEMS_PER_PAGE
    if total_pages == 0: total_pages = 1

    current_page = max(1, min(current_page, total_pages))

    start_index = (current_page - 1) * SHOP_ITEMS_PER_PAGE
    end_index = start_index + SHOP_ITEMS_PER_PAGE
    cases_on_page = all_cases[start_index:end_index]

    text = f"🔮 <b>Магазин Кейсов</b> (Стр. {current_page}/{total_pages})\n\n"
    shop_item_buttons = []

    if not cases_on_page:
        text += "ℹ️ В данный момент кейсов в продаже нет."
    else:
        for case in cases_on_page:
            price_str_parts = []
            buttons_row = []

            if case['price_coins'] > 0:
                 price_str_parts.append(f"{case['price_coins']} 🪙")
                 buttons_row.append(InlineKeyboardButton(text=f"Купить (🪙)", callback_data=f"buy_case:coins:{case['id']}"))
            if case['price_shards'] > 0:
                 price_str_parts.append(f"{case['price_shards']} 🀄️")
                 buttons_row.append(InlineKeyboardButton(text=f"Купить (🀄️)", callback_data=f"buy_case:shards:{case['id']}"))

            price_str = " или ".join(price_str_parts) if price_str_parts else "Бесплатно"

            text += f"📦 <b>{case['name']}</b> ({case['card_count']} карт)\n"
            if case['description']:
                text += f"   <i>{case['description']}</i>\n"
            text += f"   💰 Цена: {price_str}\n"

            if buttons_row:
                shop_item_buttons.append(buttons_row)
            shop_item_buttons.append([InlineKeyboardButton(text="═" * 15, callback_data="noop")])

        if shop_item_buttons and shop_item_buttons[-1][0].text.startswith("═"):
             shop_item_buttons.pop()

    keyboard = get_pagination_keyboard(
        position_prefix="shop",
        current_page=current_page,
        total_pages=total_pages,
        item_buttons=shop_item_buttons,
        back_callback="menu"
    )

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer()
        else:
            logging.error(f"Ошибка при редактировании сообщения магазина: {e}")
            await callback.answer("Произошла ошибка при обновлении магазина.", show_alert=True)
    await callback.answer() # Отвечаем на исходный callback в любом случае


@dp.callback_query(F.data.startswith("buy_case:"))
async def buy_case_handler(callback: CallbackQuery, bot: Bot):
    """Обрабатывает покупку и открытие кейса."""
    user_id = callback.from_user.id
    username = callback.from_user.first_name
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Ошибка данных покупки.", show_alert=True)
        return

    currency_type = parts[1]
    try:
        case_id = int(parts[2])
    except ValueError:
        await callback.answer("Неверный ID кейса.", show_alert=True)
        return

    await callback.answer(f"Открываем кейс...")

    obtained_cards, status_message = case_manager.open_case(user_id, case_id)

    # --- Обработка результата ---
    if obtained_cards is None:
        await callback.message.answer(
             f"🚫 Не удалось открыть кейс: {status_message}",
             reply_markup=create_back_button("shop:1")
         )
        try: await callback.message.delete()
        except Exception: pass
        return

    logging.info(f"User {user_id} opened case {case_id}. Received {len(obtained_cards)} cards. Status: {status_message}")

    result_text_lines = [f"🎉 {status_message}\n\n<b>Ты получил:</b>"]
    media_group = []
    has_images = False

    for i, card in enumerate(obtained_cards):
        rar_emoji = rarity_translate.get(card['rarity'], "<?>")[0:3].strip()
        card_line = f"{i+1}. {rar_emoji} <b>{card['name']}</b> (А:{card['attack']}/З:{card['health']})"
        result_text_lines.append(card_line)

        if card.get('image_path'):
            has_images = True
            caption_for_photo = card_line if len(obtained_cards) == 1 else (card_line if i == 0 and len(obtained_cards) <= 10 else None)
            media_group.append(InputMediaPhoto(media=card['image_path'], caption=caption_for_photo, parse_mode="HTML"))

    full_result_text = "\n".join(result_text_lines)

    try:
        try: await callback.message.delete()
        except Exception: pass

        if has_images and len(media_group) > 1:
             await bot.send_media_group(chat_id=user_id, media=media_group[:10])
             await bot.send_message(user_id, full_result_text, reply_markup=create_back_button("shop:1"), parse_mode="HTML")
        elif has_images and len(media_group) == 1:
             await bot.send_photo(chat_id=user_id, photo=media_group[0].media, caption=full_result_text, reply_markup=create_back_button("shop:1"), parse_mode="HTML")
        else:
             await bot.send_message(user_id, full_result_text, reply_markup=create_back_button("shop:1"), parse_mode="HTML")

        for card in obtained_cards:
             task_manager.update_task_progress(user_id, 'GET_CARD', rarity=card['rarity'])

    except Exception as e:
        logging.error(f"Ошибка при отправке результатов открытия кейса {case_id} для пользователя {user_id}: {e}", exc_info=True)
        await bot.send_message(user_id, full_result_text + "\n\n(Ошибка при отображении изображений)", reply_markup=create_back_button("shop:1"), parse_mode="HTML")


@dp.callback_query(F.data == "craft")
async def menu_craft(call: CallbackQuery):
    # ----- ИЗМЕНЕНИЕ ЗДЕСЬ: Использование await для get_user_info -----
    user_data = await user_manager.get_user_info(call.from_user.id)
    if not user_data:
        await call.answer("Не удалось получить данные пользователя.", show_alert=True)
        return

    craft_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Скрафтить из 🀄️", callback_data="craft_shard")],
        [back_button("menu")]
    ])
    text = (
        f"♻️ <b>{user_data.nickname}</b>, здесь ты можешь скрафтить попытки получения карт из осколков.\n\n"
        f"🧊 Осколки: <b>{user_data.shards}</b> 🀄️\n\n"
        f"⚙️ <b>Стоимость крафта:</b>\n"
        f"┗ 10 🀄️ осколков ➠ 1 случайная карта\n\n"
    )
    await call.message.edit_text(text=text, reply_markup=craft_keyboard, parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "craft_shard")
async def craft_shard(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.first_name
    cost = 10 # Стоимость крафта в осколках

    if user_manager.spend_shards(user_id, cost):
        await call.answer("Создаем карту из осколков...")
        card = card_manager.get_random_card(user_id, exclude_received=False)
        if card:
            result = card_manager.give_card_to_user(user_id, card['id'], card['rarity'], source='craft')
            if result.get('success'):
                caption = (
                    f"{username}, ты создал новую карточку из осколков! 💎\n"
                    f"\n✨ <b>{card['name']}</b>\n"
                    f"⚜️ Редкость: {rarity_translate.get(card['rarity'], card['rarity'].capitalize())}\n"
                    f"🔪 Атака: {card['attack']}\n"
                    f"❤️ Здоровье: {card['health']}\n"
                    f"💠 Ценность: {card['value']} pts"
                )
                photo_file_id = card.get('image_path')
                send_func = call.message.answer_photo if photo_file_id else call.message.answer
                kwargs = {"caption": caption, "parse_mode": "HTML", "reply_markup": main_menu()}
                if photo_file_id: kwargs["photo"] = photo_file_id

                try:
                    await send_func(**kwargs)
                    task_manager.update_task_progress(user_id, 'GET_CARD', rarity=card['rarity'])
                    # Обновляем сообщение с крафтом (показываем новый баланс)
                    await menu_craft(call)
                except Exception as e:
                    logging.error(f"Ошибка отправки карты после крафта для {user_id}: {e}")
                    await call.message.answer(caption, parse_mode="HTML", reply_markup=main_menu())
                    await menu_craft(call)

            else:
                logging.error(f"Не удалось выдать карту {card['id']} после крафта для {user_id}: {result.get('message')}")
                await call.message.answer("❌ Не удалось выдать карту после крафта. Осколки возвращены.", reply_markup=create_back_button("craft"))
                user_manager.add_shards(user_id, cost)
        else:
            logging.warning(f"Не удалось получить карту для крафта для {user_id} (нет карт?).")
            await call.message.answer("❌ Не удалось получить карту для крафта. Осколки возвращены.", reply_markup=create_back_button("craft"))
            user_manager.add_shards(user_id, cost)
    else:
        await call.answer("Недостаточно осколков для крафта!", show_alert=True)
        await menu_craft(call)


@dp.callback_query(F.data == "quests")
async def menu_quests(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.first_name
    try:
        formatted_message = task_manager.format_tasks_message(user_id, username)
        await call.message.edit_text(
            text=formatted_message,
            reply_markup=create_back_button("menu"),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке /quests для user_id={user_id}: {e}", exc_info=True)
        await call.message.edit_text("😕 Произошла ошибка при получении ваших заданий. Попробуйте позже.", reply_markup=create_back_button("menu"))
    await call.answer()


@dp.callback_query(F.data == "referral")
async def menu_referral(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.first_name or "Друг"

    user_data = user_manager.get_user_raw(user_id)
    invited_count = user_data.get('referrals', 0) if user_data else 0
    attempts_from_refs = invited_count // 3

    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    html_link = f"<code>{ref_link}</code>"

    text = (
        f"🔗 <b>{username}</b>, приводи друзей в игру по своей ссылке и получай бонусы!\n\n"
        f"🎁 За каждых <b>трёх</b> друзей ты получишь <b>1</b> попытку получения карты.\n\n"
        f"📈 Приглашено игроков: <b>{invited_count}</b>\n"
        f"🪄 Получено попыток за рефералов: <b>{attempts_from_refs}</b>\n"
        f"⬇️ Твоя ссылка (нажми, чтобы скопировать):\n{html_link}"
    )

    await call.message.edit_text(text, reply_markup=create_back_button("menu"), parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "spin_bonus")
async def menu_spin_bonus(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.first_name or "Игрок"

    total_received = user_manager.get_total_cards_received(user_id)

    text = f"🎁 <b>{username}</b>, получай карты и достигай целей для получения наград!\n\n"
    text += f"Всего получено карт (круток): <b>{total_received}</b>\n\n"
    text += "<b>Награды за количество полученных карт:</b>\n"

    for goal, coins_reward, shards_reward in reward_levels:
        status = "✅" if total_received >= goal else "⏳"
        reward_parts = []
        if coins_reward > 0: reward_parts.append(f"{coins_reward} 🪙")
        if shards_reward > 0: reward_parts.append(f"{shards_reward} 🀄️")
        reward_line = " + ".join(reward_parts) if reward_parts else "Нет"
        progress_text = f"{min(total_received, goal)}/{goal}"
        text += f"{status} <b>{goal} карт:</b> {reward_line} (Прогресс: {progress_text})\n"

    await call.message.edit_text(text, reply_markup=create_back_button("menu"), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "pass")
async def menu_pass(call: CallbackQuery):
    # Логика отображения информации о Battle Pass
    kb = [
        [InlineKeyboardButton(text="🌠 Купить пропуск", callback_data="buy_pass")], # Нужен обработчик buy_pass
        [back_button("menu")],
    ]
    builder = InlineKeyboardBuilder(markup=kb)
    await call.message.edit_text(
        "💼 Pass - 🔒 <b>Что даст тебе PoTi Pass?</b>\n\n"
        "⛺ <b>Создай собственный клан</b>\n"
        "⏳ <b>Получай карточки каждые 3 часа</b> вместо 4\n"
        "🏟 <b>Сражайся на арене каждый час</b> вместо 2\n"
        "🕒 <b>Уведомления о завершении времени ожидания</b> карт и арены\n"
        "👾 <b>Уведомления о времени сражений с боссом</b>\n"
        "👻 <b>Повышенная вероятность</b> выпадения лег., эпич. и миф. карт\n"
        "🧍 <b>Используй смайлики в никнейме</b>\n"
        "🌀 <b>+3 крутки</b> при покупке\n" # Уточнено
        "🗓 <b>Срок действия:</b> 30 дней\n"
        "🔑 <b>Стоимость:</b> 159 рублей", # Или другая цена
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data == "rating:season")
async def menu_rating_season(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.first_name

    top_users = user_manager.get_top_users_by_season()
    user_rank = user_manager.get_user_season_rank(user_id)

    text = format_top_message("🏆 Топ-10 игроков этого сезона", top_users, user_rank, username, 'season_rating')
    await call.message.edit_text(text, reply_markup=create_back_button("rating"), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "rating:all")
async def menu_rating_all(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.first_name

    top_users = user_manager.get_top_users_alltime()
    user_rank = user_manager.get_user_alltime_rank(user_id)

    text = format_top_message("🌠 Топ-10 игроков за всё время", top_users, user_rank, username, 'rating')
    await call.message.edit_text(text, reply_markup=create_back_button("rating"), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "rating:clans")
async def menu_rating_clans(call: CallbackQuery):
    # TODO: Реализовать показ рейтинга кланов
    # top_clans = clan_manager.get_top_clans()
    # text = format_clan_top_message(...)
    await call.answer("Рейтинг кланов пока в разработке", show_alert=True)
    # await call.message.edit_text(text, reply_markup=create_back_button("rating"))

@dp.callback_query(F.data == "rating")
async def menu_rating(call: CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="🏆 Топ этого сезона", callback_data="rating:season")],
        [InlineKeyboardButton(text="🌠 Топ за всё время", callback_data="rating:all")],
        [InlineKeyboardButton(text="🏰 Топ кланов", callback_data="rating:clans")], # Пока заглушка
        [back_button("menu")]
    ]
    builder = InlineKeyboardBuilder(markup=kb)
    await call.message.edit_text(
        f"📊 {call.from_user.first_name}, выбери категорию рейтинга:",
        reply_markup=builder.as_markup()
    )
    await call.answer()

def format_top_message(title: str, top_rows: list, user_place: Optional[int], username: str, rating_key: str) -> str:
    """Форматирует сообщение с топом игроков."""
    lines = [f"<b>{title}</b>", "➖➖➖➖➖➖"]

    if not top_rows:
        lines.append("<i>Пока пусто...</i>")
    else:
        for i, row in enumerate(top_rows, start=1):
            # Используем get с default, если username может быть None
            name = row.get("username") or f"User_{row.get('user_id', '?')}"
            # Получаем рейтинг по ключу (rating или season_rating)
            rating = row.get(rating_key, 0)
            lines.append(f"{i}. {name} - {format_rating(rating)}")

    lines.append("➖➖➖➖➖➖")
    place_str = f"{user_place}" if user_place is not None else "не в топе"
    lines.append(f"👤 {username}, твое место: {place_str}")
    return "\n".join(lines)

def format_rating(points: int) -> str:
    """Форматирует очки в k или m формат."""
    if points >= 1_000_000:
        # Округляем до 1 знака после запятой
        return f"{points / 1_000_000:.1f}M pts".replace('.0M', 'M')
    elif points >= 1_000:
        return f"{points / 1_000:.1f}k pts".replace('.0k', 'k')
    else:
        return f"{points} pts"

@dp.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    """Пустой обработчик для кнопок-плейсхолдеров."""
    await callback.answer()