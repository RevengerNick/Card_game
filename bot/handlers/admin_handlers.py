import asyncio
import logging
from typing import Optional, List, Dict, Any
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputMediaPhoto, InputFile
# Import StateFilter and Command filters correctly
from aiogram.filters import Command, CommandObject, Filter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

# Import necessary managers and database instance
from bot.Classes.db_manager import user_manager, card_manager, promo_manager, case_manager, db
from bot.card_database import RARITY_CHOICES, rarity_translate, SUPER_ADMIN_ID

admin_router = Router()

# --- Admin Check Filter/Decorator ---

class IsAdminFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        # Check if the user is in the admins table
        return user_manager.is_admin(message.from_user.id)

class IsSuperAdminFilter(Filter):
     async def __call__(self, message: Message) -> bool:
         # Check if the user ID matches the SUPER_ADMIN_ID from config
         return message.from_user.id == SUPER_ADMIN_ID

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

class CreateCaseStates(StatesGroup): # Case States
    WaitingForName = State()
    WaitingForDescription = State()
    WaitingForCardCount = State()
    WaitingForPriceCoins = State()
    WaitingForPriceShards = State()
    ConfirmCase = State()

# --- Helper Functions ---

def get_rarity_keyboard() -> ReplyKeyboardMarkup:
    buttons = [KeyboardButton(text=r.capitalize()) for r in RARITY_CHOICES]
    # Arrange buttons, e.g., 2 per row
    keyboard = []
    for i in range(0, len(buttons), 2):
        keyboard.append(buttons[i:i + 2])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="admin_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")
        ]
    ])

async def parse_user_id(message: Message, command_args: Optional[str]) -> Optional[int]:
    """Helper to parse user ID from command arguments or reply."""
    if command_args:
        try:
            return int(command_args.strip())
        except ValueError:
            await message.reply("⚠️ Неверный формат ID пользователя.")
            return None
    elif message.reply_to_message:
        return message.reply_to_message.from_user.id
    else:
        await message.reply("⚠️ Укажите ID пользователя или ответьте на его сообщение.")
        return None

# --- Admin Management Commands ---

@admin_router.message(Command("addadmin"), IsSuperAdminFilter())
async def cmd_add_admin(message: Message, command: CommandObject):
    target_user_id = await parse_user_id(message, command.args)
    if target_user_id is None:
        return

    if user_manager.is_admin(target_user_id):
        await message.reply(f"✅ Пользователь {target_user_id} уже является администратором.")
        return

    # Ensure user exists in the main users table before adding to admins
    if not user_manager.get_user_raw(target_user_id):
         # Maybe register them first? Or just deny. Let's deny for now.
         await message.reply(f"❌ Пользователь {target_user_id} не найден в базе. Попросите его сначала запустить /start.")
         return

    if user_manager.add_admin(target_user_id):
        await message.reply(f"✅ Пользователь {target_user_id} успешно назначен администратором.")
        try:
            await message.bot.send_message(target_user_id, "🎉 Поздравляем! Вы были назначены администратором.")
        except Exception as e:
            logging.warning(f"Не удалось уведомить нового админа {target_user_id}: {e}")
    else:
        await message.reply(f"❌ Не удалось назначить администратора {target_user_id}. Произошла ошибка БД.")

@admin_router.message(Command("deladmin"), IsSuperAdminFilter())
async def cmd_del_admin(message: Message, command: CommandObject):
    target_user_id = await parse_user_id(message, command.args)
    if target_user_id is None:
        return

    if target_user_id == message.from_user.id:
        await message.reply("❌ Вы не можете удалить себя из администраторов.")
        return

    if not user_manager.is_admin(target_user_id):
        await message.reply(f"ℹ️ Пользователь {target_user_id} не является администратором.")
        return

    if user_manager.remove_admin(target_user_id):
        await message.reply(f"✅ Пользователь {target_user_id} успешно удален из администраторов.")
        try:
            await message.bot.send_message(target_user_id, "ℹ️ Вы были удалены из списка администраторов.")
        except Exception as e:
            logging.warning(f"Не удалось уведомить удаленного админа {target_user_id}: {e}")
    else:
        await message.reply(f"❌ Не удалось удалить администратора {target_user_id}. Произошла ошибка БД.")

@admin_router.message(Command("admins"), IsAdminFilter())
async def cmd_list_admins(message: Message):
    admin_ids = db.execute("SELECT user_id FROM admins ORDER BY added_at", fetch='all')
    if not admin_ids:
        await message.reply("ℹ️ Список администраторов пуст.")
        return

    admin_list = ["👑 Список администраторов:"]
    for i, admin in enumerate(admin_ids, 1):
        # Fetch raw user data to get username, even if banned etc.
        user_info = user_manager.get_user_raw(admin['user_id'])
        username = user_info['username'] if user_info and user_info['username'] else "Неизвестно"
        user_id_str = f"`{admin['user_id']}`" # Use backticks for Markdown code block
        admin_list.append(f"{i}. ID: {user_id_str} ( @{username} )")

    await message.reply("\n".join(admin_list), parse_mode="Markdown")


