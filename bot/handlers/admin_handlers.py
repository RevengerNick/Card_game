# bot\handlers\admin_handlers.py
import asyncio
import logging
import shlex # For parsing arguments with spaces
from typing import Optional, List, Dict, Any, Union # Added Union
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputMediaPhoto
)
from aiogram.filters import Command, CommandObject, Filter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError

# Import necessary managers and database instance from central point
from bot.Classes.db_manager import user_manager, card_manager, promo_manager, case_manager, db
# Import constants, helpers
from bot.card_database import RARITY_CHOICES, rarity_translate, SUPER_ADMIN_ID
# Import back button helper if needed within this file directly
from bot.handlers.mainMenu import back_button # Or define a local helper
from bot.utils.Filters import IsAdminFilter, IsSuperAdminFilter

# Ensure managers are initialized (consider a check function or rely on startup)
if not all([user_manager, card_manager, promo_manager, case_manager, db]):
     # This check might be better placed at the application entry point (main.py)
     logging.critical("ADMIN HANDLERS: Один или несколько менеджеров не инициализированы!")
     # Depending on setup, handlers might not load correctly if managers are None.
     # For robustness, you could wrap handler logic in checks like `if not case_manager: return`

admin_router = Router()

# --- Admin Check Filters ---





# Apply admin filter to all handlers in this router
admin_router.message.filter(IsAdminFilter())
admin_router.callback_query.filter(IsAdminFilter())

# --- States for FSM ---

class CreateCardStates(StatesGroup):
    WaitingForPhoto = State()
    WaitingForName = State()
    WaitingForRarity = State()
    WaitingForAttack = State()
    WaitingForHealth = State()
    WaitingForValue = State()
    ConfirmCard = State()

class CreatePromoStates(StatesGroup):
    WaitingForCode = State()
    WaitingForReward = State()
    WaitingForUses = State()
    ConfirmPromo = State()

class BroadcastState(StatesGroup):
    WaitingForMessage = State()
    ConfirmBroadcast = State()

class CreateCaseStates(StatesGroup): # Состояния для создания кейса
    WaitingForName = State()
    WaitingForDescription = State()
    WaitingForCardCount = State()
    WaitingForPriceCoins = State()
    WaitingForPriceShards = State()
    ConfirmCase = State()

# --- Helper Functions ---

