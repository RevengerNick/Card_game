import asyncio
import logging
import sys

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage # Или RedisStorage для продакшена

# Import routers
from bot.handlers.arena import arena_handler
from bot.handlers.mainMenu import dp as router_main_menu, create_back_button, back_button
from bot.handlers.clans import clan as clan_handler
#from bot.handlers.admin_handlers import admin_router # <<< NEW: Import admin router
from bot.dev.dev import router as router_development

# Хранилище для состояний (в памяти для простоты, лучше Redis для масштабирования)

fsm_storage = MemoryStorage()

from bot.common import bot

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.types import Update # Import Update type

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from datetime import datetime, timedelta, timezone

# Import managers and db instance AFTER database setup
from bot.Classes.db_manager import card_manager, user_manager, task_manager, db, command_manager, clan_manager, promo_manager
from bot.card_database import rarity_translate, DatabaseManager # Keep DatabaseManager if needed elsewhere

from bot.keyboards.main_keyboard import main_menu

# --- Ban Check Middleware (Optional but recommended) ---
class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # Works for both Message and CallbackQuery
        user = event.from_user
        if user:
            # Check if user exists and is banned using the raw method
            # Avoid get_user_info here as it might return None for banned users already
            user_data = user_manager.get_user_raw(user.id)
            if user_data and user_data.get('is_banned'):
                logging.info(f"User {user.id} is banned. Blocking event.")
                # Optionally send a message to the banned user
                # try:
                #     if isinstance(event, Message):
                #         await event.answer("🚫 Ваш аккаунт заблокирован.")
                #     elif isinstance(event, CallbackQuery):
                #         await event.answer("🚫 Ваш аккаунт заблокирован.", show_alert=True)
                # except Exception: pass # Ignore errors sending to banned users
                return # Stop processing the event
        return await handler(event, data)


# --- Dispatcher Setup ---
dp = Dispatcher(storage=fsm_storage)

# --- Register Middlewares ---
dp.message.outer_middleware(BanCheckMiddleware())
dp.callback_query.outer_middleware(BanCheckMiddleware())

# --- Register Routers (Admin router should be checked early if needed) ---
#dp.include_router(admin_router)      # <<< NEW: Added admin router
dp.include_router(arena_handler)
dp.include_router(router_development) # Dev router - keep it if needed for testing
dp.include_router(router_main_menu)
dp.include_router(clan_handler)
# Add other routers if you have them


# --- Existing Handlers (Example: get_card) ---