# --- Card Creation Command ---

@admin_router.message(Command("createcard"), IsAdminFilter())
async def cmd_create_card_start(message: Message, state: FSMContext):
    await message.reply("🖼️ Пожалуйста, отправьте фотографию для новой карты.", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CreateCardStates.WaitingForPhoto)
    await state.update_data(card_data={}) # Initialize empty dict

@admin_router.message(CreateCardStates.WaitingForPhoto, F.photo)
async def process_card_photo(message: Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    data = await state.get_data()
    card_data = data.get('card_data', {})
    card_data['image_path'] = photo_file_id
    await state.update_data(card_data=card_data)

    await message.reply("🏷️ Теперь введите **название** карты:")
    await state.set_state(CreateCardStates.WaitingForName)

@admin_router.message(CreateCardStates.WaitingForPhoto, ~F.photo)
async def process_card_photo_invalid(message: Message, state: FSMContext):
     await message.reply("❌ Пожалуйста, отправьте именно фотографию.")

@admin_router.message(CreateCardStates.WaitingForName, F.text)
async def process_card_name(message: Message, state: FSMContext):
    card_name = message.text.strip()
    if not card_name:
        await message.reply("❌ Название карты не может быть пустым.")
        return # Stay in the same state
    # Check if card name already exists
    existing_card = db.execute("SELECT id FROM cards WHERE name = %s", (card_name,), fetch='one')
    if existing_card:
        await message.reply(f"❌ Карта с названием '{card_name}' уже существует. Введите другое название.")
        return # Stay in the same state

    data = await state.get_data()
    card_data = data.get('card_data', {})
    card_data['name'] = card_name
    await state.update_data(card_data=card_data)

    await message.reply("✨ Выберите **редкость** карты:", reply_markup=get_rarity_keyboard())
    await state.set_state(CreateCardStates.WaitingForRarity)

@admin_router.message(CreateCardStates.WaitingForRarity, F.text)
async def process_card_rarity(message: Message, state: FSMContext):
    rarity = message.text.strip().lower()
    if rarity not in RARITY_CHOICES:
        # Check if capitalized version matches
        rarity_capitalized = message.text.strip().capitalize()
        found = False
        for r_choice in RARITY_CHOICES:
            if r_choice.capitalize() == rarity_capitalized:
                rarity = r_choice
                found = True
                break
        if not found:
            await message.reply("❌ Неверная редкость. Пожалуйста, выберите из предложенных кнопок.", reply_markup=get_rarity_keyboard())
            return

    data = await state.get_data()
    card_data = data.get('card_data', {})
    card_data['rarity'] = rarity
    await state.update_data(card_data=card_data)

    await message.reply("🔪 Введите **атаку** карты (число):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CreateCardStates.WaitingForAttack)

@admin_router.message(CreateCardStates.WaitingForAttack, F.text)
async def process_card_attack(message: Message, state: FSMContext):
    try:
        attack = int(message.text.strip())
        if attack < 0: raise ValueError("Attack cannot be negative")

        data = await state.get_data()
        card_data = data.get('card_data', {})
        card_data['attack'] = attack
        await state.update_data(card_data=card_data)

        await message.reply("❤️ Введите **здоровье** карты (число > 0):")
        await state.set_state(CreateCardStates.WaitingForHealth)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое неотрицательное число для атаки.")

@admin_router.message(CreateCardStates.WaitingForHealth, F.text)
async def process_card_health(message: Message, state: FSMContext):
    try:
        health = int(message.text.strip())
        if health <= 0: raise ValueError("Health must be positive")

        data = await state.get_data()
        card_data = data.get('card_data', {})
        card_data['health'] = health
        await state.update_data(card_data=card_data)

        await message.reply("💠 Введите **ценность** карты (число >= 0):")
        await state.set_state(CreateCardStates.WaitingForValue)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое положительное число для здоровья.")

@admin_router.message(CreateCardStates.WaitingForValue, F.text)
async def process_card_value(message: Message, state: FSMContext):
    try:
        value = int(message.text.strip())
        if value < 0: raise ValueError("Value cannot be negative")

        data = await state.get_data()
        card_data = data.get('card_data', {})
        card_data['value'] = value
        await state.update_data(card_data=card_data)

        # --- Confirmation Step ---
        # Ensure rarity exists before formatting
        rarity_display = rarity_translate.get(card_data['rarity'], card_data['rarity'].capitalize())

        confirm_text = (
            f"**Проверьте данные карты:**\n\n"
            f"🏷️ Название: {card_data['name']}\n"
            f"✨ Редкость: {rarity_display}\n"
            f"🔪 Атака: {card_data['attack']}\n"
            f"❤️ Здоровье: {card_data['health']}\n"
            f"💠 Ценность: {card_data['value']}\n\n"
            f"Создаем карту?"
        )
        # Send photo with caption for confirmation
        try:
            await message.answer_photo(
                photo=card_data['image_path'],
                caption=confirm_text,
                reply_markup=get_confirmation_keyboard(),
                parse_mode="Markdown"
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

# --- Statistics Commands ---

@admin_router.message(Command("stats"), IsAdminFilter())
async def cmd_stats(message: Message):
    user_count = user_manager.get_total_user_count()
    # Assuming total cards given = sum of total_cards_received from users table
    cards_given = user_manager.get_total_cards_given_out()
    pass_count = user_manager.get_battle_pass_count()
    total_coins = user_manager.get_total_coins_in_system()

    stats_text = (
        f"📊 **Статистика Бота:**\n\n"
        f"👤 Всего пользователей: {user_count}\n"
        f"🃏 Всего выдано карт (круток): {cards_given}\n"
        f"🎫 Активных Battle Pass: {pass_count}\n"
        f"🪙 Всего PoTi Coin в системе: {total_coins}"
    )
    await message.reply(stats_text, parse_mode="Markdown")

# --- Promo Code Creation Command ---

@admin_router.message(Command("createpromo"), IsAdminFilter())
async def cmd_create_promo_start(message: Message, state: FSMContext):
    await message.reply("📝 Введите **код** для промокода (буквы/цифры, 4-20 симв., или 'auto' для генерации):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CreatePromoStates.WaitingForCode)
    await state.update_data(promo_data={})

@admin_router.message(CreatePromoStates.WaitingForCode, F.text)
async def process_promo_code(message: Message, state: FSMContext):
    code = message.text.strip()
    promo_data = (await state.get_data()).get('promo_data', {})

    if code.lower() == 'auto':
        promo_data['code'] = None # Let manager generate
    else:
        # Basic validation (e.g., length, characters - adjust as needed)
        if not (4 <= len(code) <= 20 and code.isalnum()):
            await message.reply("❌ Код должен быть от 4 до 20 символов и состоять только из букв и цифр.")
            return
        # Check if code already exists
        if promo_manager.db.execute("SELECT 1 FROM promo_achievements WHERE code = %s", (code,), fetch='one'):
            await message.reply(f"❌ Промокод '{code}' уже существует. Введите другой или 'auto'.")
            return
        promo_data['code'] = code

    await state.update_data(promo_data=promo_data)
    await message.reply("💰 Введите **сумму награды** (в PoTi Coin, число > 0):")
    await state.set_state(CreatePromoStates.WaitingForReward)

@admin_router.message(CreatePromoStates.WaitingForReward, F.text)
async def process_promo_reward(message: Message, state: FSMContext):
    try:
        reward = int(message.text.strip())
        if reward <= 0: raise ValueError("Reward must be positive")

        promo_data = (await state.get_data()).get('promo_data', {})
        promo_data['reward'] = reward
        await state.update_data(promo_data=promo_data)

        await message.reply("🔄 Введите **количество использований** (число > 0):")
        await state.set_state(CreatePromoStates.WaitingForUses)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое положительное число для награды.")

@admin_router.message(CreatePromoStates.WaitingForUses, F.text)
async def process_promo_uses(message: Message, state: FSMContext):
    try:
        uses = int(message.text.strip())
        if uses <= 0: raise ValueError("Uses must be positive")

        promo_data = (await state.get_data()).get('promo_data', {})
        promo_data['uses'] = uses
        await state.update_data(promo_data=promo_data)

        # --- Confirmation ---
        code_display = promo_data.get('code') or "(авто)"
        confirm_text = (
            f"**Проверьте данные промокода:**\n\n"
            f"📝 Код: `{code_display}`\n"
            f"💰 Награда: {promo_data['reward']} 🪙\n"
            f"🔄 Использований: {promo_data['uses']}\n\n"
            f"Создаем промокод?"
        )
        await message.reply(confirm_text, reply_markup=get_confirmation_keyboard(), parse_mode="Markdown")
        await state.set_state(CreatePromoStates.ConfirmPromo)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое положительное число для использований.")


# --- Broadcast Command ---

@admin_router.message(Command("broadcast"), IsAdminFilter())
async def cmd_broadcast_start(message: Message, state: FSMContext):
    await message.reply("📢 Введите сообщение для рассылки всем НЕ забаненным пользователям (поддерживает HTML-разметку):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(BroadcastState.WaitingForMessage)

@admin_router.message(BroadcastState.WaitingForMessage, F.text)
async def process_broadcast_message(message: Message, state: FSMContext):
    # Basic check for empty message
    if not message.text or message.text.isspace():
        await message.reply("❌ Сообщение для рассылки не может быть пустым.")
        return

    broadcast_text = message.html_text # Use html_text to preserve formatting
    await state.update_data(broadcast_message=broadcast_text)

    # Preview the message to the admin
    preview_text = f"**Предпросмотр сообщения:**\n\n{broadcast_text}\n\n--------\n\nОтправляем?"

    await message.reply(preview_text, reply_markup=get_confirmation_keyboard(), parse_mode="Markdown")
    await state.set_state(BroadcastState.ConfirmBroadcast)


# --- User Management Commands ---

@admin_router.message(Command("ban"), IsAdminFilter())
async def cmd_ban_user(message: Message, command: CommandObject):
    target_user_id = await parse_user_id(message, command.args)
    if target_user_id is None: return

    if target_user_id == message.from_user.id:
        await message.reply("❌ Нельзя забанить самого себя.")
        return
    # Allow super admin to ban regular admins, but not other super admins (if any)
    is_target_admin = user_manager.is_admin(target_user_id)
    is_caller_super = message.from_user.id == SUPER_ADMIN_ID

    if is_target_admin and not is_caller_super:
         await message.reply("❌ Вы не можете забанить другого администратора (только Супер Админ).")
         return
    if target_user_id == SUPER_ADMIN_ID and message.from_user.id != SUPER_ADMIN_ID: # Prevent banning the super admin
         await message.reply("❌ Нельзя забанить Супер Администратора.")
         return


    user_data = user_manager.get_user_raw(target_user_id)
    if not user_data:
        await message.reply(f"❌ Пользователь {target_user_id} не найден.")
        return
    if user_data['is_banned']:
        await message.reply(f"ℹ️ Пользователь {target_user_id} уже забанен.")
        return

    if user_manager.ban_user(target_user_id):
        # If banning an admin, remove them from admin table as well
        if is_target_admin:
            user_manager.remove_admin(target_user_id)
            await message.reply(f"✅ Пользователь {target_user_id} успешно забанен и удален из администраторов.")
        else:
            await message.reply(f"✅ Пользователь {target_user_id} успешно забанен.")
        try:
            await message.bot.send_message(target_user_id, "🚫 Ваш аккаунт был заблокирован администратором.")
        except Exception as e:
            logging.info(f"Не удалось уведомить забаненного пользователя {target_user_id}: {e}")
    else:
        await message.reply(f"❌ Не удалось забанить пользователя {target_user_id}. Ошибка БД.")

@admin_router.message(Command("unban"), IsAdminFilter())
async def cmd_unban_user(message: Message, command: CommandObject):
    target_user_id = await parse_user_id(message, command.args)
    if target_user_id is None: return

    user_data = user_manager.get_user_raw(target_user_id) # Need raw data to check ban status
    if not user_data:
        await message.reply(f"❌ Пользователь {target_user_id} не найден.")
        return
    if not user_data['is_banned']:
        await message.reply(f"ℹ️ Пользователь {target_user_id} не забанен.")
        return

    if user_manager.unban_user(target_user_id):
        await message.reply(f"✅ Пользователь {target_user_id} успешно разбанен.")
        try:
            await message.bot.send_message(target_user_id, "🎉 Ваш аккаунт был разблокирован администратором.")
        except Exception as e:
            logging.info(f"Не удалось уведомить разбаненного пользователя {target_user_id}: {e}")
    else:
        await message.reply(f"❌ Не удалось разбанить пользователя {target_user_id}. Ошибка БД.")

@admin_router.message(Command("resetuser"), IsAdminFilter())
async def cmd_reset_user(message: Message, command: CommandObject):
    args = (command.args or "").split()
    target_user_id_str = args[0] if args else None
    confirmation = args[1] if len(args) > 1 else None

    # Allow using reply_to_message if no ID is provided
    if target_user_id_str:
         target_user_id = await parse_user_id(message, target_user_id_str)
    elif message.reply_to_message:
         target_user_id = message.reply_to_message.from_user.id
    else:
        await message.reply("⚠️ Укажите ID пользователя или ответьте на его сообщение.")
        return

    if target_user_id is None: return # parse_user_id already sent a message

    if target_user_id == message.from_user.id:
        await message.reply("❌ Нельзя сбросить свой аккаунт.")
        return

    # Check admin status (Super Admin can reset regular admins)
    is_target_admin = user_manager.is_admin(target_user_id)
    is_caller_super = message.from_user.id == SUPER_ADMIN_ID
    if is_target_admin and not is_caller_super:
        await message.reply("❌ Нельзя сбросить аккаунт другого администратора (только Супер Админ).")
        return
    if target_user_id == SUPER_ADMIN_ID and message.from_user.id != SUPER_ADMIN_ID:
        await message.reply("❌ Нельзя сбросить аккаунт Супер Администратора.")
        return


    # Check if user exists
    if not user_manager.get_user_raw(target_user_id):
        await message.reply(f"❌ Пользователь {target_user_id} не найден.")
        return

    if confirmation != "CONFIRM":
        await message.reply(
            f"⚠️ **ПРЕДУПРЕЖДЕНИЕ!** Это действие полностью удалит все карты, колоды, прогресс заданий, промокоды, валюту и статистику пользователя `{target_user_id}`.\n\n"
            f"Для подтверждения выполните команду еще раз, добавив `CONFIRM` в конце:\n`/resetuser {target_user_id} CONFIRM`",
            parse_mode="Markdown"
        )
        return

    # --- Perform Reset ---
    await message.reply(f"⏳ Выполняется сброс аккаунта {target_user_id}...")
    if user_manager.reset_user_account(target_user_id):
        # If target was an admin, also remove from admin table
        if is_target_admin:
             user_manager.remove_admin(target_user_id)
             await message.reply(f"✅ Аккаунт пользователя {target_user_id} успешно сброшен (и удален из админов).")
        else:
             await message.reply(f"✅ Аккаунт пользователя {target_user_id} успешно сброшен.")

        try:
            await message.bot.send_message(target_user_id, "ℹ️ Ваш аккаунт был сброшен администратором.")
        except Exception as e:
            logging.info(f"Не удалось уведомить пользователя о сбросе {target_user_id}: {e}")
    else:
        await message.reply(f"❌ Не удалось сбросить аккаунт пользователя {target_user_id}. Ошибка БД.")

# --- Case/Pack Management Commands ---

@admin_router.message(Command("createcase"), IsAdminFilter())
async def cmd_create_case_start(message: Message, state: FSMContext):
    await message.reply("📦 Введите **название** нового кейса:", reply_markup=ReplyKeyboardRemove())
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
    await message.reply("📝 Введите **описание** кейса (или '-' если нет):")
    await state.set_state(CreateCaseStates.WaitingForDescription)

@admin_router.message(CreateCaseStates.WaitingForDescription, F.text)
async def process_case_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    data = await state.get_data()
    case_data = data.get('case_data', {})
    case_data['description'] = None if desc == '-' else desc
    await state.update_data(case_data=case_data)
    await message.reply("🔢 Введите **количество карт**, выпадающих из кейса (число > 0):")
    await state.set_state(CreateCaseStates.WaitingForCardCount)

@admin_router.message(CreateCaseStates.WaitingForCardCount, F.text)
async def process_case_card_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        if count <= 0: raise ValueError("Count must be positive")
        data = await state.get_data()
        case_data = data.get('case_data', {})
        case_data['card_count'] = count
        await state.update_data(case_data=case_data)
        await message.reply("💰 Введите **цену в PoTi Coin** (число >= 0, 0 если бесплатно):")
        await state.set_state(CreateCaseStates.WaitingForPriceCoins)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое положительное число.")

@admin_router.message(CreateCaseStates.WaitingForPriceCoins, F.text)
async def process_case_price_coins(message: Message, state: FSMContext):
    try:
        price = int(message.text.strip())
        if price < 0: raise ValueError("Price cannot be negative")
        data = await state.get_data()
        case_data = data.get('case_data', {})
        case_data['price_coins'] = price
        await state.update_data(case_data=case_data)
        await message.reply("🧊 Введите **цену в Осколках** (число >= 0, 0 если бесплатно):")
        await state.set_state(CreateCaseStates.WaitingForPriceShards)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое неотрицательное число.")

@admin_router.message(CreateCaseStates.WaitingForPriceShards, F.text)
async def process_case_price_shards(message: Message, state: FSMContext):
    try:
        price = int(message.text.strip())
        if price < 0: raise ValueError("Price cannot be negative")
        data = await state.get_data()
        case_data = data.get('case_data', {})
        case_data['price_shards'] = price

        # Ensure at least one price is set if case is not intended to be free? Optional check.
        # if case_data['price_coins'] == 0 and case_data['price_shards'] == 0:
        #     # Ask for confirmation if it should be free?
        #     pass

        await state.update_data(case_data=case_data)

        # --- Confirmation ---
        confirm_text = (
            f"**Проверьте данные кейса:**\n\n"
            f"📦 Название: {case_data['name']}\n"
            f"📝 Описание: {case_data['description'] or 'Нет'}\n"
            f"🔢 Карт в кейсе: {case_data['card_count']}\n"
            f"💰 Цена (монеты): {case_data['price_coins']} 🪙\n"
            f"🧊 Цена (осколки): {case_data['price_shards']} 🀄️\n\n"
            f"Создаем кейс?"
        )
        await message.reply(confirm_text, reply_markup=get_confirmation_keyboard(), parse_mode="Markdown")
        await state.set_state(CreateCaseStates.ConfirmCase)
    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое неотрицательное число.")


@admin_router.message(Command("deletecase"), IsAdminFilter())
async def cmd_delete_case(message: Message, command: CommandObject):
    args_str = command.args
    if not args_str:
        await message.reply("⚠️ Укажите ID или Название кейса для удаления.")
        return

    parts = args_str.split(maxsplit=1)
    identifier = parts[0]
    confirmation = parts[1] if len(parts) > 1 else None

    case_info = None
    try:
        case_id = int(identifier)
        case_info = case_manager.get_case_by_id(case_id)
    except ValueError:
        # Allow searching by name (case-sensitive for now)
        case_info = case_manager.get_case_by_name(identifier)

    if not case_info:
        await message.reply(f"❌ Кейс '{identifier}' не найден.")
        return

    case_id_to_delete = case_info['id']
    case_name_to_delete = case_info['name']

    if confirmation != "CONFIRM":
        await message.reply(
            f"⚠️ **ПРЕДУПРЕЖДЕНИЕ!** Это действие безвозвратно удалит кейс '{case_name_to_delete}' (ID: {case_id_to_delete}) и все связи карт с ним.\n\n"
            f"Для подтверждения выполните команду еще раз, добавив `CONFIRM` в конце:\n`/deletecase \"{identifier}\" CONFIRM`", # Use quotes if name has spaces
            parse_mode="Markdown"
        )
        return

    if case_manager.delete_case(case_id_to_delete):
        await message.reply(f"✅ Кейс '{case_name_to_delete}' (ID: {case_id_to_delete}) успешно удален.")
    else:
        await message.reply(f"❌ Не удалось удалить кейс '{case_name_to_delete}'. Ошибка БД.")


@admin_router.message(Command("addcardtocase"), IsAdminFilter())
async def cmd_add_card_to_case(message: Message, command: CommandObject):
    args_str = command.args
    if not args_str:
        await message.reply("⚠️ Использование: `/addcardtocase <ID или \"Название Кейса\"> <ID или \"Название Карты\"> <Вес выпадения>`")
        return
    # Improved parsing for quoted names
    import shlex
    try:
        args = shlex.split(args_str)
        if len(args) != 3: raise ValueError("Incorrect number of arguments")
    except ValueError as e:
        logging.warning(f"Failed to parse addcardtocase args '{args_str}': {e}")
        await message.reply("⚠️ Ошибка парсинга аргументов. Используйте кавычки для названий с пробелами.\nПример: `/addcardtocase \"Epic Pack\" \"Dragon Lord\" 10`")
        return

    case_identifier, card_identifier, weight_str = args

    # Find Case ID
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

    # Find Card ID
    card_info = None
    try:
        card_id = int(card_identifier)
        card_info = card_manager.get_card_by_id(card_id)
    except ValueError:
         # Assume get_card_by_id handles dict conversion or returns None
         card_info = db.execute("SELECT * FROM cards WHERE name = %s", (card_identifier,), fetch='one')

    if not card_info:
        await message.reply(f"❌ Карта '{card_identifier}' не найдена.")
        return
    card_id = card_info['id'] # Get ID from the fetched dict

    # Validate Weight
    try:
        weight = int(weight_str)
        if weight <= 0: raise ValueError("Weight must be positive")
    except ValueError:
        await message.reply("❌ Вес выпадения должен быть положительным целым числом.")
        return

    # Add card to case
    if case_manager.add_card_to_case(case_id, card_id, weight):
        await message.reply(f"✅ Карта '{card_info['name']}' добавлена/обновлена в кейсе '{case_info['name']}' с весом {weight}.")
    else:
        await message.reply(f"❌ Не удалось добавить карту в кейс. Ошибка БД или карта/кейс не найдены.")


@admin_router.message(Command("removecardfromcase"), IsAdminFilter())
async def cmd_remove_card_from_case(message: Message, command: CommandObject):
    args_str = command.args
    if not args_str:
        await message.reply("⚠️ Использование: `/removecardfromcase <ID или \"Название Кейса\"> <ID или \"Название Карты\">`")
        return
    # Improved parsing
    import shlex
    try:
        args = shlex.split(args_str)
        if len(args) != 2: raise ValueError("Incorrect number of arguments")
    except ValueError as e:
        logging.warning(f"Failed to parse removecardfromcase args '{args_str}': {e}")
        await message.reply("⚠️ Ошибка парсинга аргументов. Используйте кавычки для названий с пробелами.")
        return

    case_identifier, card_identifier = args

    # Find Case ID (similar logic as addcardtocase)
    case_info = None
    try: case_id = int(case_identifier); case_info = case_manager.get_case_by_id(case_id)
    except ValueError: case_info = case_manager.get_case_by_name(case_identifier)
    if not case_info: return await message.reply(f"❌ Кейс '{case_identifier}' не найден.")
    case_id = case_info['id']

    # Find Card ID (similar logic as addcardtocase)
    card_info = None
    try: card_id = int(card_identifier); card_info = card_manager.get_card_by_id(card_id)
    except ValueError: card_info = db.execute("SELECT * FROM cards WHERE name = %s", (card_identifier,), fetch='one')
    if not card_info: return await message.reply(f"❌ Карта '{card_identifier}' не найдена.")
    card_id = card_info['id']

    # Remove card from case
    if case_manager.remove_card_from_case(case_id, card_id):
        await message.reply(f"✅ Карта '{card_info['name']}' удалена из кейса '{case_info['name']}'.")
    else:
        await message.reply(f"❌ Не удалось удалить карту из кейса (возможно, ее там и не было или ошибка БД).")


@admin_router.message(Command("listcases"), IsAdminFilter())
async def cmd_list_cases(message: Message):
    cases = case_manager.get_all_cases()
    if not cases:
        await message.reply("ℹ️ В базе данных нет созданных кейсов.")
        return

    text_lines = ["📦 **Список доступных кейсов:**\n"]
    for case in cases:
        # Fetch card count in case for display
        card_count_in_case = db.execute("SELECT COUNT(*) as count FROM case_cards WHERE case_id = %s", (case['id'],), fetch='one')['count']
        text_lines.append(
            f"- ID: `{case['id']}`, Имя: **{case['name']}**\n"
            f"  (Выпадает: {case['card_count']}, Содержит: {card_count_in_case}, 🪙: {case['price_coins']}, 🀄️: {case['price_shards']})"
        )
    await message.reply("\n".join(text_lines), parse_mode="Markdown")


@admin_router.message(Command("viewcase"), IsAdminFilter())
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
    cards_in_case = case_manager.get_cards_in_case(case_id)

    text_lines = [f"🃏 **Содержимое кейса '{case_info['name']}' (ID: {case_id}):**\n"]
    if not cards_in_case:
        text_lines.append("  _(Пусто)_")
    else:
        # Sort cards for consistent display, e.g., by rarity then name
        cards_in_case.sort(key=lambda c: (RARITY_CHOICES.index(c['rarity']) if c['rarity'] in RARITY_CHOICES else 99, c['name']))
        for card in cards_in_case:
             rar_emoji = rarity_translate.get(card['rarity'], "<?>")[0:3] # Get emoji
             text_lines.append(f"- {rar_emoji} {card['name']} (ID: `{card['id']}`) - Вес: **{card['drop_weight']}**")

    await message.reply("\n".join(text_lines), parse_mode="Markdown")


# --- Confirmation Handlers ---
# Use StateFilter("*") for aiogram 3.x
@admin_router.callback_query(F.data == "admin_confirm", StateFilter("*"))
async def handle_admin_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    current_state_str = await state.get_state()
    data = await state.get_data()
    await callback.answer("Подтверждено")
    # It's often better to edit the original message than the reply markup
    # Try editing the message text/caption to indicate confirmation succeeded before long actions
    try:
        if callback.message.photo:
             await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ Обрабатываю...", reply_markup=None)
        else:
             await callback.message.edit_text(callback.message.text + "\n\n✅ Обрабатываю...", reply_markup=None)
    except Exception: # Ignore if editing fails
        pass


    # --- Card Creation Confirmation ---
    if current_state_str == CreateCardStates.ConfirmCard.state:
        card_data = data.get('card_data')
        if not card_data: await callback.message.edit_text("❌ Ошибка: данные карты не найдены."); await state.clear(); return
        final_caption = f"❌ Не удалось создать карту '{card_data['name']}'." # Default error message
        try:
            card_id = card_manager.add_card(name=card_data['name'], rarity=card_data['rarity'], attack=card_data['attack'], health=card_data['health'], value=card_data['value'], image_path=card_data['image_path'])
            if card_id: final_caption = f"✅ Карта '{card_data['name']}' (ID: {card_id}) успешно создана!"
            else: final_caption = f"❌ Не удалось создать карту '{card_data['name']}'. Имя занято?"
        except Exception as e: logging.error(f"Error creating card: {e}"); final_caption = f"❌ Ошибка при создании: {e}"
        finally:
            try: await callback.message.edit_caption(caption=final_caption, reply_markup=None)
            except: pass # Ignore if message was deleted etc.
            await state.clear()

    # --- Promo Creation Confirmation ---
    elif current_state_str == CreatePromoStates.ConfirmPromo.state:
        promo_data = data.get('promo_data');
        if not promo_data: await callback.message.edit_text("❌ Ошибка: данные промокода не найдены."); await state.clear(); return
        final_text = "❌ Не удалось создать промокод."
        code = promo_manager.generate_promo_code(custom_code=promo_data.get('code'), reward_amount=promo_data['reward'], uses=promo_data['uses'])
        if code: final_text = f"✅ Промокод `{code}` на {promo_data['reward']} 🪙 ({promo_data['uses']} исп.) создан!"
        else: final_text = "❌ Не удалось создать промокод. Код занят?"
        try: await callback.message.edit_text(final_text, parse_mode="Markdown", reply_markup=None)
        except: pass
        await state.clear()

    # --- Broadcast Confirmation ---
    elif current_state_str == BroadcastState.ConfirmBroadcast.state:
        broadcast_message = data.get('broadcast_message')
        if not broadcast_message: await callback.message.edit_text("❌ Ошибка: текст для рассылки не найден."); await state.clear(); return
        await callback.message.edit_text("⏳ Начинаю рассылку...", reply_markup=None) # Update status
        user_ids = user_manager.get_all_user_ids(include_banned=False); sent_count=0; failed_count=0; total_users = len(user_ids)
        status_message_id = callback.message.message_id # To update progress

        logging.info(f"Starting broadcast to {total_users} users.")
        last_update_time = asyncio.get_event_loop().time()

        for i, user_id in enumerate(user_ids):
            try:
                await bot.send_message(user_id, broadcast_message, parse_mode="HTML", disable_web_page_preview=True) # Consider disable_web_page_preview
                sent_count += 1
            except Exception as e:
                failed_count += 1
                logging.info(f"Failed broadcast to {user_id}: {e}") # Log specific errors
            await asyncio.sleep(0.1) # Small delay between messages

            # Update status message periodically (e.g., every 5 seconds or 100 users)
            current_time = asyncio.get_event_loop().time()
            if current_time - last_update_time > 5 or (i + 1) % 100 == 0:
                 progress_text = f"⏳ Рассылка... ({i+1}/{total_users})\nУспешно: {sent_count}, Ошибок: {failed_count}"
                 try:
                     await bot.edit_message_text(progress_text, chat_id=callback.message.chat.id, message_id=status_message_id)
                     last_update_time = current_time
                 except TelegramBadRequest: # Ignore if message hasn't changed
                     pass
                 except Exception as edit_e:
                     logging.warning(f"Could not edit broadcast status message: {edit_e}")


        final_text = f"✅ Рассылка завершена!\nУспешно: {sent_count}, Ошибок: {failed_count}, Всего: {total_users}"
        try: await bot.edit_message_text(final_text, chat_id=callback.message.chat.id, message_id=status_message_id)
        except Exception as final_edit_e:
             logging.warning(f"Could not edit final broadcast status: {final_edit_e}")
             await callback.message.answer(final_text) # Send final status as new message if edit failed

        logging.info(f"Broadcast finished. Sent: {sent_count}, Failed: {failed_count}")
        await state.clear()

    # --- Case Creation Confirmation ---
    elif current_state_str == CreateCaseStates.ConfirmCase.state:
        case_data = data.get('case_data')
        if not case_data: await callback.message.edit_text("❌ Ошибка: данные кейса не найдены."); await state.clear(); return
        final_text = f"❌ Не удалось создать кейс '{case_data['name']}'."
        try:
            case_id = case_manager.create_case(name=case_data['name'], description=case_data['description'], card_count=case_data['card_count'], price_coins=case_data['price_coins'], price_shards=case_data['price_shards'])
            if case_id: final_text = f"✅ Кейс '{case_data['name']}' (ID: {case_id}) успешно создан!"
            else: final_text = f"❌ Не удалось создать кейс '{case_data['name']}'. Имя занято?"
        except Exception as e: logging.error(f"Error creating case: {e}"); final_text = f"❌ Ошибка при создании кейса: {e}"
        finally:
            try: await callback.message.edit_text(final_text, reply_markup=None)
            except: pass
            await state.clear()

    else:
        logging.warning(f"Received admin_confirm callback in unexpected state: {current_state_str}")
        try: await callback.message.edit_text("Неизвестное действие для подтверждения.")
        except: pass
        await state.clear()


# Use StateFilter("*") for aiogram 3.x
@admin_router.callback_query(F.data == "admin_cancel", StateFilter("*"))
async def handle_admin_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Отменено")
    try:
        if callback.message.photo:
             await callback.message.delete() # Delete the photo message on cancel
        else:
             await callback.message.edit_text("Действие отменено.", reply_markup=None)
    except Exception as e:
        # If deletion fails, maybe just edit text as fallback
        logging.info(f"Could not delete/edit message on admin cancel: {e}")
        await callback.message.answer("Действие отменено.") # Fallback reply