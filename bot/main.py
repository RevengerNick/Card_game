# bot\main.py
import asyncio
import logging
import sys
from typing import Union

from aiogram.filters import Filter
# Настройка FSM Storage (MemoryStorage для разработки)
from aiogram.fsm.storage.memory import MemoryStorage
fsm_storage = MemoryStorage()
# Для Redis:
# from aiogram.fsm.storage.redis import RedisStorage
# from redis.asyncio import Redis
# redis_client = Redis(host='localhost', port=6379, db=0) # Настройте подключение
# fsm_storage = RedisStorage(redis=redis_client)

# Импорт роутеров в нужном порядке
from bot.handlers.admin_handlers import admin_router
from bot.dev.dev import router as router_development
from bot.handlers.mainMenu import dp as router_main_menu, create_back_button, back_button # mainMenu содержит dp? Переименовать dp в router?
from bot.handlers.arena import arena_handler
from bot.handlers.clans import clan as clan_handler

# Импорт common.py для экземпляра бота
from bot.common import bot # bot может быть None, если токен не найден

# Базовые импорты aiogram
from aiogram import Dispatcher, F, BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, User # Добавил User
from aiogram.exceptions import TelegramBadRequest, TelegramAPIError
from datetime import datetime, timedelta, timezone

# Импорт менеджеров и экземпляра БД
# Убедитесь, что db_manager.py успешно инициализирует ВСЕ менеджеры
from bot.Classes.db_manager import (
    card_manager, user_manager, task_manager, command_manager,
    clan_manager, promo_manager, case_manager, db # case_manager импортирован
)

# Импорт констант и хелперов
from bot.card_database import rarity_translate
from bot.keyboards.main_keyboard import main_menu

# --- Ban Check Middleware ---
class BanCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = event.from_user
        if user:
            try:
                # Используем синхронный метод get_user_raw
                user_data = user_manager.get_user_raw(user.id)
                if user_data and user_data.get('is_banned'):
                    logging.info(f"User {user.id} is banned. Blocking event type: {type(event).__name__}")
                    if isinstance(event, CallbackQuery):
                         try:
                             await event.answer("🚫 Ваш аккаунт заблокирован.", show_alert=True)
                         except Exception: pass # Игнорируем ошибки отправки забаненному
                    # Не отвечаем на сообщения от забаненных, чтобы не спамить
                    return # Останавливаем обработку
            except Exception as e:
                logging.error(f"Ошибка во время проверки бана для user {user.id}: {e}")
                # Решаем, блокировать ли событие при ошибке проверки? Безопаснее блокировать.
                # return # Раскомментировать для блокировки при ошибке
        return await handler(event, data)

# --- Dispatcher Setup ---
# Проверяем, что bot не None перед созданием Dispatcher
if bot is None:
    logging.critical("Экземпляр бота не создан (отсутствует токен?). Запуск невозможен.")
    exit(1)
# Проверяем, что менеджеры инициализированы
if user_manager is None: # Достаточно проверить один менеджер
     logging.critical("Менеджеры не были инициализированы (ошибка в db_manager?). Запуск невозможен.")
     exit(1)

dp = Dispatcher(storage=fsm_storage)

# --- Register Middlewares ---
dp.message.outer_middleware(BanCheckMiddleware())
dp.callback_query.outer_middleware(BanCheckMiddleware())

# --- Register Routers ---
# Порядок важен: специфичные (admin, dev) -> общие фичи -> главное меню
dp.include_router(admin_router)
dp.include_router(router_development)
dp.include_router(arena_handler)
dp.include_router(clan_handler)
# Обработчики из mainMenu (переименовать бы dp там в router)
dp.include_router(router_main_menu) # Этот роутер должен идти после более специфичных

# --- Existing Handlers (Example: get_card - ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ИЗ ПРЕДЫДУЩЕГО ОТВЕТА НЕ ИЗМЕНИЛИСЬ) ---
# Оставил только get_card как пример, остальные (my_cards, show_settings и т.д.) остаются такими же,
# как в предыдущем ответе, так как они не требовали изменений.