@dp.message(F.text == "🃏 Получить карточку")
async def get_card(message: Message):
    # Ban check is handled by middleware now
    user_manager.register_user(message.from_user.id, message.from_user.username) # Ensure user exists
    user_id = message.from_user.id

    if card_manager.can_receive_card(user_id):
        card = card_manager.get_random_card(user_id=user_id, exclude_received=False) # Pass user_id if needed
        if card:
            # Give card returns a dict now, check for rewards
            result = card_manager.give_card_to_user(user_id, card['id'], card["rarity"]) # Pass rarity

            caption = (
                f"{message.from_user.first_name}, ты получил новую карточку! 🃏\n"
                f"\n✨ <b>{card['name']}</b>\n"
                f"⚜️ Редкость: {rarity_translate.get(card['rarity'], card['rarity'])}\n" # Use .get for safety
                f"🔪 Атака: {card['attack']}\n"
                f"❤️ Здоровье: {card['health']}\n"
                f"\n💠 Ценность: {card['value']} pts"
            )
            photo = card.get('image_path') # Use .get for safety

            # Notify about rewards if any
            reward_text = ""
            if result.get('success') and result.get('rewards'):
                 reward_lines = []
                 for reward in result['rewards']:
                     if reward['type'] == 'coins':
                         reward_lines.append(f"💰 +{reward['amount']} монет за {reward['goal']} карт!")
                     elif reward['type'] == 'shards':
                          reward_lines.append(f"🀄️ +{reward['amount']} осколков за {reward['goal']} карт!")
                     # Add other reward types if implemented
                 if reward_lines:
                     reward_text = "\n\n🎁 **Бонусы за сбор:**\n" + "\n".join(reward_lines)
                 caption += reward_text # Append rewards to caption

            if photo:
                try:
                    await message.answer_photo(photo=photo, caption=caption, parse_mode="HTML", reply_markup=main_menu())
                except TelegramBadRequest as e:
                    logging.error(f"Error sending photo for card {card['id']} ({photo}): {e}")
                    await message.answer(caption, parse_mode="HTML", reply_markup=main_menu()) # Fallback to text
            else:
                await message.answer(caption, parse_mode="HTML", reply_markup=main_menu())

            # Update task progress (AFTER successful card grant)
            if result.get('success'):
                task_manager.update_task_progress(
                    user_id=user_id,
                    event_type='GET_CARD',
                    rarity=card['rarity']
                )
        else:
            # Check if it's because user has all cards or DB error
            all_cards_in_game = db.execute("SELECT COUNT(*) as count FROM cards", fetch='one')['count']
            user_unique_cards = db.execute("SELECT COUNT(DISTINCT card_id) as count FROM user_cards WHERE user_id = %s", (user_id,), fetch='one')['count']
            if user_unique_cards >= all_cards_in_game:
                 await message.answer("🎉 Поздравляем! Ты собрал все доступные карточки в игре!", reply_markup=main_menu())
            else:
                 await message.answer("⏳ Не удалось получить карту. Возможно, нет доступных карт или произошла ошибка. Попробуй позже.", reply_markup=main_menu())

    else:
        # Cooldown logic remains the same
        last_time = user_manager.get_last_card_time(user_id)
        # Ensure last_time is timezone-aware if comparing with aware datetime.now()
        if last_time and last_time.tzinfo is None:
             # Assuming DB stores UTC but without TZ info (adjust if needed)
             last_time = last_time.replace(tzinfo=timezone.utc)

        now_aware = datetime.now(timezone.utc)
        cooldown = timedelta(hours=4) # Define cooldown duration

        # Check if user has battle pass for reduced cooldown
        user_info = await user_manager.get_user_info(user_id) # Might be None if banned
        if user_info and user_info.has_battle_pass:
            cooldown = timedelta(hours=3)

        if last_time:
            remaining = cooldown - (now_aware - last_time)
            if remaining.total_seconds() > 0:
                 remaining_str = str(remaining).split(".")[0] # HH:MM:SS format

                 keyboard = InlineKeyboardMarkup(inline_keyboard=[
                     [InlineKeyboardButton(text="Купить 1 прокрут за 1 PoTi Coin", callback_data="buy_spin")] # Price corrected
                 ])

                 await message.answer(
                     f"🃏🙅‍♂ {message.from_user.first_name}, получать карточки можно раз в {cooldown.total_seconds() // 3600} часа. Приходи через:\n"
                     "➖➖➖➖➖➖\n"
                     f"   ⏳ {remaining_str}",
                     reply_markup=keyboard
                 )
            else:
                 # Should not happen if can_receive_card is False, but as a fallback:
                 await get_card(message) # Try again immediately if timer calculation was off

        else:
             # Should not happen if can_receive_card is False, but as a fallback:
             await get_card(message) # User never received a card


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




# --- Main Execution ---
async def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    # Add any bot startup logic here (e.g., setting commands)
    logging.info("Bot starting polling...")
    # Ensure DB connection is likely alive before starting polling
    try:
        db._get_connection().cursor().execute("SELECT 1")
    except Exception as e:
        logging.critical(f"Database connection failed on startup: {e}")
        return # Don't start polling if DB is down

    await dp.start_polling(bot)
    logging.info("Bot polling stopped.")

if __name__ == "__main__":

    # Ensure super admin exists on startup (moved this logic to card_database.py __main__)
    asyncio.run(main())