def get_rarity_keyboard() -> ReplyKeyboardMarkup:
    """Создает клавиатуру ответа с выбором редкости."""
    buttons = [KeyboardButton(text=rarity_translate.get(r, r.capitalize())) for r in RARITY_CHOICES]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_confirmation_keyboard(confirm_callback: str = "admin_confirm", cancel_callback: str = "admin_cancel") -> InlineKeyboardMarkup:
    """Создает стандартную инлайн-клавиатуру подтверждения."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=confirm_callback),
            InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_callback)
        ]
    ])

async def parse_user_id(message: Message, command_args: Optional[str]) -> Optional[int]:
    """Извлекает ID пользователя из аргументов команды или ответа на сообщение."""
    target_user_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user_id = message.reply_to_message.from_user.id
        logging.debug(f"Используется ID пользователя {target_user_id} из ответа на сообщение.")

    if command_args and not target_user_id: # Парсим аргументы только если не взят ID из ответа
        args_list = command_args.strip().split()
        if args_list:
            potential_id = args_list[0].replace('@', '') # Удаляем @, если упомянули
            if potential_id.isdigit():
                 target_user_id = int(potential_id)
                 logging.debug(f"Используется ID пользователя {target_user_id} из аргументов команды.")

    if target_user_id is None:
        await message.reply("⚠️ Укажите ID пользователя (число) или ответьте на его сообщение.")
        return None

    return target_user_id

# --- Admin Management Commands (Require Super Admin) ---

@admin_router.message(Command("addadmin"), IsSuperAdminFilter())
async def cmd_add_admin(message: Message, command: CommandObject):
    target_user_id = await parse_user_id(message, command.args)
    if target_user_id is None: return

    if user_manager.is_admin(target_user_id):
        await message.reply(f"✅ Пользователь ID `{target_user_id}` уже является администратором.")
        return

    if not user_manager.get_user_raw(target_user_id):
         await message.reply(f"❌ Пользователь ID `{target_user_id}` не найден в базе. Попросите его сначала запустить /start.")
         return

    if user_manager.add_admin(target_user_id):
        await message.reply(f"✅ Пользователь ID `{target_user_id}` успешно назначен администратором.")
        try:
            await message.bot.send_message(target_user_id, "🎉 Поздравляем! Вы были назначены администратором.")
        except TelegramAPIError as e:
            logging.warning(f"Не удалось уведомить нового админа {target_user_id}: {e}")
        except Exception as e:
             logging.error(f"Неожиданная ошибка при уведомлении нового админа {target_user_id}: {e}")
    else:
        await message.reply(f"❌ Не удалось назначить администратора ID `{target_user_id}`. Произошла ошибка БД или пользователь не найден.")

@admin_router.message(Command("deladmin"), IsSuperAdminFilter())
async def cmd_del_admin(message: Message, command: CommandObject):
    target_user_id = await parse_user_id(message, command.args)
    if target_user_id is None: return

    if target_user_id == message.from_user.id:
        await message.reply("❌ Вы не можете удалить себя из администраторов.")
        return
    if target_user_id in SUPER_ADMIN_ID:
         await message.reply("❌ Нельзя удалить Супер Администратора.")
         return

    if not user_manager.is_admin(target_user_id):
        await message.reply(f"ℹ️ Пользователь ID `{target_user_id}` не является администратором.")
        return

    if user_manager.remove_admin(target_user_id):
        await message.reply(f"✅ Пользователь ID `{target_user_id}` успешно удален из администраторов.")
        try:
            await message.bot.send_message(target_user_id, "ℹ️ Вы были удалены из списка администраторов.")
        except TelegramAPIError as e:
            logging.warning(f"Не удалось уведомить удаленного админа {target_user_id}: {e}")
        except Exception as e:
             logging.error(f"Неожиданная ошибка при уведомлении удаленного админа {target_user_id}: {e}")
    else:
        await message.reply(f"❌ Не удалось удалить администратора ID `{target_user_id}`. Ошибка БД или он не был админом.")

@admin_router.message(Command("admins"), IsAdminFilter()) # Любой админ может посмотреть список
async def cmd_list_admins(message: Message):
    admin_rows = db.execute("SELECT user_id, added_at FROM admins ORDER BY added_at", fetch='all')
    if not admin_rows:
        await message.reply("ℹ️ Список администраторов пуст.")
        return

    admin_list = ["👑 <b>Список администраторов:</b>\n"]
    for i, admin in enumerate(admin_rows, 1):
        user_id = admin['user_id']
        user_info = user_manager.get_user_raw(user_id)
        username = user_info.get('username') if user_info else None
        name_display = f"@{username}" if username else f"ID {user_id}"
        status = " (👑 <b>SUPER</b>)" if user_id == SUPER_ADMIN_ID else ""
        admin_list.append(f"{i}. {name_display}{status}")

    await message.reply("\n".join(admin_list), parse_mode="HTML")


# --- Card Creation Command (Any Admin) ---

@admin_router.message(Command("createcard"), StateFilter(None))
async def cmd_create_card_start(message: Message, state: FSMContext):
    await message.reply("🖼️ Пожалуйста, отправьте <b>фотографию</b> для новой карты.", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CreateCardStates.WaitingForPhoto)
    await state.update_data(card_data={})

# Обработка отмены состояния
@admin_router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel_state(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.reply("Нет активной операции для отмены.", reply_markup=ReplyKeyboardRemove())
        return

    logging.info(f"Отмена состояния {current_state} пользователем {message.from_user.id}")
    await state.clear()
    await message.reply("Операция отменена.", reply_markup=ReplyKeyboardRemove())

@admin_router.message(CreateCardStates.WaitingForPhoto, F.photo)
async def process_card_photo(message: Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    data = await state.get_data()
    card_data = data.get('card_data', {})
    card_data['image_path'] = photo_file_id
    await state.update_data(card_data=card_data)
    await message.reply("🏷️ Теперь введите <b>название</b> карты (уникальное):")
    await state.set_state(CreateCardStates.WaitingForName)

@admin_router.message(CreateCardStates.WaitingForPhoto, ~F.photo)
async def process_card_photo_invalid(message: Message):
     await message.reply("❌ Пожалуйста, отправьте именно <b>фотографию</b>.")

@admin_router.message(CreateCardStates.WaitingForName, F.text)
async def process_card_name(message: Message, state: FSMContext):
    card_name = message.text.strip()
    if not card_name:
        await message.reply("❌ Название карты не может быть пустым.")
        return
    existing_card = db.execute("SELECT id FROM cards WHERE name = %s", (card_name,), fetch='one')
    if existing_card:
        await message.reply(f"❌ Карта с названием '{card_name}' уже существует (ID: {existing_card['id']}). Введите другое название.")
        return
    data = await state.get_data()
    card_data = data.get('card_data', {})
    card_data['name'] = card_name
    await state.update_data(card_data=card_data)
    await message.reply("✨ Выберите <b>редкость</b> карты:", reply_markup=get_rarity_keyboard())
    await state.set_state(CreateCardStates.WaitingForRarity)

@admin_router.message(CreateCardStates.WaitingForRarity, F.text)
async def process_card_rarity(message: Message, state: FSMContext):
    input_text = message.text.strip()
    selected_rarity = None
    for key, display_name in rarity_translate.items():
        if display_name.strip() == input_text:
            selected_rarity = key
            break
    if not selected_rarity and input_text.lower() in RARITY_CHOICES:
         selected_rarity = input_text.lower()

    if not selected_rarity or selected_rarity not in RARITY_CHOICES:
        await message.reply("❌ Неверная редкость. Пожалуйста, выберите из предложенных кнопок.", reply_markup=get_rarity_keyboard())
        return
    data = await state.get_data()
    card_data = data.get('card_data', {})
    card_data['rarity'] = selected_rarity
    await state.update_data(card_data=card_data)
    await message.reply("🔪 Введите <b>атаку</b> карты (целое число >= 0):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CreateCardStates.WaitingForAttack)

@admin_router.message(CreateCardStates.WaitingForAttack, F.text)
async def process_card_attack(message: Message, state: FSMContext):
    try:
        attack = int(message.text.strip())
        if attack < 0: raise ValueError("Атака не может быть отрицательной.")
        data = await state.get_data()
        card_data = data.get('card_data', {})
        card_data['attack'] = attack
        await state.update_data(card_data=card_data)
        await message.reply("❤️ Введите <b>здоровье</b> карты (целое число > 0):")
        await state.set_state(CreateCardStates.WaitingForHealth)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое неотрицательное число для атаки.")

@admin_router.message(CreateCardStates.WaitingForHealth, F.text)
async def process_card_health(message: Message, state: FSMContext):
    try:
        health = int(message.text.strip())
        if health <= 0: raise ValueError("Здоровье должно быть положительным.")
        data = await state.get_data()
        card_data = data.get('card_data', {})
        card_data['health'] = health
        await state.update_data(card_data=card_data)
        await message.reply("💠 Введите <b>ценность</b> карты (целое число >= 0):")
        await state.set_state(CreateCardStates.WaitingForValue)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое положительное число для здоровья.")

@admin_router.message(CreateCardStates.WaitingForValue, F.text)
async def process_card_value(message: Message, state: FSMContext):
    try:
        value = int(message.text.strip())
        if value < 0: raise ValueError("Ценность не может быть отрицательной.")
        data = await state.get_data()
        card_data = data.get('card_data', {})
        card_data['value'] = value
        await state.update_data(card_data=card_data)

        # --- Шаг подтверждения ---
        rarity_display = rarity_translate.get(card_data['rarity'], card_data['rarity'].capitalize())
        confirm_text = (
            f"<b>Проверьте данные карты:</b>\n\n"
            f"🏷️ Название: {card_data['name']}\n"
            f"✨ Редкость: {rarity_display}\n"
            f"🔪 Атака: {card_data['attack']}\n"
            f"❤️ Здоровье: {card_data['health']}\n"
            f"💠 Ценность: {card_data['value']}\n\n"
            f"Создаем карту?"
        )
        try:
            await message.answer_photo(
                photo=card_data['image_path'],
                caption=confirm_text,
                reply_markup=get_confirmation_keyboard(),
                parse_mode="HTML"
            )
            await state.set_state(CreateCardStates.ConfirmCard)
        except TelegramBadRequest as e:
             logging.error(f"Error sending confirmation photo: {e}")
             await message.reply("❌ Не удалось отправить фото для подтверждения. Попробуйте снова /createcard")
             await state.clear()
        except Exception as e:
             logging.error(f"Unexpected error during card confirmation: {e}")
             await message.reply("❌ Произошла непредвиденная ошибка. Попробуйте снова.")
             await state.clear()
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое неотрицательное число для ценности.")

# --- Statistics Commands (Any Admin) ---

@admin_router.message(Command("stats"))
async def cmd_stats(message: Message):
    user_count = user_manager.get_total_user_count()
    user_count_noban = user_manager.get_total_user_count(include_banned=False)
    cards_given = user_manager.get_total_cards_given_out()
    pass_count = user_manager.get_battle_pass_count()
    currency = user_manager.get_total_currency_in_system()

    stats_text = (
        f"📊 <b>Статистика Бота:</b>\n\n"
        f"👤 Всего пользователей: {user_count} (Активных: {user_count_noban})\n"
        f"🃏 Всего выдано карт (круток): {cards_given}\n"
        f"🎫 Активных Battle Pass: {pass_count}\n"
        f"🪙 Всего PoTi Coin в системе: {currency.get('coins', 0)}\n"
        f"🀄️ Всего Осколков в системе: {currency.get('shards', 0)}"
        # Добавить статистику по редким осколкам, если нужно
    )
    await message.reply(stats_text, parse_mode="HTML")

# --- Promo Code Creation Command (Any Admin) ---

@admin_router.message(Command("createpromo"), StateFilter(None))
async def cmd_create_promo_start(message: Message, state: FSMContext):
    await message.reply("📝 Введите <b>код</b> для промокода (4-20 букв/цифр, или 'auto' для генерации):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CreatePromoStates.WaitingForCode)
    await state.update_data(promo_data={})

@admin_router.message(CreatePromoStates.WaitingForCode, F.text)
async def process_promo_code(message: Message, state: FSMContext):
    code_input = message.text.strip()
    promo_data = (await state.get_data()).get('promo_data', {})

    if code_input.lower() == 'auto':
        promo_data['code'] = None # Менеджер сгенерирует
    else:
        if not (4 <= len(code_input) <= 20 and code_input.isalnum()):
            await message.reply("❌ Код должен быть от 4 до 20 символов и состоять только из латинских букв и цифр.")
            return
        # Проверка существования кода
        if promo_manager.db.execute("SELECT 1 FROM promo_achievements WHERE code = %s", (code_input,), fetch='one'):
            await message.reply(f"❌ Промокод '{code_input}' уже существует. Введите другой или 'auto'.")
            return
        promo_data['code'] = code_input

    await state.update_data(promo_data=promo_data)
    await message.reply("💰 Введите <b>сумму награды</b> (в PoTi Coin, число > 0):")
    await state.set_state(CreatePromoStates.WaitingForReward)

@admin_router.message(CreatePromoStates.WaitingForReward, F.text)
async def process_promo_reward(message: Message, state: FSMContext):
    try:
        reward = int(message.text.strip())
        if reward <= 0: raise ValueError("Награда должна быть положительной.")
        promo_data = (await state.get_data()).get('promo_data', {})
        promo_data['reward'] = reward
        await state.update_data(promo_data=promo_data)
        await message.reply("🔄 Введите <b>количество использований</b> (число > 0):")
        await state.set_state(CreatePromoStates.WaitingForUses)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое положительное число для награды.")

@admin_router.message(CreatePromoStates.WaitingForUses, F.text)
async def process_promo_uses(message: Message, state: FSMContext):
    try:
        uses = int(message.text.strip())
        if uses <= 0: raise ValueError("Количество использований должно быть положительным.")
        promo_data = (await state.get_data()).get('promo_data', {})
        promo_data['uses'] = uses
        await state.update_data(promo_data=promo_data)

        # --- Подтверждение ---
        code_display = promo_data.get('code') or "(авто)"
        confirm_text = (
            f"<b>Проверьте данные промокода:</b>\n\n"
            f"📝 Код: <code>{code_display}</code>\n" # Используем code для HTML
            f"💰 Награда: {promo_data['reward']} 🪙\n"
            f"🔄 Использований: {promo_data['uses']}\n\n"
            f"Создаем промокод?"
        )
        await message.reply(confirm_text, reply_markup=get_confirmation_keyboard(), parse_mode="HTML")
        await state.set_state(CreatePromoStates.ConfirmPromo)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое положительное число для использований.")


# --- Broadcast Command (Any Admin) ---

@admin_router.message(Command("broadcast"), StateFilter(None))
async def cmd_broadcast_start(message: Message, state: FSMContext):
    await message.reply("📢 Введите сообщение для рассылки всем <b>НЕ</b> забаненным пользователям (поддерживает HTML-разметку). Используйте /cancel для отмены.", reply_markup=ReplyKeyboardRemove())
    await state.set_state(BroadcastState.WaitingForMessage)

@admin_router.message(BroadcastState.WaitingForMessage, F.text)
async def process_broadcast_message(message: Message, state: FSMContext):
    if not message.text or message.text.isspace():
        await message.reply("❌ Сообщение для рассылки не может быть пустым.")
        return

    broadcast_text_html = message.html_text # Сохраняем HTML-разметку
    await state.update_data(broadcast_message=broadcast_text_html)

    # Показываем предпросмотр админу
    preview_text = f"<b>Предпросмотр сообщения:</b>\n\n{broadcast_text_html}\n\n--------\n\nОтправляем?"

    await message.reply(preview_text, reply_markup=get_confirmation_keyboard(), parse_mode="HTML")
    await state.set_state(BroadcastState.ConfirmBroadcast)


# --- User Management Commands (Any Admin, with restrictions) ---

@admin_router.message(Command("ban"))
async def cmd_ban_user(message: Message, command: CommandObject):
    target_user_id = await parse_user_id(message, command.args)
    if target_user_id is None: return

    if target_user_id == message.from_user.id:
        await message.reply("❌ Нельзя забанить самого себя.")
        return

    is_target_admin = user_manager.is_admin(target_user_id)
    is_caller_super = await IsSuperAdminFilter()(message) # Проверяем права вызывающего

    # Обычный админ не может банить другого админа или суперадмина
    if is_target_admin and not is_caller_super:
         await message.reply("❌ Вы не можете забанить другого администратора (только Супер Админ).")
         return
    # Никто не может банить суперадмина (кроме него самого, что предотвращено выше)
    if target_user_id == SUPER_ADMIN_ID and message.from_user.id != SUPER_ADMIN_ID:
         await message.reply("❌ Нельзя забанить Супер Администратора.")
         return

    user_data = user_manager.get_user_raw(target_user_id)
    if not user_data:
        await message.reply(f"❌ Пользователь ID `{target_user_id}` не найден.")
        return
    if user_data.get('is_banned', False):
        await message.reply(f"ℹ️ Пользователь ID `{target_user_id}` уже забанен.")
        return

    if user_manager.ban_user(target_user_id):
        admin_removed_msg = ""
        if is_target_admin:
            # Если баним админа, также удаляем его из админов (делает только суперадмин)
            if is_caller_super:
                 user_manager.remove_admin(target_user_id)
                 admin_removed_msg = " и удален из администраторов"
            else:
                 # Этого не должно произойти из-за проверок выше, но для полноты
                 admin_removed_msg = " (статус админа не снят, т.к. вы не Супер Админ)"

        await message.reply(f"✅ Пользователь ID `{target_user_id}` успешно забанен{admin_removed_msg}.")
        try:
            # Уведомляем пользователя о бане
            await message.bot.send_message(target_user_id, "🚫 Ваш аккаунт был заблокирован администратором.")
        except Exception as e:
            logging.info(f"Не удалось уведомить забаненного пользователя {target_user_id}: {e}")
    else:
        await message.reply(f"❌ Не удалось забанить пользователя ID `{target_user_id}`. Ошибка БД.")

@admin_router.message(Command("unban"))
async def cmd_unban_user(message: Message, command: CommandObject):
    target_user_id = await parse_user_id(message, command.args)
    if target_user_id is None: return

    user_data = user_manager.get_user_raw(target_user_id)
    if not user_data:
        await message.reply(f"❌ Пользователь ID `{target_user_id}` не найден.")
        return
    if not user_data.get('is_banned', False):
        await message.reply(f"ℹ️ Пользователь ID `{target_user_id}` не забанен.")
        return

    if user_manager.unban_user(target_user_id):
        await message.reply(f"✅ Пользователь ID `{target_user_id}` успешно разбанен.")
        try:
            await message.bot.send_message(target_user_id, "🎉 Ваш аккаунт был разблокирован администратором.")
        except Exception as e:
            logging.info(f"Не удалось уведомить разбаненного пользователя {target_user_id}: {e}")
    else:
        await message.reply(f"❌ Не удалось разбанить пользователя ID `{target_user_id}`. Ошибка БД.")

@admin_router.message(Command("resetuser"))
async def cmd_reset_user(message: Message, command: CommandObject):
    args_str = command.args or ""
    try:
        # Используем shlex для безопасного разбора аргументов с возможными кавычками
        args = shlex.split(args_str)
    except ValueError:
        await message.reply("⚠️ Ошибка разбора аргументов. Используйте кавычки для ID или username с пробелами, если необходимо.")
        return

    target_user_id_str = args[0] if args else None
    confirmation = args[1] if len(args) > 1 else None

    target_user_id = None

    if message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
    elif target_user_id_str:
         if target_user_id_str.isdigit():
             target_user_id = int(target_user_id_str)
         else:
             # Поиск по username? Пока не реализован.
             await message.reply("⚠️ Поиск по username не поддерживается. Укажите ID или ответьте на сообщение.")
             return
    else:
         await message.reply("⚠️ Укажите ID пользователя или ответьте на его сообщение.")
         return

    if target_user_id is None: return # Сообщение об ошибке уже отправлено

    if target_user_id == message.from_user.id:
        await message.reply("❌ Нельзя сбросить свой аккаунт.")
        return

    is_target_admin = user_manager.is_admin(target_user_id)
    is_caller_super = await IsSuperAdminFilter()(message)

    if is_target_admin and not is_caller_super:
        await message.reply("❌ Нельзя сбросить аккаунт другого администратора (только Супер Админ).")
        return
    if target_user_id == SUPER_ADMIN_ID and message.from_user.id != SUPER_ADMIN_ID:
        await message.reply("❌ Нельзя сбросить аккаунт Супер Администратора.")
        return

    if not user_manager.get_user_raw(target_user_id):
        await message.reply(f"❌ Пользователь ID `{target_user_id}` не найден.")
        return

    if confirmation != "CONFIRM":
        await message.reply(
            f"⚠️ <b>ПРЕДУПРЕЖДЕНИЕ!</b> Это действие необратимо удалит ВСЕ данные пользователя ID `{target_user_id}` (карты, колоды, валюту, прогресс, статистику и т.д.).\n\n"
            f"Для подтверждения выполните команду еще раз, добавив <code>CONFIRM</code> в конце:\n"
            f"<code>/resetuser {target_user_id} CONFIRM</code>",
            parse_mode="HTML"
        )
        return

    # --- Выполнение сброса ---
    await message.reply(f"⏳ Выполняется сброс аккаунта ID `{target_user_id}`...")
    if user_manager.reset_user_account(target_user_id):
        admin_removed_msg = ""
        # Если сбрасываемый был админом, удаляем его из админов (только суперадмин)
        if is_target_admin and is_caller_super:
             user_manager.remove_admin(target_user_id)
             admin_removed_msg = " (и удален из админов)"

        await message.reply(f"✅ Аккаунт пользователя ID `{target_user_id}` успешно сброшен{admin_removed_msg}.")
        try:
            await message.bot.send_message(target_user_id, "ℹ️ Ваш аккаунт был сброшен администратором до начального состояния.")
        except Exception as e:
            logging.info(f"Не удалось уведомить пользователя о сбросе {target_user_id}: {e}")
    else:
        await message.reply(f"❌ Не удалось сбросить аккаунт пользователя ID `{target_user_id}`. Ошибка БД.")


# --- Case/Pack Management Commands (Any Admin) ---

@admin_router.message(Command("createcase"), StateFilter(None))
async def cmd_create_case_start(message: Message, state: FSMContext):
    await message.reply("📦 Введите <b>название</b> нового кейса:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CreateCaseStates.WaitingForName)
    await state.update_data(case_data={})

@admin_router.message(CreateCaseStates.WaitingForName, F.text)
async def process_case_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.reply("❌ Название кейса не может быть пустым.")
        return
    if case_manager.get_case_by_name(name):
         await message.reply(f"❌ Кейс с названием '{name}' уже существует. Введите другое.")
         return
    data = await state.get_data()
    case_data = data.get('case_data', {})
    case_data['name'] = name
    await state.update_data(case_data=case_data)
    await message.reply("📝 Введите <b>описание</b> кейса (или '-' если нет):")
    await state.set_state(CreateCaseStates.WaitingForDescription)

@admin_router.message(CreateCaseStates.WaitingForDescription, F.text)
async def process_case_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    data = await state.get_data()
    case_data = data.get('case_data', {})
    case_data['description'] = None if desc == '-' else desc
    await state.update_data(case_data=case_data)
    await message.reply("🔢 Введите <b>количество карт</b>, выпадающих из кейса (число > 0):")
    await state.set_state(CreateCaseStates.WaitingForCardCount)

@admin_router.message(CreateCaseStates.WaitingForCardCount, F.text)
async def process_case_card_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        if count <= 0: raise ValueError("Количество карт должно быть положительным.")
        data = await state.get_data()
        case_data = data.get('case_data', {})
        case_data['card_count'] = count
        await state.update_data(case_data=case_data)
        await message.reply("💰 Введите <b>цену в PoTi Coin</b> (число >= 0, 0 если бесплатно):")
        await state.set_state(CreateCaseStates.WaitingForPriceCoins)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое положительное число.")

@admin_router.message(CreateCaseStates.WaitingForPriceCoins, F.text)
async def process_case_price_coins(message: Message, state: FSMContext):
    try:
        price = int(message.text.strip())
        if price < 0: raise ValueError("Цена не может быть отрицательной.")
        data = await state.get_data()
        case_data = data.get('case_data', {})
        case_data['price_coins'] = price
        await state.update_data(case_data=case_data)
        await message.reply("🧊 Введите <b>цену в Осколках</b> (число >= 0, 0 если бесплатно):")
        await state.set_state(CreateCaseStates.WaitingForPriceShards)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое неотрицательное число.")

@admin_router.message(CreateCaseStates.WaitingForPriceShards, F.text)
async def process_case_price_shards(message: Message, state: FSMContext):
    try:
        price = int(message.text.strip())
        if price < 0: raise ValueError("Цена не может быть отрицательной.")
        data = await state.get_data()
        case_data = data.get('case_data', {})
        case_data['price_shards'] = price
        await state.update_data(case_data=case_data)

        # --- Подтверждение ---
        confirm_text = (
            f"<b>Проверьте данные кейса:</b>\n\n"
            f"📦 Название: {case_data['name']}\n"
            f"📝 Описание: {case_data['description'] or 'Нет'}\n"
            f"🔢 Карт в кейсе: {case_data['card_count']}\n"
            f"💰 Цена (монеты): {case_data['price_coins']} 🪙\n"
            f"🧊 Цена (осколки): {case_data['price_shards']} 🀄️\n\n"
            f"Создаем кейс?"
        )
        await message.reply(confirm_text, reply_markup=get_confirmation_keyboard(), parse_mode="HTML")
        await state.set_state(CreateCaseStates.ConfirmCase)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое неотрицательное число.")


@admin_router.message(Command("deletecase"))
async def cmd_delete_case(message: Message, command: CommandObject):
    args_str = command.args
    if not args_str:
        await message.reply("⚠️ Укажите ID или Название кейса для удаления.\nИспользование: `/deletecase <ID или \"Название\"> [CONFIRM]`")
        return

    try:
        args = shlex.split(args_str)
    except ValueError:
        await message.reply("⚠️ Ошибка разбора аргументов. Используйте кавычки для названий с пробелами.")
        return

    identifier = args[0] if args else None
    confirmation = args[1] if len(args) > 1 else None

    if not identifier:
        await message.reply("⚠️ Укажите ID или Название кейса.")
        return

    case_info = None
    try:
        # Попытка найти по ID
        case_id = int(identifier)
        case_info = case_manager.get_case_by_id(case_id)
    except ValueError:
        # Если не ID, ищем по имени
        case_info = case_manager.get_case_by_name(identifier)

    if not case_info:
        await message.reply(f"❌ Кейс '{identifier}' не найден.")
        return

    case_id_to_delete = case_info['id']
    case_name_to_delete = case_info['name']

    if confirmation != "CONFIRM":
        await message.reply(
            f"⚠️ <b>ПРЕДУПРЕЖДЕНИЕ!</b> Это действие безвозвратно удалит кейс '{case_name_to_delete}' (ID: {case_id_to_delete}) и все связи карт с ним.\n\n"
            f"Для подтверждения выполните команду еще раз, добавив <code>CONFIRM</code> в конце:\n<code>/deletecase \"{identifier}\" CONFIRM</code>",
            parse_mode="HTML"
        )
        return

    if case_manager.delete_case(case_id_to_delete):
        await message.reply(f"✅ Кейс '{case_name_to_delete}' (ID: {case_id_to_delete}) успешно удален.")
    else:
        await message.reply(f"❌ Не удалось удалить кейс '{case_name_to_delete}'. Ошибка БД или кейс не найден.")


@admin_router.message(Command("addcardtocase"))
async def cmd_add_card_to_case(message: Message, command: CommandObject):
    args_str = command.args
    usage_text = "⚠️ Использование: `/addcardtocase <ID или \"Назв. Кейса\"> <ID или \"Назв. Карты\"> <Вес>`\nПример: `/addcardtocase \"Epic Pack\" 123 10`"
    if not args_str:
        await message.reply(usage_text)
        return

    try:
        args = shlex.split(args_str)
        if len(args) != 3: raise ValueError("Неверное количество аргументов")
    except ValueError as e:
        logging.warning(f"Failed to parse addcardtocase args '{args_str}': {e}")
        await message.reply(f"{usage_text}\nОшибка: {e}")
        return

    case_identifier, card_identifier, weight_str = args

    # --- Найти ID кейса ---
    case_info = None
    try:
        case_id = int(case_identifier)
        case_info = case_manager.get_case_by_id(case_id)
    except ValueError:
        case_info = case_manager.get_case_by_name(case_identifier)
    if not case_info:
        await message.reply(f"❌ Кейс '{case_identifier}' не найден.")
        return
    case_id = case_info['id']

    # --- Найти ID карты ---
    card_info = None
    try:
        card_id = int(card_identifier)
        card_info = card_manager.get_card_by_id(card_id)
    except ValueError:
         # Ищем по имени, если не ID
         card_info = db.execute("SELECT id, name FROM cards WHERE name = %s", (card_identifier,), fetch='one')
    if not card_info:
        await message.reply(f"❌ Карта '{card_identifier}' не найдена.")
        return
    # card_info теперь dict или None
    card_id = card_info['id']
    card_name = card_info.get('name', f"ID {card_id}")

    # --- Проверить вес ---
    try:
        weight = int(weight_str)
        if weight <= 0: raise ValueError("Вес должен быть положительным.")
    except ValueError:
        await message.reply("❌ Вес выпадения должен быть положительным целым числом.")
        return

    # --- Добавить карту в кейс ---
    if case_manager.add_card_to_case(case_id, card_id, weight):
        await message.reply(f"✅ Карта '{card_name}' добавлена/обновлена в кейсе '{case_info['name']}' с весом {weight}.")
    else:
        await message.reply(f"❌ Не удалось добавить карту в кейс. Ошибка БД или карта/кейс не найдены.")


@admin_router.message(Command("removecardfromcase"))
async def cmd_remove_card_from_case(message: Message, command: CommandObject):
    args_str = command.args
    usage_text = "⚠️ Использование: `/removecardfromcase <ID или \"Назв. Кейса\"> <ID или \"Назв. Карты\">`"
    if not args_str:
        await message.reply(usage_text)
        return

    try:
        args = shlex.split(args_str)
        if len(args) != 2: raise ValueError("Неверное количество аргументов")
    except ValueError as e:
        logging.warning(f"Failed to parse removecardfromcase args '{args_str}': {e}")
        await message.reply(f"{usage_text}\nОшибка: {e}")
        return

    case_identifier, card_identifier = args

    # --- Найти ID кейса ---
    case_info = None
    try: case_id = int(case_identifier); case_info = case_manager.get_case_by_id(case_id)
    except ValueError: case_info = case_manager.get_case_by_name(case_identifier)
    if not case_info: return await message.reply(f"❌ Кейс '{case_identifier}' не найден.")
    case_id = case_info['id']

    # --- Найти ID карты ---
    card_info = None
    try: card_id = int(card_identifier); card_info = card_manager.get_card_by_id(card_id)
    except ValueError: card_info = db.execute("SELECT id, name FROM cards WHERE name = %s", (card_identifier,), fetch='one')
    if not card_info: return await message.reply(f"❌ Карта '{card_identifier}' не найдена.")
    card_id = card_info['id']
    card_name = card_info.get('name', f"ID {card_id}")

    # --- Удалить карту из кейса ---
    if case_manager.remove_card_from_case(case_id, card_id):
        await message.reply(f"✅ Карта '{card_name}' удалена из кейса '{case_info['name']}'.")
    else:
        # Сообщение об ошибке включает случай, когда карта не была найдена в кейсе
        await message.reply(f"❌ Не удалось удалить карту из кейса (возможно, ее там и не было или ошибка БД).")


@admin_router.message(Command("listcases"))
async def cmd_list_cases(message: Message):
    cases = case_manager.get_all_cases()
    if not cases:
        await message.reply("ℹ️ В базе данных нет созданных кейсов.")
        return

    text_lines = ["📦 <b>Список доступных кейсов:</b>\n"]
    for case_item in cases: # Renamed variable to avoid conflict with module name
        # Получаем количество карт в пуле кейса
        card_count_in_pool = db.execute("SELECT COUNT(*) as count FROM case_cards WHERE case_id = %s", (case_item['id'],), fetch='one')['count']
        text_lines.append(
            f"\n- ID: <code>{case_item['id']}</code>, Имя: <b>{case_item['name']}</b>\n"
            f"  (Выпадает: {case_item['card_count']}, Содержит карт в пуле: {card_count_in_pool}, 🪙: {case_item['price_coins']}, 🀄️: {case_item['price_shards']})"
        )
        if case_item['description']:
             text_lines.append(f"  <i>{case_item['description']}</i>")

    # Возможно, стоит добавить пагинацию, если список кейсов может стать очень большим
    await message.reply("\n".join(text_lines), parse_mode="HTML")


@admin_router.message(Command("viewcase"))
async def cmd_view_case_content(message: Message, command: CommandObject):
    identifier = command.args
    if not identifier:
        await message.reply("⚠️ Укажите ID или Название кейса для просмотра содержимого.")
        return

    case_info = None
    try: case_id = int(identifier); case_info = case_manager.get_case_by_id(case_id)
    except ValueError: case_info = case_manager.get_case_by_name(identifier)

    if not case_info:
        await message.reply(f"❌ Кейс '{identifier}' не найден.")
        return

    case_id = case_info['id']
    cards_in_case = case_manager.get_cards_in_case(case_id) # Already sorted by weight desc

    text_lines = [f"🃏 <b>Содержимое кейса '{case_info['name']}' (ID: {case_id}):</b>\n"]
    if not cards_in_case:
        text_lines.append("  <i>(Пусто)</i>")
    else:
        for card in cards_in_case:
             # Используем первый символ из перевода редкости
             rar_emoji = rarity_translate.get(card['rarity'], "<?>")[0:3].strip()
             text_lines.append(f"- {rar_emoji} {card['name']} (ID: <code>{card['id']}</code>) - Вес: <b>{card['drop_weight']}</b>")

    # Добавить пагинацию, если карт в кейсе много
    await message.reply("\n".join(text_lines), parse_mode="HTML")


# --- Confirmation Handlers ---

@admin_router.callback_query(F.data == "admin_confirm", StateFilter("*"))
async def handle_admin_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    current_state_str = await state.get_state()
    data = await state.get_data()
    user_id = callback.from_user.id
    message = callback.message # Сообщение, к которому привязана кнопка

    logging.info(f"Admin confirmation received by {user_id} for state {current_state_str}")
    await callback.answer("Подтверждено")

    # Пытаемся отредактировать исходное сообщение, чтобы показать обработку
    confirm_in_progress_text = "\n\n✅ Обрабатываю..."
    try:
        if message.photo:
             await message.edit_caption(caption=(message.caption or "") + confirm_in_progress_text, reply_markup=None)
        elif message.text:
             await message.edit_text(message.text + confirm_in_progress_text, reply_markup=None)
    except Exception as e:
        logging.warning(f"Не удалось отредактировать сообщение для подтверждения: {e}")
        pass # Продолжаем выполнение

    # --- Card Creation Confirmation ---
    if current_state_str == CreateCardStates.ConfirmCard.state:
        card_data = data.get('card_data')
        final_caption = f"❌ Ошибка: данные карты не найдены в состоянии."
        if card_data:
            try:
                card_id = card_manager.add_card(
                    name=card_data['name'], rarity=card_data['rarity'],
                    attack=card_data['attack'], health=card_data['health'],
                    value=card_data['value'], image_path=card_data['image_path']
                )
                if card_id:
                    final_caption = f"✅ Карта '{card_data['name']}' (ID: {card_id}) успешно создана!"
                    logging.info(f"Admin {user_id} created card '{card_data['name']}' (ID: {card_id})")
                else:
                    final_caption = f"❌ Не удалось создать карту '{card_data['name']}'. Возможно, имя занято или ошибка БД."
            except Exception as e:
                logging.error(f"Ошибка при создании карты админом {user_id}: {e}", exc_info=True)
                final_caption = f"❌ Ошибка при создании карты: {e}"
        # Обновляем исходное сообщение с результатом
        try: await message.edit_caption(caption=final_caption, reply_markup=None)
        except Exception: pass # Игнорируем ошибки редактирования, если сообщение удалено и т.п.
        await state.clear()

    # --- Promo Creation Confirmation ---
    elif current_state_str == CreatePromoStates.ConfirmPromo.state:
        promo_data = data.get('promo_data')
        final_text = "❌ Ошибка: данные промокода не найдены в состоянии."
        if promo_data:
            code = promo_manager.generate_promo_code(
                custom_code=promo_data.get('code'),
                reward_amount=promo_data['reward'],
                uses=promo_data['uses']
            )
            if code:
                final_text = f"✅ Промокод <code>{code}</code> на {promo_data['reward']} 🪙 ({promo_data['uses']} исп.) создан!"
                logging.info(f"Admin {user_id} created promo code '{code}'")
            else:
                final_text = "❌ Не удалось создать промокод. Возможно, код занят или ошибка БД."
        try: await message.edit_text(final_text, parse_mode="HTML", reply_markup=None)
        except Exception: pass
        await state.clear()

    # --- Broadcast Confirmation ---
    elif current_state_str == BroadcastState.ConfirmBroadcast.state:
        broadcast_message_html = data.get('broadcast_message')
        final_text = "❌ Ошибка: текст для рассылки не найден."
        if broadcast_message_html:
            await message.edit_text("⏳ Начинаю рассылку...", reply_markup=None) # Обновляем статус
            user_ids = user_manager.get_all_user_ids(include_banned=False)
            sent_count = 0
            failed_count = 0
            total_users = len(user_ids)
            status_message_id = message.message_id
            chat_id = message.chat.id

            logging.info(f"Admin {user_id} starting broadcast to {total_users} users.")
            start_time = asyncio.get_event_loop().time()
            last_update_time = start_time

            for i, target_user_id in enumerate(user_ids):
                try:
                    # Используем copy_message для поддержки форматирования и медиа в будущем
                    # await bot.copy_message(chat_id=target_user_id, from_chat_id=chat_id, message_id=?) # Сложно, если текст введен вручную
                    # Пока используем send_message с HTML
                    await bot.send_message(target_user_id, broadcast_message_html, parse_mode="HTML", disable_web_page_preview=True)
                    sent_count += 1
                    logging.debug(f"Broadcast sent to {target_user_id}")
                except TelegramAPIError as e:
                    # Обработка конкретных ошибок (бот заблокирован, чат не найден и т.д.)
                    logging.warning(f"Failed broadcast to {target_user_id}: {e.method} - {e.message}")
                    failed_count += 1
                    # Можно добавить логику для удаления/деактивации пользователя при определенных ошибках
                    # if e.message == "Forbidden: bot was blocked by the user": ...
                except Exception as e:
                    # Другие неожиданные ошибки
                    logging.error(f"Unexpected error broadcasting to {target_user_id}: {e}", exc_info=True)
                    failed_count += 1

                # Небольшая пауза для избежания флуд-лимитов
                await asyncio.sleep(0.1)

                # Обновляем статусное сообщение периодически
                current_time = asyncio.get_event_loop().time()
                if current_time - last_update_time > 5 or (i + 1) % 100 == 0 or i == total_users - 1:
                     progress_text = f"⏳ Рассылка... ({i+1}/{total_users})\nУспешно: {sent_count}, Ошибок: {failed_count}"
                     try:
                         # Редактируем сообщение админа
                         await bot.edit_message_text(progress_text, chat_id=chat_id, message_id=status_message_id)
                         last_update_time = current_time
                     except TelegramBadRequest: pass # Игнорируем, если сообщение не изменилось
                     except Exception as edit_e:
                         logging.warning(f"Could not edit broadcast status message: {edit_e}")

            end_time = asyncio.get_event_loop().time()
            duration = end_time - start_time
            final_text = (
                f"✅ Рассылка завершена за {duration:.2f} сек!\n"
                f"Успешно: {sent_count}, Ошибок: {failed_count}, Всего: {total_users}"
            )
            logging.info(f"Broadcast finished. Sent: {sent_count}, Failed: {failed_count}. Duration: {duration:.2f}s")

        try:
            await bot.edit_message_text(final_text, chat_id=chat_id, message_id=status_message_id)
        except Exception as final_edit_e:
             logging.warning(f"Could not edit final broadcast status: {final_edit_e}")
             await message.answer(final_text) # Отправляем новым сообщением, если редактирование не удалось
        await state.clear()

    # --- Case Creation Confirmation ---
    elif current_state_str == CreateCaseStates.ConfirmCase.state:
        case_data = data.get('case_data')
        final_text = "❌ Ошибка: данные кейса не найдены в состоянии."
        if case_data:
            try:
                case_id = case_manager.create_case(
                    name=case_data['name'], description=case_data['description'],
                    card_count=case_data['card_count'], price_coins=case_data['price_coins'],
                    price_shards=case_data['price_shards']
                )
                if case_id:
                    final_text = f"✅ Кейс '{case_data['name']}' (ID: {case_id}) успешно создан!"
                    logging.info(f"Admin {user_id} created case '{case_data['name']}' (ID: {case_id})")
                else:
                    final_text = f"❌ Не удалось создать кейс '{case_data['name']}'. Возможно, имя занято или ошибка БД."
            except Exception as e:
                logging.error(f"Ошибка при создании кейса админом {user_id}: {e}", exc_info=True)
                final_text = f"❌ Ошибка при создании кейса: {e}"
        try: await message.edit_text(final_text, reply_markup=None)
        except Exception: pass
        await state.clear()

    else:
        logging.warning(f"Получен callback admin_confirm в неожиданном состоянии: {current_state_str}")
        try: await message.edit_text("Неизвестное действие для подтверждения.")
        except Exception: pass
        await state.clear()


@admin_router.callback_query(F.data == "admin_cancel", StateFilter("*"))
async def handle_admin_cancel(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    logging.info(f"Admin action cancelled by {callback.from_user.id} in state {current_state}")
    await state.clear()
    await callback.answer("Отменено")
    try:
        # Редактируем или удаляем исходное сообщение
        if callback.message.photo:
             # Удаляем сообщение с фото, т.к. оно больше не нужно
             await callback.message.delete()
        elif callback.message.text:
             # Редактируем текстовое сообщение
             await callback.message.edit_text("Действие отменено.", reply_markup=None)
    except Exception as e:
        logging.info(f"Не удалось удалить/отредактировать сообщение при отмене админом: {e}")
        # Можно отправить новое сообщение как fallback, если редактирование/удаление важно
        # await callback.message.answer("Действие отменено.")