@dp.message(F.text == "🃏 Получить карточку")
async def get_card(message: Message):
    # Ban check is handled by middleware
    user_id = message.from_user.id
    username = message.from_user.username or f"User_{user_id}" # Use username or generate one

    # Ensure user is registered (idempotent operation)
    user_manager.register_user(user_id, username)

    # Check cooldown (consider Battle Pass reduction)
    user_info = await user_manager.get_user_info(user_id) # Use sync version
    if not user_info: # Should not happen if register_user worked, but handles edge cases
        logging.warning(f"User {user_id} not found after registration attempt in get_card.")
        await message.answer("Произошла ошибка. Попробуйте /start и затем снова.", reply_markup=main_menu())
        return

    cooldown_hours = 3 if user_info.has_battle_pass else 4
    can_receive, time_remaining = card_manager.can_receive_card(user_id, cooldown_hours=cooldown_hours)

    if can_receive:
        card = card_manager.get_random_card(user_id=user_id, exclude_received=False) # Consider exclude_received logic carefully
        if card:
            # Give card returns a dict now, including rewards
            result = card_manager.give_card_to_user(user_id, card['id'], card["rarity"], source='spin') # Pass rarity and source

            if result.get('success'):
                caption = (
                    f"{message.from_user.first_name}, ты получил новую карточку! 🃏\n"
                    f"\n✨ <b>{card['name']}</b>\n"
                    f"⚜️ Редкость: {rarity_translate.get(card['rarity'], card['rarity'].capitalize())}\n"
                    f"🔪 Атака: {card['attack']}\n"
                    f"❤️ Здоровье: {card['health']}\n"
                    f"\n💠 Ценность: {card['value']} pts"
                )
                photo_file_id = card.get('image_path')

                # Notify about rewards if any
                reward_text = ""
                if result.get('rewards'):
                     reward_lines = []
                     for reward in result['rewards']:
                         if reward['type'] == 'coins':
                             reward_lines.append(f"💰 +{reward['amount']} монет за {reward['goal']} карт!")
                         elif reward['type'] == 'shards':
                              reward_lines.append(f"🀄️ +{reward['amount']} осколков за {reward['goal']} карт!")
                         # Add other reward types if implemented (e.g., 'card')
                     if reward_lines:
                         # Используем HTML для жирного шрифта
                         reward_text = "\n\n🎁 <b>Бонусы за сбор:</b>\n" + "\n".join(reward_lines)
                     caption += reward_text # Append rewards to caption

                send_func = message.answer_photo if photo_file_id else message.answer
                kwargs = {"caption": caption, "parse_mode": "HTML", "reply_markup": main_menu()}
                if photo_file_id:
                    kwargs["photo"] = photo_file_id

                try:
                    await send_func(**kwargs)
                except TelegramBadRequest as e:
                    logging.error(f"Error sending photo for card {card['id']} ({photo_file_id}): {e}. Falling back to text.")
                    # Fallback to text if photo sending fails (e.g., invalid file_id)
                    await message.answer(caption, parse_mode="HTML", reply_markup=main_menu())
                except Exception as e:
                     logging.error(f"Unexpected error sending card message: {e}")
                     await message.answer("Произошла ошибка при отправке карты.", reply_markup=main_menu())


                # Update task progress (AFTER successful card grant)
                task_manager.update_task_progress(
                    user_id=user_id,
                    event_type='GET_CARD',
                    rarity=card['rarity']
                )
            else:
                # Handle failure from give_card_to_user (e.g., DB error)
                 logging.error(f"Failed to give card {card['id']} to user {user_id}: {result.get('message')}")
                 await message.answer("⏳ Не удалось выдать карту из-за внутренней ошибки. Попробуй позже.", reply_markup=main_menu())

        else:
            # Check if it's because user has all cards or DB error/no cards exist
            all_cards_in_game_row = db.execute("SELECT COUNT(*) as count FROM cards", fetch='one')
            user_unique_cards_row = db.execute("SELECT COUNT(DISTINCT card_id) as count FROM user_cards WHERE user_id = %s", (user_id,), fetch='one')
            all_cards_in_game = all_cards_in_game_row['count'] if all_cards_in_game_row else 0
            user_unique_cards = user_unique_cards_row['count'] if user_unique_cards_row else 0


            if user_unique_cards >= all_cards_in_game and all_cards_in_game > 0 :
                 await message.answer("🎉 Поздравляем! Ты собрал все доступные карточки в игре!", reply_markup=main_menu())
            else:
                 logging.warning(f"get_random_card returned None for user {user_id}. No cards available or DB error?")
                 await message.answer("⏳ Не удалось получить карту. Возможно, нет доступных карт или произошла ошибка. Попробуй позже.", reply_markup=main_menu())

    else:
        # Cooldown logic
        remaining_str = str(time_remaining).split(".")[0] # HH:MM:SS format
        cooldown_hours_str = int(cooldown_hours)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
             [InlineKeyboardButton(text="Купить 1 прокрут за 1 🪙", callback_data="buy_spin")]
        ])

        await message.answer(
            f"🃏🙅‍♂ {message.from_user.first_name}, получать карточки можно раз в {cooldown_hours_str} час{'а' if 2 <= cooldown_hours_str <= 4 else 'ов'}. "
            f"Приходи через:\n"
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
        f"🆔 *Твой айди:* {user_id}\n"
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
    # Setup logging
    log_format = '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format=log_format)
    # Настройте уровень логирования для aiogram и других библиотек по необходимости
    logging.getLogger('aiogram.event').setLevel(logging.INFO) # Менее подробное логирование событий aiogram
    logging.getLogger('aiogram. FSM').setLevel(logging.INFO) # Логирование FSM

    # Проверка соединения с БД перед запуском
    try:
        conn = db._get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        logging.info("Проверка соединения с базой данных прошла успешно.")
    except Exception as e:
        logging.critical(f"Критическая ошибка: Не удалось подключиться к базе данных перед запуском бота: {e}")
        print(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к БД: {e}. Проверьте настройки и доступность сервера PostgreSQL.", file=sys.stderr)
        return # Останавливаем выполнение

    logging.info("Запуск бота...")
    # Запуск polling
    try:
        # allowed_updates чтобы получать только нужные типы обновлений
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logging.critical(f"Критическая ошибка во время работы бота: {e}", exc_info=True)
    finally:
        logging.info("Остановка бота...")
        # Закрываем соединение с БД
        db.close()
        # Закрываем сессию бота
        await bot.session.close()
        logging.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную (KeyboardInterrupt).")
    except Exception as main_e:
        logging.critical(f"Непредвиденная ошибка на верхнем уровне: {main_e}", exc_info=True)

