
# --- bot\card_database.py ---
# --- bot\card_database.py ---
import psycopg2
import psycopg2.extras # для DictCursor
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import os
import logging # Import logging

# ... (rest of your imports and dataclasses) ...

# --- Конфигурация ---
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))

DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ... (UserProfile, DeckProfile, rarity_translate, RARITY_CHOICES, RARITY_WEIGHTS) ...

# --- Базовый класс для управления БД ---
class DatabaseManager:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._conn = None
        try: # <<< Add try block here
            self._connect()
            self.create_tables() # Create tables only after successful connection
        except psycopg2.OperationalError as e: # Catch the specific connection error
             # Log the critical error
             logging.critical(f"КРИТИЧЕСКАЯ ОШИБКА ПОДКЛЮЧЕНИЯ К БАЗЕ ДАННЫХ!")
             logging.critical(f"DSN: {self.dsn}")
             logging.critical(f"Ошибка psycopg2: {e}")
             logging.critical(f"ПОЖАЛУЙСТА, ПРОВЕРЬТЕ:")
             logging.critical(f"  1. Запущен ли сервер PostgreSQL?")
             logging.critical(f"  2. Правильно ли указаны хост ({DB_HOST}) и порт ({DB_PORT})?")
             logging.critical(f"  3. Настроен ли PostgreSQL для приема TCP/IP соединений (pg_hba.conf, postgresql.conf)?")
             logging.critical(f"  4. Нет ли проблем с сетью или фаерволом?")
             # Re-raise the exception to stop the application gracefully
             raise

    def _connect(self):
        """Устанавливает соединение с БД. Raises psycopg2.OperationalError on failure."""
        # No try-except here, let the caller handle it or the __init__ block
        self._conn = psycopg2.connect(self.dsn)
        logging.info(f"Успешное подключение к PostgreSQL ({DB_HOST}:{DB_PORT})") # Use logging

    # ... (rest of DatabaseManager methods: _get_connection, drop_all_tables, execute, executescript, close, create_tables) ...

    # IMPORTANT: Keep the create_tables method with the added case tables from the previous step
    def create_tables(self):
        """Создает все необходимые таблицы с нуля (если они не существуют)."""
        script = """
        -- Таблица карт
        CREATE TABLE IF NOT EXISTS cards (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            rarity TEXT NOT NULL,
            attack INTEGER NOT NULL,
            health INTEGER NOT NULL,
            value INTEGER NOT NULL,
            image_path TEXT,
            drop_weight INTEGER DEFAULT 1
        );

        -- Таблица кланов
        CREATE TABLE IF NOT EXISTS clans (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            description TEXT,
            points INTEGER DEFAULT 0,
            rank INTEGER DEFAULT 0,
            leader_id BIGINT
        );

        -- Таблица пользователей
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            registered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            clan_id INTEGER REFERENCES clans(id) ON DELETE SET NULL,
            clan_role TEXT DEFAULT NULL,
            has_battle_pass BOOLEAN NOT NULL DEFAULT FALSE,
            rating INTEGER NOT NULL DEFAULT 0,
            season_rating INTEGER NOT NULL DEFAULT 0,
            coins INTEGER NOT NULL DEFAULT 0,
            last_card_received TIMESTAMP WITH TIME ZONE,
            referrals INTEGER NOT NULL DEFAULT 0,
            referrer_id BIGINT DEFAULT NULL REFERENCES users(user_id) ON DELETE SET NULL,
            total_cards_received INTEGER NOT NULL DEFAULT 0,
            free_spins INTEGER NOT NULL DEFAULT 0,
            shards_rare INTEGER NOT NULL DEFAULT 0,
            shards_epic INTEGER NOT NULL DEFAULT 0,
            shards_legendary INTEGER NOT NULL DEFAULT 0,
            season_wins INTEGER NOT NULL DEFAULT 0,
            season_losses INTEGER NOT NULL DEFAULT 0,
            all_wins INTEGER NOT NULL DEFAULT 0,
            all_losses INTEGER NOT NULL DEFAULT 0,
            total_duplicates_received INTEGER NOT NULL DEFAULT 0,
            shards INTEGER NOT NULL DEFAULT 0,
            is_banned BOOLEAN NOT NULL DEFAULT FALSE
        );

        -- Таблица администраторов
        CREATE TABLE IF NOT EXISTS admins (
            user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
            added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );

        -- Таблица колод пользователей
        CREATE TABLE IF NOT EXISTS user_decks (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            card_id INTEGER REFERENCES cards(id) ON DELETE SET NULL,
            position INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, position)
        );

        -- Таблица карт пользователя
        CREATE TABLE IF NOT EXISTS user_cards (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            amount INTEGER NOT NULL DEFAULT 1,
            obtained_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, card_id)
        );

        -- Таблица промокодов
        CREATE TABLE IF NOT EXISTS promo_achievements (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE,
            reward_amount INTEGER NOT NULL,
            uses_left INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );

        -- Таблица использованных промокодов
        CREATE TABLE IF NOT EXISTS user_promos (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            promo_id INTEGER NOT NULL REFERENCES promo_achievements(id) ON DELETE CASCADE,
            used_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, promo_id)
        );

        -- === Таблицы для Ежедневных Заданий ===
        -- ... (daily_tasks, user_daily_tasks, daily_active_tasks, daily_bonus_claimed) ...
        -- 1. Справочник заданий
        CREATE TABLE IF NOT EXISTS daily_tasks (
            id SERIAL PRIMARY KEY,
            description TEXT NOT NULL,
            task_type TEXT NOT NULL,
            target INTEGER NOT NULL,
            rarity_condition TEXT DEFAULT NULL,
            reward_shards INTEGER NOT NULL DEFAULT 5
        );

        -- 2. Прогресс пользователя по заданиям
        CREATE TABLE IF NOT EXISTS user_daily_tasks (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            task_id INTEGER NOT NULL REFERENCES daily_tasks(id) ON DELETE CASCADE,
            progress INTEGER NOT NULL DEFAULT 0,
            target INTEGER NOT NULL,
            completed BOOLEAN NOT NULL DEFAULT FALSE,
            reward_claimed BOOLEAN NOT NULL DEFAULT FALSE,
            date DATE NOT NULL DEFAULT CURRENT_DATE,
            UNIQUE (user_id, task_id, date)
        );

        -- 3. Активные задания на день
        CREATE TABLE IF NOT EXISTS daily_active_tasks (
            date DATE PRIMARY KEY,
            task_ids INTEGER[] NOT NULL
        );

        -- 4. Отметка получения бонуса за все задания дня
        CREATE TABLE IF NOT EXISTS daily_bonus_claimed (
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            date DATE NOT NULL DEFAULT CURRENT_DATE,
            claimed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (user_id, date)
        );


        -- === Таблицы для Кейсов (Card Packs) ===
        CREATE TABLE IF NOT EXISTS card_cases (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            card_count INTEGER NOT NULL DEFAULT 1,
            price_coins INTEGER DEFAULT 0 CHECK (price_coins >= 0),
            price_shards INTEGER DEFAULT 0 CHECK (price_shards >= 0)
            -- image_path TEXT  -- Optional: Add later if needed
        );

        CREATE TABLE IF NOT EXISTS case_cards (
            case_id INTEGER NOT NULL REFERENCES card_cases(id) ON DELETE CASCADE,
            card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            drop_weight INTEGER NOT NULL DEFAULT 1 CHECK (drop_weight > 0),
            PRIMARY KEY (case_id, card_id)
        );

        -- === Индексы ===
        -- ... (Existing indexes) ...
        CREATE INDEX IF NOT EXISTS idx_user_decks_user_id ON user_decks(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_decks_card_id ON user_decks(card_id);
        CREATE INDEX IF NOT EXISTS idx_user_cards_user_id ON user_cards(user_id);
        CREATE INDEX IF NOT EXISTS idx_users_clan_id ON users(clan_id);
        CREATE INDEX IF NOT EXISTS idx_user_daily_tasks_user_date ON user_daily_tasks(user_id, date);
        CREATE INDEX IF NOT EXISTS idx_promo_achievements_code ON promo_achievements(code);
        CREATE INDEX IF NOT EXISTS idx_daily_tasks_type ON daily_tasks(task_type);
        CREATE INDEX IF NOT EXISTS idx_admins_user_id ON admins(user_id);
        CREATE INDEX IF NOT EXISTS idx_users_is_banned ON users(is_banned);
        CREATE INDEX IF NOT EXISTS idx_case_cards_case_id ON case_cards(case_id);
        CREATE INDEX IF NOT EXISTS idx_case_cards_card_id ON case_cards(card_id);
        CREATE INDEX IF NOT EXISTS idx_card_cases_name ON card_cases(name); -- Index for case lookup by name
        """
        self.executescript(script)
        logging.info("Создание/обновление таблиц (включая кейсы) выполнено.") # Use logging

        # --- Foreign key for clans.leader_id ---
        # ... (existing logic for adding fk_clans_leader) ...

        logging.info("--- Проверка и создание всех таблиц завершены ---") # Use logging

# --- Instantiate DatabaseManager ---
# This will now raise the OperationalError immediately if connection fails
try:
    db = DatabaseManager(DSN)
except psycopg2.OperationalError:
     # The error is already logged critically inside __init__
     # Exit gracefully if the DB connection failed on startup
     logging.critical("Завершение работы из-за ошибки подключения к БД.")
     exit(1) # Exit the script


if __name__ == '__main__':
    # ... (rest of your __main__ block, e.g., ensuring super admin) ...
     if SUPER_ADMIN_ID != 0:
         conn = None
         try:
             # Get connection safely AFTER db object is potentially created
             conn = db._get_connection()
             with conn.cursor() as cur:
                 cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (SUPER_ADMIN_ID, 'SUPER_ADMIN'))
                 cur.execute("INSERT INTO admins (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (SUPER_ADMIN_ID,))
             conn.commit()
             logging.info(f"Super Admin ID {SUPER_ADMIN_ID} ensured in admins table.")
         except psycopg2.Error as e:
             if conn: conn.rollback()
             logging.error(f"Error ensuring super admin: {e}")
         except NameError:
              logging.error("Переменная 'db' не определена. Не удалось добавить супер админа.")
         # Don't close the connection here if the bot needs it later
     else:
         logging.warning("SUPER_ADMIN_ID не установлен. Супер админ не будет добавлен автоматически.")
     pass


# --- bot\common.py ---
from aiogram.client.default import DefaultBotProperties
from aiogram import Bot
import os, json

# Загрузка конфигурации
file_path = os.getenv('python_conf')
with open(file_path, 'r') as file:
    config = json.load(file)
TOKEN = config.get("bot_revcard")


bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode='HTML'))


# --- bot\main.py ---
# --- bot\main.py ---
import asyncio
import logging
import sys

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage # Или RedisStorage для продакшена

# Import routers
from bot.handlers.arena import arena_handler
from bot.handlers.mainMenu import dp as router_main_menu, create_back_button, back_button
from bot.handlers.clans import clan as clan_handler
from bot.handlers.admin_handlers import admin_router # <<< NEW: Import admin router
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
dp.include_router(admin_router)      # <<< NEW: Added admin router
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


# ... (rest of your existing main.py handlers like my_cards, show_settings, show_rarity_cards, change_nickname, buy_spin etc.) ...
# Ensure they use await user_manager.get_user_info() where needed


# --- Main Execution ---
async def main() -> None:
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
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s - %(levelname)s - %(message)s')
    # Ensure super admin exists on startup (moved this logic to card_database.py __main__)
    asyncio.run(main())


# --- bot\Classes\CardManager.py ---
from datetime import timedelta, datetime
from typing import Optional,  Any, List, Dict


from psycopg2.tz import FixedOffsetTimezone

from bot.card_database import DatabaseManager, RARITY_WEIGHTS, reward_levels, db
from bot.Classes.UserManager import UserManager
import random
import psycopg2
import psycopg2.extras # для DictCursor

class CardManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.user_manager = UserManager(db_manager) # Может понадобиться для обновления времени

    def add_card(self, name: str, rarity: str, attack: int, health: int, value: int, image_path: Optional[str] = None) -> Optional[int]:
        """Добавляет новую карту в игру. Возвращает ID новой карты или None."""
        drop_weight = RARITY_WEIGHTS.get(rarity.lower(), 1)
        query = """
            INSERT INTO cards (name, rarity, attack, health, value, image_path, drop_weight)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        result = self.db.execute(query, (name, rarity, attack, health, value, image_path, drop_weight), fetch='one')
        return result['id'] if result else None

    def edit_card(self, card_id: int, name: Optional[str] = None, rarity: Optional[str] = None,
                  attack: Optional[int] = None, health: Optional[int] = None, value: Optional[int] = None,
                  image_path: Optional[str] = None):
        """Редактирует существующую карту."""
        # Сначала получаем текущие значения, чтобы не перезаписывать NULL'ами
        current_card = self.get_card_by_id(card_id)
        if not current_card:
            print(f"Карта с ID {card_id} не найдена для редактирования.")
            return

        updates = []
        params = []

        if name is not None:
            updates.append("name = %s")
            params.append(name)
        else: name = current_card['name'] # Нужно для обновления веса

        if rarity is not None:
            updates.append("rarity = %s")
            params.append(rarity)
            updates.append("drop_weight = %s")
            params.append(RARITY_WEIGHTS.get(rarity.lower(), 1))
        else: rarity = current_card['rarity'] # Нужно для обновления веса

        if attack is not None:
            updates.append("attack = %s")
            params.append(attack)
        if health is not None:
            updates.append("health = %s")
            params.append(health)
        if value is not None:
            updates.append("value = %s")
            params.append(value)
        if image_path is not None: # Позволяем установить image_path в NULL
            updates.append("image_path = %s")
            params.append(image_path)

        if not updates:
            print("Нет полей для обновления.")
            return

        params.append(card_id) # Добавляем ID для WHERE
        query = f"UPDATE cards SET {', '.join(updates)} WHERE id = %s"
        self.db.execute(query, tuple(params))

    def get_card_by_id(self, card_id: int) -> Optional[Dict[str, Any]]:
        """Получает информацию о карте по ID."""
        query = "SELECT * FROM cards WHERE id = %s"
        return self.db.execute(query, (card_id,), fetch='one')


    def get_all_cards(self) -> List[Dict[str, Any]]:
        """Получает список всех карт в игре."""
        query = "SELECT * FROM cards ORDER BY rarity, name"
        return self.db.execute(query, fetch='all') or []

    def get_user_cards(self, user_id: int) -> List[Dict[str, Any]]:
        """Получает список карт пользователя с их количеством."""
        query = """
            SELECT c.*, uc.amount, uc.obtained_at
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = %s
            ORDER BY c.rarity, c.name;
        """
        return self.db.execute(query, (user_id,), fetch='all') or []

    def can_receive_card(self, user_id: int, cooldown_hours: int = 4) -> bool:
        """Проверяет, может ли пользователь получить карту (прошел ли кулдаун)."""
        last_time = self.user_manager.get_last_card_time(user_id)
        if not last_time:
            return True # Никогда не получал карту
        # Убедимся, что last_time в UTC, если оно из БД TIMESTAMPTZ
        # psycopg2 обычно возвращает aware datetime, если тип TIMESTAMPTZ
        # Сравнение aware и naive вызовет ошибку, поэтому делаем now() aware
        now_utc = datetime.now(tz=last_time.tzinfo) # Используем таймзону из БД
        return now_utc - last_time >= timedelta(hours=cooldown_hours)

    def reset_last_received_time(self, user_id: int):
        """Сбрасывает таймер получения карты (для админских команд)."""
        # Ставим время так, чтобы can_receive_card сразу вернуло True
        reset_time = datetime.utcnow() - timedelta(hours=5) # Убедимся, что это UTC
        # psycopg2 требует aware datetime для TIMESTAMPTZ, добавим UTC
        reset_time = reset_time.replace(tzinfo=FixedOffsetTimezone(offset=0))
        self.user_manager.update_last_card_time(user_id, reset_time)

    def give_card_to_user(self, user_id: int, card_id: int, rarity: str, amount: int = 1) -> Dict[str, Any]:
        """
        Выдает карту пользователю, обновляет счетчики и проверяет/выдает награды за этапы.
        Возвращает словарь с результатом и списком выданных наград.
        Пример: {'success': True, 'rewards': [{'type': 'coins', 'amount': 100}, {'type': 'card', 'count': 3}]}
        """
        if amount <= 0:
            return {'success': False, 'message': 'Amount must be positive'}
        now = datetime.utcnow().replace(tzinfo=psycopg2.tz.FixedOffsetTimezone(offset=0, name=None))

        conn = self.db._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # 1. Обновляем user_cards и определяем, была ли это повторка
                insert_update_query = """
                    WITH uc_update AS (
                        INSERT INTO user_cards (user_id, card_id, amount, obtained_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (user_id, card_id) DO UPDATE SET
                            amount = user_cards.amount + EXCLUDED.amount,
                            obtained_at = EXCLUDED.obtained_at
                        RETURNING xmax
                    )
                    SELECT xmax FROM uc_update;
                """
                cur.execute(insert_update_query, (user_id, card_id, amount, now))
                result = cur.fetchone()
                if result is None:
                     raise Exception("INSERT/UPDATE в user_cards не вернул результат.") # Прерываем транзакцию

                is_duplicate = result['xmax'] != 0
                duplicates_to_add_this_time = amount if is_duplicate else 0

                # 2. Обновляем users и получаем НОВОЕ значение total_cards_received
                update_users_query = """
                    UPDATE users
                    SET
                        last_card_received = %s,
                        total_cards_received = total_cards_received + %s,
                        total_duplicates_received = total_duplicates_received + %s
                    WHERE user_id = %s
                    RETURNING total_cards_received; -- Возвращаем новое значение
                """
                cur.execute(update_users_query, (now, amount, duplicates_to_add_this_time, user_id))
                result = cur.fetchone()
                if result is None:
                    # Пользователь не найден? Это странно, если мы дошли сюда.
                    raise Exception(f"Пользователь {user_id} не найден при обновлении счетчиков.")

                new_total_received = result['total_cards_received']
                old_total_received = new_total_received - amount # Вычисляем старое значение

                # --- Логика проверки и выдачи наград ---
                rewards_granted_list = []
                total_coins_reward = 0
                total_shards_reward = 0
                reward_cards_to_add = [] # Список ID карт для награды

                for goal, coins_reward, shards in reward_levels:
                    # Проверяем, был ли порог ПЕРЕСЕЧЕН именно в этом вызове
                    if old_total_received < goal <= new_total_received:
                        print(f"Пользователь {user_id} достиг рубежа {goal} карт!") # Лог
                        if coins_reward > 0:
                             total_coins_reward += coins_reward
                             rewards_granted_list.append({'type': 'coins', 'amount': coins_reward, 'goal': goal})
                        if coins_reward > 0:
                            total_shards_reward += shards
                            rewards_granted_list.append({'type': 'shards', 'amount': shards, 'goal': goal})
                #
                #         # Генерируем ID карт для награды
                #         if card_reward_count > 0:
                #             current_reward_cards = []
                #             for _ in range(card_reward_count):
                #                 # Используем вспомогательный метод или get_random_card
                #                 random_reward_card = self._get_random_card_for_reward(user_id)
                #                 if random_reward_card:
                #                     reward_cards_to_add.append(random_reward_card['id'])
                #                     current_reward_cards.append(random_reward_card['name']) # Для лога/сообщения
                #                 else:
                #                     print(f"Не удалось получить случайную карту для награды на рубеже {goal}")
                #             if current_reward_cards:
                #                  rewards_granted_list.append({'type': 'card', 'count': card_reward_count, 'goal': goal, 'cards': current_reward_cards})
                #
                #
                # # 3. Применяем награды (если есть) в той же транзакции
                #
                # # Обновляем монеты (если есть награда)
                print("money")
                if total_coins_reward > 0:
                    print(f"give money{total_shards_reward}")
                    #self.user_manager.add_coins(user_id, tot)
                    print(self.user_manager.get_coins(user_id))
                    self.user_manager.add_coins(user_id, total_coins_reward)
                    print(self.user_manager.get_coins(user_id))
                    #cur.execute("UPDATE users SET coins = coins + %s WHERE user_id = %s", (total_coins_reward, user_id))

                if total_shards_reward > 0:
                    print("give shards")
                    self.user_manager.add_shards(user_id, total_shards_reward)
                    #cur.execute("UPDATE users SET coins = coins + %s WHERE user_id = %s", (total_coins_reward, user_id))
                #
                # # Выдаем наградные карты
                # if reward_cards_to_add:
                #     # Важно: Выдача наградных карт НЕ должна менять last_card_received
                #     # и НЕ должна влиять на счетчики total_cards/duplicates (они уже учтены)
                #     # и НЕ должна триггерить новые награды.
                #     reward_card_query = """
                #         INSERT INTO user_cards (user_id, card_id, amount, obtained_at)
                #         VALUES (%s, %s, %s, %s)
                #         ON CONFLICT (user_id, card_id) DO UPDATE SET
                #             amount = user_cards.amount + EXCLUDED.amount,
                #             obtained_at = EXCLUDED.obtained_at; -- Можно оставить старое время, если не хотим обновлять для наград
                #     """
                #     reward_obtained_at = now # Или использовать другое время для наград
                #     for reward_card_id in reward_cards_to_add:
                #          # Выдаем по одной (amount=1)
                #          cur.execute(reward_card_query, (user_id, reward_card_id, 1, reward_obtained_at))

                # Коммитим всю транзакцию (основная карта + награды)
                conn.commit()
                return {'success': True, 'rewards': rewards_granted_list}

        except psycopg2.Error as e:
            conn.rollback()
            print(f"Ошибка psycopg2 при выдаче карты/награды пользователю {user_id}: {e}")
            return {'success': False, 'message': f"Ошибка базы данных: {e}"}
        except Exception as e:
            conn.rollback()
            print(f"Неожиданная ошибка при выдаче карты/награды: {e}")
            return {'success': False, 'message': f"Внутренняя ошибка: {e}"}

    def remove_card_from_user(self, user_id: int, card_id: int, amount: int = 1) -> bool:
        """Удаляет карту у пользователя или уменьшает ее количество."""
        if amount <= 0: return False

        conn = self.db._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # Получаем текущее количество с блокировкой строки
                cur.execute("SELECT id, amount FROM user_cards WHERE user_id = %s AND card_id = %s FOR UPDATE", (user_id, card_id))
                existing = cur.fetchone()

                if not existing or existing['amount'] < amount:
                    conn.rollback() # Недостаточно карт или нет такой карты
                    return False

                if existing['amount'] > amount:
                    # Уменьшаем количество
                    cur.execute("UPDATE user_cards SET amount = amount - %s WHERE id = %s", (amount, existing['id']))
                else:
                    # Удаляем запись полностью
                    cur.execute("DELETE FROM user_cards WHERE id = %s", (existing['id'],))
                conn.commit()
                return True
        except psycopg2.Error as e:
            conn.rollback()
            print(f"Ошибка при удалении карты у пользователя: {e}")
            return False

    def get_random_card(self, user_id: Optional[int] = None, exclude_received: bool = False) -> Optional[Dict[str, Any]]:
        """
        Возвращает случайную карту с учетом веса редкости.
        exclude_received - исключить карты, которые УЖЕ есть у пользователя (хотя бы 1 шт).
        """
        query = "SELECT * FROM cards"
        params = []

        # ВАЖНО: exclude_received=True исключает ЛЮБУЮ карту, которая есть у юзера.
        # Если нужно исключать только те, что получены в ПОСЛЕДНИЙ РАЗ - логика сложнее.
        # Если нужно давать только те, которых НЕТ СОВСЕМ - так и делаем.
        if exclude_received and user_id is not None:
            # Выбираем карты, ID которых НЕТ в user_cards для данного user_id
            query += " WHERE id NOT IN (SELECT card_id FROM user_cards WHERE user_id = %s)"
            params.append(user_id)

        all_possible_cards = self.db.execute(query, tuple(params), fetch='all')

        if not all_possible_cards:
            # Если exclude_received=True, возможно, пользователь собрал все карты?
            # Попробуем вернуть любую карту, если ничего не найдено с исключением
            if exclude_received:
                 all_possible_cards = self.db.execute("SELECT * FROM cards", fetch='all')
                 if not all_possible_cards: return None # Карт вообще нет в игре
            else:
                 return None # Карт нет по исходному запросу

        # Используем веса редкости для выбора
        try:
             weights = [RARITY_WEIGHTS.get(card['rarity'].lower(), 1) for card in all_possible_cards]
             chosen_card = random.choices(all_possible_cards, weights=weights, k=1)[0]
             return dict(chosen_card) # Возвращаем как словарь
        except IndexError:
             return None # Если random.choices по какой-то причине не сработал

    def get_user_card_counts_by_rarity(self, user_id: int) -> Dict[str, int]:
        """
        Возвращает количество карт пользователя, сгруппированное по редкости.
        Пример результата: {'common': 5, 'rare': 2, 'legendary': 1}
        """
        query = """
            SELECT c.rarity, COUNT(uc.card_id) as count
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = %s
            GROUP BY c.rarity;
        """
        results = self.db.execute(query, (user_id,), fetch='all')
        # Преобразуем список DictRow в словарь
        counts_dict = {row['rarity']: row['count'] for row in results} if results else {}
        return counts_dict

    def get_user_cards_ordered_by_value(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Возвращает список карт пользователя (с информацией о карте и количестве),
        отсортированный по ценности (value) по убыванию.
        """
        query = """
            SELECT c.*, uc.amount, uc.obtained_at
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = %s
            ORDER BY c.value DESC, c.id ASC; -- Добавим сортировку по ID для стабильности
        """
        results = self.db.execute(query, (user_id,), fetch='all')
        return [dict(row) for row in results] if results else []

    def get_user_cards_by_rarity(self, user_id: int, rarity: str) -> List[Dict[str, Any]]:
        """
        Возвращает список карт пользователя (с информацией о карте и количестве)
        указанной редкости.
        """
        query = """
            SELECT c.*, uc.amount, uc.obtained_at
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = %s AND c.rarity = %s
            ORDER BY c.name ASC; -- Сортируем по имени для удобства
        """
        # Приводим редкость к нижнему регистру для надежности сравнения,
        # если в базе могут быть разные регистры (хотя лучше следить за этим при вставке)
        results = self.db.execute(query, (user_id, rarity.lower()), fetch='all')
        return [dict(row) for row in results] if results else []

#card_manager = CardManager(db)


# --- bot\Classes\ClanManager.py ---
from typing import Optional, Tuple, Any, List, Dict

from bot.card_database import DatabaseManager


class ClanManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def create_clan(self, name: str, leader_id: int, description: Optional[str] = None) -> Optional[int]:
        """Создает новый клан и назначает пользователя лидером. Возвращает ID клана."""
        # 1. Проверить, не состоит ли лидер уже в клане
        user_info = self.db.execute("SELECT clan_id FROM users WHERE user_id = %s", (leader_id,), fetch='one')
        if user_info and user_info['clan_id'] is not None:
            print(f"Пользователь {leader_id} уже состоит в клане.")
            return None

        # 2. Создать клан
        clan_query = """
            INSERT INTO clans (name, leader_id, description) VALUES (%s, %s, %s)
            ON CONFLICT (name) DO NOTHING
            RETURNING id;
        """
        clan_result = self.db.execute(clan_query, (name, leader_id, description), fetch='one')

        if not clan_result:
            print(f"Клан с именем '{name}' уже существует или произошла ошибка.")
            # Нужно откатить транзакцию, если она была начата неявно в execute
            self.db._get_connection().rollback()
            return None

        clan_id = clan_result['id']

        # 3. Назначить пользователя лидером в таблице users
        user_update_query = "UPDATE users SET clan_id = %s, clan_role = 'leader' WHERE user_id = %s"
        self.db.execute(user_update_query, (clan_id, leader_id))
        # Коммит произойдет внутри execute user_update_query

        print(f"Клан '{name}' (ID: {clan_id}) успешно создан. Лидер: {leader_id}")
        return clan_id

    def get_clan_info(self, clan_id: int) -> Optional[Dict[str, Any]]:
        """Получает подробную информацию о клане."""
        clan_query = """
            SELECT c.*, u.username as leader_username
            FROM clans c
            LEFT JOIN users u ON c.leader_id = u.user_id
            WHERE c.id = %s;
        """
        clan = self.db.execute(clan_query, (clan_id,), fetch='one')
        if not clan:
            return None

        members_query = """
            SELECT user_id, username, rating, clan_role
            FROM users
            WHERE clan_id = %s
            ORDER BY clan_role DESC, rating DESC; -- Лидер и замы вверху, потом по рейтингу
        """
        members = self.db.execute(members_query, (clan_id,), fetch='all') or []

        deputies = [
            {"user_id": m["user_id"], "username": m["username"]}
            for m in members if m["clan_role"] == "deputy"
        ]

        # Топ-7 участников по рейтингу (исключая лидера/замов, если нужно другое поведение)
        top7_members = sorted(members, key=lambda x: x['rating'], reverse=True)[:7]

        return {
            "id": clan["id"],
            "name": clan["name"],
            "description": clan["description"],
            "points": clan["points"],
            "rank": clan["rank"],
            "leader_id": clan["leader_id"],
            "leader_username": clan["leader_username"],
            "deputies": deputies,
            "top7": [{"user_id": m["user_id"], "username": m["username"], "rating": m["rating"]} for m in top7_members],
            "members_count": len(members)
        }

    def get_top_clans(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает топ кланов по очкам."""
        query = """
            SELECT
                c.id,
                c.name,
                c.points,
                c.rank,
                (SELECT COUNT(*) FROM users u WHERE u.clan_id = c.id) as members_count
            FROM clans c
            ORDER BY c.points DESC, c.id ASC -- Добавим сортировку по ID для стабильности
            LIMIT %s;
        """
        clans = self.db.execute(query, (limit,), fetch='all')
        return [dict(clan) for clan in clans] if clans else []

    def add_user_to_clan(self, user_id: int, clan_id: int) -> bool:
        """Добавляет пользователя в клан."""
         # Проверить, не состоит ли уже в клане
        user_info = self.db.execute("SELECT clan_id FROM users WHERE user_id = %s", (user_id,), fetch='one')
        if user_info and user_info['clan_id'] is not None:
            print(f"Пользователь {user_id} уже состоит в клане.")
            return False

        query = "UPDATE users SET clan_id = %s, clan_role = 'member' WHERE user_id = %s"
        self.db.execute(query, (clan_id, user_id))
        # Проверить бы количество строк, обновленных execute, если бы он это возвращал
        return True # Упрощенно

    def remove_user_from_clan(self, user_id: int) -> bool:
        """Удаляет пользователя из клана."""
        query = "UPDATE users SET clan_id = NULL, clan_role = NULL WHERE user_id = %s"
        self.db.execute(query, (user_id,))
        # Проверить бы количество строк
        return True

    def set_clan_role(self, user_id: int, clan_id: int, role: Optional[str]) -> bool:
        """Устанавливает роль пользователя в клане (member, deputy, leader)."""
        # Проверка, что пользователь вообще в этом клане
        user_info = self.db.execute("SELECT clan_id FROM users WHERE user_id = %s", (user_id,), fetch='one')
        if not user_info or user_info['clan_id'] != clan_id:
            print(f"Пользователь {user_id} не состоит в клане {clan_id}.")
            return False

        valid_roles = ['member', 'deputy', 'leader', None] # None для удаления роли (но лучше remove_user_from_clan)
        if role not in valid_roles and role is not None:
             print(f"Недопустимая роль: {role}")
             return False

        if role is None: # Если хотят убрать роль - это равносильно удалению из клана
            return self.remove_user_from_clan(user_id)
        else:
            query = "UPDATE users SET clan_role = %s WHERE user_id = %s AND clan_id = %s"
            self.db.execute(query, (role, user_id, clan_id))
            return True

#clan_manager = ClanManager(db)


# --- bot\Classes\CommandManager.py ---
from typing import List, Tuple, Dict, Optional, Union
from bot.card_database import DatabaseManager, rarity_translate, DeckProfile

RARITY_EMOJIS = {
    "обычная": ["⚪", "обычная"],
    "редкая": "🩸",
    "эпическая": "🐉",
    "легендарная": "✨",
}


class CommandManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def format_user_team(self, user_id: int) -> List[tuple[str, str]]:
        team = self.get_user_deck(user_id)
        formatted_team = [('⚪️', 'Пусто')] * 5  # Позиции 1–5 => индексы 0–4

        if team:
            for card in team:
                pos = card.get("position")
                if pos is not None and 1 <= pos <= 5:
                    index = pos - 1
                    emoji = rarity_translate[card["rarity"]][:3]
                    name = card.get("name", "Без имени")
                    formatted_team[index] = (emoji, name)

        return formatted_team

    def get_user_deck(self, user_id: int) -> Optional[List[Dict]]:
        rows = self.db.execute(
            """
            SELECT c.*, ud.position 
            FROM cards c
            JOIN user_decks ud ON c.id = ud.card_id
            WHERE ud.user_id = %s
            ORDER BY ud.position;
            """,
            (user_id,),
            fetch='all'
        )
        if rows:

            return [dict(row) for row in rows]
        else:
            return None

    # Назначить карту на позицию (вставить или обновить)
    def assign_card_to_position(self, user_id: int, card_id: int, position: int):
        self.db.execute("""
            INSERT INTO user_decks (user_id, card_id, position)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, position) DO UPDATE SET card_id = EXCLUDED.card_id;
        """, (user_id, card_id, position))


    # Удалить карту с конкретной позиции у пользователя
    def remove_card_from_position(self, user_id: int, position: int):
        self.db.execute("""
            DELETE FROM user_decks
            WHERE user_id = %s AND position = %s;
        """, (user_id, position))

    # Посчитать суммарные характеристики команды
    def get_team_stats(self, user_id: int) -> Optional[DeckProfile]:
        row = self.db.execute("""
            SELECT 
                COALESCE(SUM(c.attack), 0) as total_attack,
                COALESCE(SUM(c.health), 0) as total_health,
                COALESCE(SUM(c.value), 0) as total_value
            FROM cards c
            JOIN user_decks ud ON c.id = ud.card_id
            WHERE ud.user_id = %s;
        """, (user_id,), fetch='one')
        if row:
            deck = DeckProfile(
                attack=row["total_attack"],
                health=row["total_health"],
                value=row["total_value"]
            )
            return deck
        else: return None


# --- bot\Classes\db_manager.py ---
# --- bot\Classes\db_manager.py ---
from bot.Classes.UserManager import UserManager
from bot.Classes.ClanManager import ClanManager
from bot.Classes.CardManager import CardManager
from bot.Classes.CommandManager import CommandManager # Assuming this is for deck/team commands
from bot.Classes.PromoManager import PromoManager
from bot.Classes.TaskManager import TaskManager
# Import CaseManager if you create it
# from bot.Classes.CaseManager import CaseManager

from bot.card_database import db # Import the single db instance

# Instantiate all managers using the shared db instance
user_manager = UserManager(db)
clan_manager = ClanManager(db)
card_manager = CardManager(db)
command_manager = CommandManager(db) # For deck management
promo_manager = PromoManager(db)
task_manager = TaskManager(db, user_manager) # TaskManager needs UserManager
# case_manager = CaseManager(db) # Instantiate if created

# You can optionally add a function to get all managers if needed elsewhere
# def get_managers():
#    return {
#        "user": user_manager,
#        "clan": clan_manager,
#        "card": card_manager,
#        "command": command_manager,
#        "promo": promo_manager,
#        "task": task_manager,
#        # "case": case_manager,
#    }


# --- bot\Classes\PromoManager.py ---
from typing import Optional, Tuple, Any, List, Dict

from bot.card_database import DatabaseManager, db
from bot.Classes.UserManager import UserManager
import random, string

import psycopg2
import psycopg2.extras # для DictCursor




class PromoManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.user_manager = UserManager(db_manager) # Для начисления монет

    def generate_promo_code(self, reward_amount: int, uses: int = 1, custom_code: Optional[str] = None) -> Optional[str]:
        """Генерирует новый промокод."""
        code = custom_code or ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        query = """
            INSERT INTO promo_achievements (code, reward_amount, uses_left)
            VALUES (%s, %s, %s);
        """
        try:
            # Используем execute базового класса, который обрабатывает ошибки
             result = self.db.execute(query, (code, reward_amount, uses))
             # Если execute вернул None и не было ошибки psycopg2, значит вставка прошла успешно
             # (хотя лучше бы он возвращал количество вставленных строк)
             # Мы не можем быть на 100% уверены без проверки существования кода до/после,
             # но для упрощения считаем, что если нет исключения - код создан.
             return code
        except psycopg2.errors.UniqueViolation:
             print(f"Промокод '{code}' уже существует.")
             return None
        except Exception as e: # Ловим другие возможные ошибки psycopg2
            print(f"Не удалось создать промокод '{code}': {e}")
            return None


    def check_promo_valid(self, user_id: int, code: str) -> Tuple[bool, Any]:
        """Проверяет валидность промокода для пользователя."""
        # 1. Найти активный промокод
        promo = self.db.execute(
            "SELECT * FROM promo_achievements WHERE code = %s AND uses_left > 0",
            (code,), fetch='one'
        )
        if not promo:
            return False, "Промокод недействителен или закончились использования."

        # 2. Проверить, не использовал ли пользователь его уже
        used = self.db.execute(
            "SELECT 1 FROM user_promos WHERE user_id = %s AND promo_id = %s",
            (user_id, promo['id']), fetch='one'
        )
        if used:
            return False, "Вы уже использовали этот промокод."

        return True, dict(promo) # Возвращаем информацию о промо

    def apply_promo_code(self, user_id: int, code: str) -> Tuple[bool, str]:
        """Применяет промокод к пользователю."""
        valid, result = self.check_promo_valid(user_id, code)
        if not valid:
            return False, result # result здесь - это сообщение об ошибке

        promo = result # result здесь - это информация о промо
        conn = self.db._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # 1. Отмечаем использование промокода пользователем
                cur.execute(
                    "INSERT INTO user_promos (user_id, promo_id) VALUES (%s, %s)",
                    (user_id, promo['id'])
                )
                # 2. Уменьшаем количество доступных использований промокода
                cur.execute(
                    "UPDATE promo_achievements SET uses_left = uses_left - 1 WHERE id = %s",
                    (promo['id'],)
                )
                # 3. Начисляем монеты пользователю
                cur.execute(
                    "UPDATE users SET coins = coins + %s WHERE user_id = %s",
                    (promo['reward_amount'], user_id)
                )
                conn.commit()
                return True, f"Промокод успешно применён! Вы получили {promo['reward_amount']} 🪙."

        except psycopg2.Error as e:
            conn.rollback()
            print(f"Ошибка применения промокода {code} для пользователя {user_id}: {e}")
            # Возможна ситуация гонки (race condition), если два запроса одновременно
            # прошли проверку check_promo_valid и пытаются применить код.
            # Уникальный индекс в user_promos (user_id, promo_id) предотвратит
            # двойное применение, вызвав здесь ошибку UniqueViolation.
            return False, "Не удалось применить промокод. Возможно, он был использован только что."

    def get_active_promos(self) -> List[Dict[str, Any]]:
        """Получает список активных промокодов."""
        query = "SELECT * FROM promo_achievements WHERE uses_left > 0 ORDER BY created_at DESC"
        promos = self.db.execute(query, fetch='all')
        return [dict(p) for p in promos] if promos else []

    def get_used_promos_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Получает список промокодов, использованных пользователем."""
        query = """
            SELECT p.*, up.used_at
            FROM promo_achievements p
            JOIN user_promos up ON up.promo_id = p.id
            WHERE up.user_id = %s
            ORDER BY up.used_at DESC;
        """
        promos = self.db.execute(query, (user_id,), fetch='all')
        return [dict(p) for p in promos] if promos else []

#promo_manager = PromoManager(db)


# --- bot\Classes\TaskManager.py ---
# task_manager.py

import datetime as dt
import random
from typing import List, Dict, Any, Optional, TYPE_CHECKING

quest_reward = f"📬🀄️ name, тебе начислено 5 осколков за выполнение ежедневного задания"

from bot.card_database import DatabaseManager
from bot.Classes.UserManager import UserManager
import psycopg2
import psycopg2.extras

class TaskManager:
    """
    Управляет ежедневными заданиями: генерацией общего набора на день,
    отслеживанием прогресса пользователей и выдачей наград.
    """
    TASKS_PER_DAY = 5 # Сколько заданий активно каждый день для ВСЕХ
    BONUS_REWARD_SHARDS = 10 # Бонусная награда за все задания

    def __init__(self, db_manager: 'DatabaseManager', user_manager: 'UserManager'):
        """
        Инициализирует TaskManager.
        :param db_manager: Экземпляр DatabaseManager для работы с БД.
        :param user_manager: Экземпляр UserManager для начисления осколков.
        """
        self.db = db_manager
        self.user_manager = user_manager

    def _generate_and_store_daily_tasks(self, date: dt.date) -> List[int]:
        """
        (Приватный) Выбирает случайные задания и сохраняет их ID для указанной даты.
        Вызывается, если задания на дату еще не сгенерированы.
        """
        print(f"Генерация набора ежедневных заданий на {date}...")
        # Выбираем N случайных ID из daily_tasks
        possible_tasks = self.db.execute(
            "SELECT id FROM daily_tasks ORDER BY RANDOM() LIMIT %s",
            (self.TASKS_PER_DAY,), fetch='all'
        )
        if not possible_tasks:
            print("Нет доступных заданий в daily_tasks для генерации!")
            return []

        task_ids = [task['id'] for task in possible_tasks]

        # Сохраняем набор в daily_active_tasks
        insert_query = "INSERT INTO daily_active_tasks (date, task_ids) VALUES (%s, %s) ON CONFLICT (date) DO NOTHING"
        self.db.execute(insert_query, (date, task_ids))

        print(f"Сгенерированы задания на {date}: {task_ids}")
        return task_ids

    def _get_active_task_ids_for_date(self, date: dt.date) -> List[int]:
        """
        (Приватный) Получает ID активных заданий на дату, генерирует при необходимости.
        """
        result = self.db.execute("SELECT task_ids FROM daily_active_tasks WHERE date = %s", (date,), fetch='one')
        if result and result['task_ids']: # Проверяем, что массив не пустой
            return result['task_ids']
        else:
            # Заданий на эту дату еще нет или массив пуст, генерируем
            return self._generate_and_store_daily_tasks(date)

    def get_user_tasks_for_display(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Получает ОБЩИЕ задания на сегодня и ИНДИВИДУАЛЬНЫЙ прогресс пользователя для отображения.
        """
        today = dt.date.today()
        active_task_ids = self._get_active_task_ids_for_date(today)

        if not active_task_ids:
            return []

        # Получаем детали этих активных заданий из daily_tasks
        tasks_details_list = self.db.execute(
            "SELECT id as task_id, description, task_type, target, rarity_condition, reward_shards FROM daily_tasks WHERE id = ANY(%s)",
            (active_task_ids,), fetch='all'
        )
        if not tasks_details_list:
             print(f"Не найдены детали для активных заданий {active_task_ids}")
             return []
        tasks_details_map = {task['task_id']: dict(task) for task in tasks_details_list}

        # Получаем прогресс пользователя по этим заданиям на сегодня
        user_progress_list = self.db.execute(
            """SELECT id, task_id, progress, completed, reward_claimed
               FROM user_daily_tasks
               WHERE user_id = %s AND date = %s AND task_id = ANY(%s)""",
            (user_id, today, active_task_ids), fetch='all'
        )
        user_progress_map = {prog['task_id']: dict(prog) for prog in user_progress_list} if user_progress_list else {}

        # Собираем итоговый список заданий с прогрессом
        display_tasks = []
        for task_id in active_task_ids:
            if task_id not in tasks_details_map: continue

            task_detail = tasks_details_map[task_id]
            user_progress = user_progress_map.get(task_id)

            display_task_data = {
                 **task_detail,
                 'id': user_progress['id'] if user_progress else None,
                 'progress': user_progress['progress'] if user_progress else 0,
                 'completed': user_progress['completed'] if user_progress else False,
                 'reward_claimed': user_progress['reward_claimed'] if user_progress else False,
                 'user_id': user_id,
                 'date': today,
             }
            display_tasks.append(display_task_data)

        # Сортируем результат так же, как task_ids были изначально
        display_tasks.sort(key=lambda t: active_task_ids.index(t['task_id']) if t['task_id'] in active_task_ids else float('inf'))
        return display_tasks

    def update_task_progress(self, user_id: int, event_type: str, amount: int = 1, rarity: Optional[str] = None):
        """
        Обновляет прогресс пользователя по АКТИВНЫМ на сегодня заданиям,
        создавая запись о прогрессе при необходимости.
        """
        today = dt.date.today()
        active_task_ids = self._get_active_task_ids_for_date(today)
        if not active_task_ids: return

        # Находим, какие из АКТИВНЫХ заданий соответствуют событию
        relevant_tasks_details = self.db.execute(
            """SELECT id as task_id, task_type, rarity_condition, target
               FROM daily_tasks
               WHERE id = ANY(%s)""",
            (active_task_ids,), fetch='all'
        )
        if not relevant_tasks_details: return

        matching_task_ids = []
        task_targets = {}
        for task in relevant_tasks_details:
            task_id = task['task_id']
            task_targets[task_id] = task['target']
            task_matches = False
            # Логика проверки соответствия события типу задания
            if event_type == 'GET_CARD':
                if task['task_type'] == 'GET_ANY_CARD': task_matches = True
                elif task['task_type'] == 'GET_RARITY_CARD' and task['rarity_condition'] == (rarity.lower() if rarity else None): task_matches = True # Сравниваем с lower()
            elif event_type == 'INVITE_FRIEND':
                if task['task_type'] == 'INVITE_FRIEND': task_matches = True
            # ... другие типы событий ...
            if task_matches: matching_task_ids.append(task_id)

        if not matching_task_ids: return

        # Обновляем прогресс атомарно
        conn = self.db._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                updated_tasks_data = []
                for task_id in matching_task_ids:
                    target = task_targets.get(task_id, 0)
                    if target == 0: continue

                    upsert_progress_query = """
                        INSERT INTO user_daily_tasks (user_id, task_id, date, progress, target)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, task_id, date) DO UPDATE SET
                            progress = LEAST(user_daily_tasks.progress + EXCLUDED.progress, user_daily_tasks.target)
                        WHERE user_daily_tasks.completed = FALSE -- Обновляем прогресс только у невыполненных
                        RETURNING user_daily_tasks.*,
                                  (SELECT dt.reward_shards FROM daily_tasks dt WHERE dt.id=user_daily_tasks.task_id) as reward_shards;
                    """
                    progress_to_add = amount
                    cur.execute(upsert_progress_query, (user_id, task_id, today, progress_to_add, target))
                    updated_row = cur.fetchone() # Получаем обновленную или только что вставленную строку
                    if updated_row:
                        updated_tasks_data.append(dict(updated_row))

                # Проверяем завершение для всех обновленных задач
                task_completed_in_this_run = False
                for task_data in updated_tasks_data:
                    if self._check_and_claim_completion(task_data, cur):
                        task_completed_in_this_run = True

                # Если что-то обновилось/завершилось, проверяем бонус
                if updated_tasks_data:
                    self._check_and_claim_bonus(user_id, today, cur)

                conn.commit()

        except psycopg2.Error as e:
            conn.rollback(); print(f"Ошибка psycopg2 при обновлении прогресса (общие задания) для {user_id}: {e}")
        except Exception as e:
            conn.rollback(); print(f"Неожиданная ошибка при обновлении прогресса (общие задания) для {user_id}: {e}")

    def _check_and_claim_completion(self, task_data: Dict[str, Any], cursor: 'psycopg2.extensions.cursor') -> bool:
        """(Приватный) Проверяет завершение, выдает награду, если нужно."""
        if task_data.get('completed') or task_data.get('reward_claimed'):
            return False # Уже завершено или награда получена

        if task_data.get('progress', 0) >= task_data.get('target', 1): # Проверка >= target
            task_data['completed'] = True # Обновляем локальный статус
            user_task_id = task_data['id']
            user_id = task_data['user_id']
            reward = task_data.get('reward_shards', 5)

            cursor.execute(
                "UPDATE user_daily_tasks SET completed = TRUE, reward_claimed = TRUE WHERE id = %s",
                (user_task_id,)
            )
            self.user_manager.add_shards(user_id, reward, cursor=cursor) # Используем user_manager
            print(f"Пользователь {user_id} выполнил задание #{task_data['task_id']}, получил {reward} осколков.")
            return True
        return False

    def _check_and_claim_bonus(self, user_id: int, date: dt.date, cursor: 'psycopg2.extensions.cursor'):
        """(Приватный) Проверяет, выполнены ли ВСЕ АКТИВНЫЕ задания дня, и выдает бонус."""
        cursor.execute("SELECT 1 FROM daily_bonus_claimed WHERE user_id = %s AND date = %s", (user_id, date))
        if cursor.fetchone(): return # Бонус уже выдан

        active_task_ids = self._get_active_task_ids_for_date(date) # Получаем ID активных заданий
        if not active_task_ids: return

        # Проверяем, все ли АКТИВНЫЕ задания выполнены пользователем
        query = """
            SELECT COUNT(*) FROM unnest(%s) AS active_task(id)
            LEFT JOIN user_daily_tasks udt ON active_task.id = udt.task_id AND udt.user_id = %s AND udt.date = %s
            WHERE udt.completed IS NULL OR udt.completed = FALSE;
        """
        cursor.execute(query, (active_task_ids, user_id, date))
        incomplete_count = cursor.fetchone()[0]

        if incomplete_count == 0:
             # Все АКТИВНЫЕ задания выполнены!
            self.user_manager.add_shards(user_id, self.BONUS_REWARD_SHARDS, cursor=cursor) # Используем user_manager
            cursor.execute(
                "INSERT INTO daily_bonus_claimed (user_id, date) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user_id, date)
            )

    def format_tasks_message(self, user_id: int, username: str) -> str:
        """Форматирует сообщение с заданиями для пользователя."""
        tasks = self.get_user_tasks_for_display(user_id)
        if not tasks:
            return f"🌙 {username}, похоже, на сегодня заданий нет."

        # (Код форматирования остается таким же, как в предыдущем ответе)
        # ... (копипаста кода из предыдущего ответа для форматирования строк) ...
        message_lines = [f"🌙 {username}, вот твои ежедневные задания на сегодня:\n"]
        all_completed = True
        for i, task in enumerate(tasks, 1):
            progress = task.get('progress', 0) # Используем .get для безопасности
            target = task.get('target', 1)
            description = task.get('description', 'Задание').replace('{target}', str(target))
            completed = task.get('completed', False)
            status_icon = "✅" if completed else "☁️"
            progress_text = f"{progress} из {target}" if not completed else f"{target} из {target}"
            message_lines.append(f"{i}️⃣ {description}")
            message_lines.append(f"{status_icon} Прогресс: {progress_text}")
            message_lines.append("➖➖➖➖➖")
            if not completed: all_completed = False

        bonus_claimed = self.db.execute("SELECT 1 FROM daily_bonus_claimed WHERE user_id = %s AND date = CURRENT_DATE", (user_id,), fetch='one')
        if all_completed and bonus_claimed: message_lines.append(f"🌠 Все задания выполнены! Бонус {self.BONUS_REWARD_SHARDS} 🀄️ уже начислен.")
        elif all_completed and not bonus_claimed: message_lines.append(f"🌠 Отлично! Все задания выполнены! Забирай бонус в {self.BONUS_REWARD_SHARDS} 🀄️ осколков!")
        else: message_lines.append(f"🌠 Выполни все задания и получи в награду {self.BONUS_REWARD_SHARDS} 🀄️ осколков")

        time_left = self.get_time_until_reset()
        hours, rem = divmod(time_left.total_seconds(), 3600); minutes, sec = divmod(rem, 60)
        time_left_str = f"{int(hours):02d}ч. {int(minutes):02d}м. {int(sec):02d}с."
        message_lines.append(f"\n🕒 До обновления: {time_left_str}")
        individual_reward = tasks[0].get('reward_shards', 5) if tasks else 5
        message_lines.append(f"📃 За каждое выполненное задание ты получишь награду {individual_reward} 🀄️ осколков")

        return "\n".join(message_lines)

    def get_time_until_reset(self) -> dt.timedelta:
         """Возвращает timedelta до следующей полуночи UTC."""
         # (Код остается тем же)
         now_utc = dt.datetime.now(dt.timezone.utc)
         midnight_utc = (now_utc + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
         return midnight_utc - now_utc


# --- bot\Classes\UserManager.py ---
# --- bot\Classes\UserManager.py ---
from typing import Optional, Tuple, Any, List, Dict
from redis.asyncio import Redis
import json
from datetime import timedelta, datetime

redis = Redis(host="localhost", port=6379, decode_responses=True)

from bot.card_database import DatabaseManager, UserProfile, db
import psycopg2
import psycopg2.extras # для DictCursor

class UserManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def register_user(self, user_id: int, username: Optional[str] = None) -> bool:
        """Регистрирует нового пользователя или обновляет его username."""
        query = """
            INSERT INTO users (user_id, username) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username;
        """
        # Execute returns rowcount for INSERT/UPDATE
        result = self.db.execute(query, (user_id, username))
        return result is not None # True if execution didn't fail

    def is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором."""
        query = "SELECT 1 FROM admins WHERE user_id = %s"
        result = self.db.execute(query, (user_id,), fetch='one')
        return result is not None

    def add_admin(self, user_id: int) -> bool:
        """Добавляет пользователя в администраторы."""
        # Ensure user exists first
        if not self.get_user_raw(user_id):
             print(f"Cannot add admin: User {user_id} not found in users table.")
             return False
        query = "INSERT INTO admins (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING"
        result = self.db.execute(query, (user_id,))
        return result == 1 # Returns 1 if inserted, 0 if conflict

    def remove_admin(self, user_id: int) -> bool:
        """Удаляет пользователя из администраторов."""
        query = "DELETE FROM admins WHERE user_id = %s"
        result = self.db.execute(query, (user_id,))
        return result == 1 # Returns 1 if deleted, 0 if not found

    def get_user_raw(self, user_id: int) -> Optional[dict]:
         """Получает сырые данные пользователя из БД."""
         query = "SELECT * FROM users WHERE user_id = %s"
         return self.db.execute(query, (user_id,), fetch='one')

    async def get_user_info(self, user_id: int) -> Optional[UserProfile]:
        """Получает полную информацию о профиле пользователя."""
        # Consider adding caching logic here if needed (e.g., Redis)
        # cached = await redis.hgetall(f"user:{user_id}:profile")
        # if cached: ...

        query = """
            SELECT
                u.*,
                c.name as clan_name,
                (SELECT COUNT(DISTINCT card_id) FROM user_cards WHERE user_id = u.user_id) as cards_owned_count,
                (SELECT COUNT(*) FROM cards) as total_cards_in_game
            FROM users u
            LEFT JOIN clans c ON u.clan_id = c.id
            WHERE u.user_id = %s;
        """
        user_row = self.db.execute(query, (user_id,), fetch='one')

        if user_row is None:
            # Optional: register if not found? Depends on your flow.
            # self.register_user(user_id)
            # user_row = self.db.execute(query, (user_id,), fetch='one')
            # if user_row is None: return None
            return None
        if user_row['is_banned']: # Return None or a specific indicator for banned users
            print(f"User {user_id} is banned. Access denied.") # Log this
            # Decide how to handle banned users in profiles. Return None?
            # Or return profile with a flag? Let's return None for simplicity now.
            return None


        profile = UserProfile(
            nickname=user_row["username"] or f"User_{user_id}",
            total_cards_received=user_row["total_cards_received"],
            cards_owned=user_row["cards_owned_count"],
            total_cards_in_game=user_row["total_cards_in_game"],
            season_points=user_row["season_rating"], # Changed from rating to season_rating
            has_battle_pass=user_row["has_battle_pass"],
            season_wins=user_row["season_wins"],
            season_losses=user_row["season_losses"],
            all_wins=user_row["all_wins"],
            all_losses=user_row["all_losses"],
            free_spins=user_row["free_spins"],
            coins=user_row["coins"],
            shards=user_row["shards"],
            shards_rare=user_row["shards_rare"],
            shards_epic=user_row["shards_epic"],
            shards_legendary=user_row["shards_legendary"],
            is_banned=user_row["is_banned"], # <-- Added
            clan_name=user_row["clan_name"],
            clan_role=user_row["clan_role"]
        )

        # Add caching logic if needed
        # await redis.hset(f"user:{user_id}:profile", mapping={...})

        return profile

    def update_username(self, user_id: int, new_username: str):
        query = "UPDATE users SET username = %s WHERE user_id = %s"
        self.db.execute(query, (new_username, user_id))

    def update_rating(self, user_id: int, delta_rating: int):
        """Изменяет общий рейтинг пользователя на указанную дельту."""
        query = "UPDATE users SET rating = rating + %s WHERE user_id = %s"
        self.db.execute(query, (delta_rating, user_id))

    def update_season_rating(self, user_id: int, delta_rating: int):
        """Изменяет сезонный рейтинг пользователя на указанную дельту."""
        query = "UPDATE users SET season_rating = season_rating + %s WHERE user_id = %s"
        self.db.execute(query, (delta_rating, user_id))

    def set_battle_pass(self, user_id: int, has_pass: bool):
        query = "UPDATE users SET has_battle_pass = %s WHERE user_id = %s"
        self.db.execute(query, (has_pass, user_id))

    def set_referrer(self, user_id: int, referrer_id: int):
        """Устанавливает реферера для пользователя."""
        query = "UPDATE users SET referrer_id = %s WHERE user_id = %s AND referrer_id IS NULL"
        self.db.execute(query, (referrer_id, user_id))

    def add_referral(self, user_id: int):
        query = "UPDATE users SET referrals = referrals + 1 WHERE user_id = %s"
        self.db.execute(query, (user_id,))

    def add_coins(self, user_id: int, amount: int):
        """Добавляет монеты пользователю."""
        if amount <= 0: return # Не добавляем 0 или отрицательное число
        query = "UPDATE users SET coins = coins + %s WHERE user_id = %s"
        self.db.execute(query, (amount, user_id))

    def get_coins(self, user_id: int) -> int:
        """Получает текущий баланс монет пользователя."""
        query = "SELECT coins FROM users WHERE user_id = %s"
        result = self.db.execute(query, (user_id,), fetch='one')
        return result['coins'] if result else 0

    def spend_coins(self, user_id: int, amount: int) -> bool:
        """Пытается потратить монеты пользователя. Возвращает True при успехе."""
        if amount <= 0: return False # Нельзя потратить 0 или отрицательное число

        # Update with balance check in WHERE clause for atomicity without explicit transaction
        query = "UPDATE users SET coins = coins - %s WHERE user_id = %s AND coins >= %s"
        rows_affected = self.db.execute(query, (amount, user_id, amount))
        return rows_affected == 1 # True if 1 row was updated

    def get_total_cards_received(self, user_id: int) -> int:
        """
        Возвращает общее количество карт (включая дубликаты),
        полученных пользователем за все время.
        """
        query = "SELECT total_cards_received FROM users WHERE user_id = %s"
        result = self.db.execute(query, (user_id,), fetch='one')
        # Возвращаем значение счетчика или 0, если пользователь не найден
        return result['total_cards_received'] if result else 0

    def get_last_card_time(self, user_id: int) -> Optional[datetime]:
        """Получает время последнего получения карты."""
        query = "SELECT last_card_received FROM users WHERE user_id = %s"
        result = self.db.execute(query, (user_id,), fetch='one')
        return result['last_card_received'] if result and result['last_card_received'] else None

    def update_last_card_time(self, user_id: int, time: datetime):
        """Обновляет время последнего получения карты."""
        query = "UPDATE users SET last_card_received = %s WHERE user_id = %s"
        self.db.execute(query, (time, user_id))

    def add_shards(self, user_id: int, amount: int, cursor: Optional['psycopg2.extensions.cursor'] = None) -> bool:
        """Добавляет осколки пользователю. Можно передать курсор для использования в транзакции."""
        if amount <= 0: return False
        query = "UPDATE users SET shards = shards + %s WHERE user_id = %s"
        try:
            if cursor:
                cursor.execute(query, (amount, user_id))
                return True # Success assumed if no exception in transaction
            else:
                result = self.db.execute(query, (amount, user_id))
                return result is not None # True if execution didn't fail
        except Exception as e:
            print(f"Ошибка при добавлении {amount} осколков пользователю {user_id}: {e}")
            return False

    def get_shards(self, user_id: int) -> int:
        """Получает баланс осколков пользователя."""
        query = "SELECT shards FROM users WHERE user_id = %s"
        result = self.db.execute(query, (user_id,), fetch='one')
        return result['shards'] if result else 0

    def spend_shards(self, user_id: int, amount: int, cursor: Optional['psycopg2.extensions.cursor'] = None) -> bool:
        """Пытается потратить осколки пользователя. Можно передать курсор для использования в транзакции."""
        if amount <= 0: return False

        try:
            if cursor:
                # Check balance within the transaction
                cursor.execute("SELECT shards FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
                row = cursor.fetchone()
                if not row or row[0] < amount:
                    return False # Not enough shards
                # Spend shards
                cursor.execute("UPDATE users SET shards = shards - %s WHERE user_id = %s", (amount, user_id))
                return True # Success assumed if no exception
            else:
                # Without cursor - use atomic update
                query = "UPDATE users SET shards = shards - %s WHERE user_id = %s AND shards >= %s"
                rows_affected = self.db.execute(query, (amount, user_id, amount))
                return rows_affected == 1 # True if 1 row was updated
        except Exception as e:
            print(f"Ошибка при попытке потратить {amount} осколков у пользователя {user_id}: {e}")
            # Important: Don't rollback here if using an external cursor/transaction
            return False

    def ban_user(self, user_id: int) -> bool:
        """Банит пользователя."""
        query = "UPDATE users SET is_banned = TRUE WHERE user_id = %s"
        result = self.db.execute(query, (user_id,))
        return result == 1 # 1 row updated

    def unban_user(self, user_id: int) -> bool:
        """Разбанивает пользователя."""
        query = "UPDATE users SET is_banned = FALSE WHERE user_id = %s"
        result = self.db.execute(query, (user_id,))
        return result == 1 # 1 row updated

    def reset_user_account(self, user_id: int) -> bool:
        """Сбрасывает данные аккаунта пользователя (ОСТОРОЖНО!)."""
        conn = self.db._get_connection()
        try:
            with conn.cursor() as cur:
                # Delete related data
                cur.execute("DELETE FROM user_cards WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM user_decks WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM user_promos WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM user_daily_tasks WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM daily_bonus_claimed WHERE user_id = %s", (user_id,))

                # Reset fields in users table to defaults
                cur.execute("""
                    UPDATE users
                    SET
                        clan_id = NULL,
                        clan_role = NULL,
                        has_battle_pass = FALSE,
                        rating = 0,
                        season_rating = 0,
                        coins = 0,
                        last_card_received = NULL,
                        referrals = 0,
                        -- referrer_id = NULL, -- Keep referrer? Optional.
                        total_cards_received = 0,
                        free_spins = 0,
                        shards_rare = 0,
                        shards_epic = 0,
                        shards_legendary = 0,
                        season_wins = 0,
                        season_losses = 0,
                        all_wins = 0,
                        all_losses = 0,
                        total_duplicates_received = 0,
                        shards = 0,
                        is_banned = FALSE -- Unban on reset? Or keep ban status? Let's unban.
                    WHERE user_id = %s;
                """, (user_id,))
            conn.commit()
            return True
        except psycopg2.Error as e:
            conn.rollback()
            print(f"Ошибка при сбросе аккаунта пользователя {user_id}: {e}")
            return False

    def get_all_user_ids(self, include_banned=False) -> List[int]:
        """Получает список ID всех пользователей."""
        query = "SELECT user_id FROM users"
        if not include_banned:
            query += " WHERE is_banned = FALSE"
        results = self.db.execute(query, fetch='all')
        return [row['user_id'] for row in results] if results else []

    # --- Statistics Methods ---
    def get_total_user_count(self) -> int:
        query = "SELECT COUNT(*) FROM users"
        result = self.db.execute(query, fetch='one')
        return result['count'] if result else 0

    def get_total_cards_given_out(self) -> int:
        # 'total_cards_received' seems the best metric available
        query = "SELECT SUM(total_cards_received) as total FROM users"
        result = self.db.execute(query, fetch='one')
        return result['total'] if result and result['total'] is not None else 0

    def get_battle_pass_count(self) -> int:
        query = "SELECT COUNT(*) FROM users WHERE has_battle_pass = TRUE"
        result = self.db.execute(query, fetch='one')
        return result['count'] if result else 0

    def get_total_coins_in_system(self) -> int:
        query = "SELECT SUM(coins) as total FROM users"
        result = self.db.execute(query, fetch='one')
        return result['total'] if result and result['total'] is not None else 0

    # --- Ranking Methods (Keep existing ones) ---
    def get_top_users_by_season(self, limit=10):
        # ... (keep existing implementation) ...
        return self.db.execute(
            """
            SELECT user_id, username, season_rating
            FROM users WHERE is_banned = FALSE
            ORDER BY season_rating DESC
            LIMIT %s;
            """,
            (limit,),
            fetch='all'
        )


    def get_user_season_rank(self, user_id):
        # ... (keep existing implementation) ...
        result = self.db.execute( # Check if user exists and is not banned first
            "SELECT season_rating FROM users WHERE user_id = %s AND is_banned = FALSE",
            (user_id,),
            fetch='one'
        )
        if not result: return None # User not found or banned

        return self.db.execute(
            """
            SELECT COUNT(*) + 1 as rank
            FROM users
            WHERE season_rating > (SELECT season_rating FROM users WHERE user_id = %s)
              AND is_banned = FALSE;
            """,
            (user_id,),
            fetch='one'
        )['rank']


    def get_top_users_alltime(self, limit=10):
        # ... (keep existing implementation) ...
        return self.db.execute(
            """
            SELECT user_id, username, rating
            FROM users WHERE is_banned = FALSE
            ORDER BY rating DESC
            LIMIT %s;
            """,
            (limit,),
            fetch='all'
        )

    def get_user_alltime_rank(self, user_id):
        # ... (keep existing implementation) ...
        result = self.db.execute( # Check if user exists and is not banned first
            "SELECT rating FROM users WHERE user_id = %s AND is_banned = FALSE",
            (user_id,),
            fetch='one'
        )
        if not result: return None # User not found or banned

        return self.db.execute(
            """
            SELECT COUNT(*) + 1 as rank
            FROM users
            WHERE rating > (SELECT rating FROM users WHERE user_id = %s)
              AND is_banned = FALSE;
            """,
            (user_id,),
            fetch='one'
        )['rank']

#user_manager = UserManager(db) # Keep this commented out here, instantiate in db_manager.py


# --- bot\dev\card_generator.py ---
import random
from faker import Faker

from bot.Classes.db_manager import card_manager
from bot.card_database import RARITY_WEIGHTS

fake = Faker()

PHOTO_IDS = [
    'AgACAgIAAxkBAAMNaAVO23_cGAwozoEi02KkZbGve1UAAsz4MRsg1ihIgCpP6-dH3pEBAAMCAAN5AAM2BA',
'AgACAgIAAxkBAAMPaAVO27Z3BbiFAAHfvIR3ObYWSm-tAALN-DEbINYoSDacvAzZ6sASAQADAgADeQADNgQ',
'AgACAgIAAxkBAAMRaAVO3HLnKnqFLcQPVuNpwZDFgPwAAs74MRsg1ihIReh5UoXJDY4BAAMCAAN5AAM2BA',
'AgACAgIAAxkBAAMTaAVO3LMAAao9j5B-iar9iGuKifzEAALP-DEbINYoSN8_EHVRblM0AQADAgADeQADNgQ',
'AgACAgIAAxkBAAMVaAVO3HUAAQtLrzxE34yReiiS6oiBAALQ-DEbINYoSNyjUm5GWY_DAQADAgADeQADNgQ',
'AgACAgIAAxkBAAMXaAVO30uZypCZUOOQxyfp1toCs5UAAtH4MRsg1ihIiLRC_BFikZEBAAMCAAN5AAM2BA',
'AgACAgIAAxkBAAMZaAVO4u6RA1a_MquPr-ET1m4UMwoAAtL4MRsg1ihI1sePi9abWZMBAAMCAAN5AAM2BA',
'AgACAgIAAxkBAAMbaAVO4ixZ5M8i7tUxikrHaIycjZ4AAtP4MRsg1ihIr7pr2mN5Jv8BAAMCAAN5AAM2BA',
'AgACAgIAAxkBAAMdaAVO4tFg5VRBQ3_WHvPyRFiJxJ0AAtT4MRsg1ihIzNnjAnQNPHMBAAMCAAN5AAM2BA',
'AgACAgIAAxkBAAMfaAVO5DSLaiu7YIqS7fguOqkORnoAAtX4MRsg1ihIqS3fbTQ7aDUBAAMCAAN5AAM2BA',
'AgACAgIAAxkBAAMhaAVPDXsNjYPEaUM7vcrIDYw8q-4AAt74MRsg1ihIHYbT41N-ge8BAAMCAAN5AAM2BA',
'AgACAgIAAxkBAAMjaAVPDuxrYxKx2-SpwDUyl69JIIQAAt_4MRsg1ihIHw3RIoG-0d8BAAMCAAN5AAM2BA'

]

def weighted_rarity():
    names = list(RARITY_WEIGHTS.keys())
    weights = list(RARITY_WEIGHTS.values())
    return random.choices(names, weights=weights, k=1)[0]

def generate_random_cards(amount):
    for _ in range(amount):

        name = fake.first_name() + " " + fake.last_name()
        rarity = weighted_rarity()

        base_attack = random.randint(500, 1500)
        base_health = random.randint(2000, 6000)
        multiplier = {
            "common": 1,
            "rare": 3,
            "epic": 5,
            "legendary": 8,
            "mythical": 15
        }.get(rarity, 1)

        attack = int(base_attack * multiplier)
        health = int(base_health * multiplier)
        value = int((attack + health) / 2)

        photo_id = random.choice(PHOTO_IDS)

        card_manager.add_card(name=name, rarity=rarity, attack=attack, health=health, value=value, image_path=photo_id)

if __name__ == "__main__":
    generate_random_cards(20)  # Пример: сгенерировать 20 карт


# --- bot\dev\dev.py ---
from aiogram import F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram import Router

from bot.Classes.db_manager import user_manager, card_manager, db
from bot.dev.card_generator import generate_random_cards
from bot.dev.task_utils import generate_task_variations

router = Router()


@router.message(F.text.startswith("/get_all"))
async def cmd_generate(message: Message):
    print(card_manager.get_all_cards())

@router.message(F.text == "/quest_generate")
async def questing(message: Message):
    generate_task_variations(db_manager=db, clear_existing=True)

@router.message(F.text.startswith("/generate"))
async def cmd_generate(message: Message):
    try:
        amount = message.text.split()[1]
        generate_random_cards(int(amount))
        await message.answer(f"✅ Успешно сгенерировано {amount} случайных карт!")
    except (ValueError, TypeError) as e:
        await message.answer("❌ Пожалуйста, укажи количество карт. Пример: /generate 30" + str(e))

@router.message(F.text.startswith("/give_bp"))
async def reset_last_time(message: Message):
    print(db.execute("UPDATE users SET has_battle_pass = TRUE WHERE user_id = %s", (message.from_user.id,)))
    await message.answer("Боевой пропуск выдан успешно")

@router.message(F.text.startswith("/discard_bp"))
async def reset_last_time(message: Message):
    print(db.execute("UPDATE users SET has_battle_pass = FALSE WHERE user_id = %s", (message.from_user.id,)))
    await message.answer("Боевой пропуск аннулирован")

@router.message(F.text.startswith("/drop_bd"))
async def reset_last_time(message: Message):
    await message.answer(db.drop_all_tables())

@router.message(F.text.startswith("/reset"))
async def reset_last_time(message: Message):
    card_manager.reset_last_received_time(message.from_user.id)
    await message.answer("time reset")

@router.message(F.text.startswith("/get_cards"))
async def reset_last_time(message: Message):
    if int(message.text[10:])> 100:
        await message.answer(f"Да вы ахуели сударь")
        return
    for i in range(0, int(message.text[10:])):
        card = card_manager.get_random_card(user_id=message.from_user.id, exclude_received=True)
        if card:
            card_manager.give_card_to_user(message.from_user.id, card['id'], card["rarity"])

    await message.answer(f"Отдал кровные {message.text[10:]} карт")


@router.message(Command("add"))
async def handle_add_poti_coins(message: Message):
    args = message.text.strip().split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("❌ Использование: /add <сумма>")
        return

    amount = int(args[1])
    user_id = message.from_user.id

    user_manager.add_coins(user_id, amount)
    new_balance = user_manager.get_coins(user_id)

    await message.answer(f"✅ {amount} PoTi Coin добавлено!\n💰 Новый баланс: {new_balance}")



# --- bot\dev\streess_bd.py ---
import asyncio
from flask import Flask, request, jsonify
from bot.main import bot, dp
from pydantic import BaseModel, ValidationError
import threading

app = Flask(__name__)

class User(BaseModel):
    id: int
    is_bot: bool
    first_name: str
    username: str

class Chat(BaseModel):
    id: int
    first_name: str
    type: str

class Message(BaseModel):
    message_id: int
    from_user: User
    chat: Chat
    date: int
    text: str

class Update(BaseModel):
    update_id: int
    message: Message

# Flask эндпоинт для получения обновлений
@app.route('/test-bot', methods=['POST'])
def test_bot():
    try:
        # Получаем данные из POST-запроса
        data = request.get_json()

        # Пытаемся преобразовать данные в объект Update
        update = Update(**data)

        # Обработка данных с помощью бота
        print(f"Received message: {update.message.text} from {update.message.from_user.username}")

        # Здесь можно добавить логику для взаимодействия с ботом, если необходимо.

        return jsonify({"status": "success", "message": "Data processed successfully"}), 200

    except ValidationError as e:
        # Обрабатываем ошибки валидации
        return jsonify({"status": "error", "message": "Invalid data", "details": e.errors()}), 400
    except Exception as e:
        # Общая ошибка
        return jsonify({"status": "error", "message": str(e)}), 500

# Функция для запуска Flask в отдельном потоке
def run_flask():
    app.run(debug=True, use_reloader=False)  # use_reloader=False для предотвращения второго запуска

# Функция для запуска бота
async def start_bot():
    await dp.start_polling(bot)

# Основная функция для запуска обоих процессов
def run():
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Запускаем Telegram-бота с использованием asyncio.run
    asyncio.run(start_bot())

if __name__ == '__main__':
    run()



# --- bot\dev\task_utils.py ---
# task_utils.py (или другой подходящий файл)

import random
from typing import List, Dict, Any, Optional, Tuple

from bot.card_database import DatabaseManager

# --- Настройки для генерации ---

# Варианты целей для разных типов заданий
TARGETS_INVITE = [1, 3, 5]
TARGETS_GET_ANY = [3, 5, 7, 10]
TARGETS_GET_RARITY = {
    'common': [3, 5, 7, 10],
    'rare': [2, 3, 5],
    'epic': [1, 2, 3],
    'legendary': [1, 2],
    'mythical': [1]
}

# Список редкостей
RARITIES = ['common', 'rare', 'epic', 'legendary', 'mythical']

# Базовые награды и бонусы (можно настроить)
REWARD_BASE = {
    'INVITE_FRIEND': 5,
    'GET_ANY_CARD': 3,
    'GET_RARITY_CARD': {
        'common': 5,
        'rare': 7,
        'epic': 10,
        'legendary': 15,
        'mythical': 20,
    }
}
REWARD_PER_TARGET_MULTIPLIER = {
    'INVITE_FRIEND': 1,
    'GET_ANY_CARD': 1,
    'GET_RARITY_CARD': {
        'common': 1,
        'rare': 1.5,
        'epic': 2,
        'legendary': 3,
        'mythical': 4,
    }
}

# Шаблоны описаний
DESCRIPTIONS = {
    'INVITE_FRIEND': "Пригласи {target} друзей по реферальной ссылке",
    'GET_ANY_CARD': "Получи {target} любые карты",
    'GET_RARITY_CARD': "Получи {target} {rarity_adj} карты" # Используем прилагательные
}

# Прилагательные для редкостей в нужном падеже
RARITY_ADJECTIVES = {
    'common': 'обычные',
    'rare': 'редкие',
    'epic': 'эпические',
    'legendary': 'легендарные',
    'mythical': 'мифические'
}

def generate_task_variations(db_manager: 'DatabaseManager', clear_existing: bool = False):
    """
    Генерирует и добавляет в БД различные вариации ежедневных заданий.

    :param db_manager: Экземпляр DatabaseManager для доступа к БД.
    :param clear_existing: Если True, сначала удалит ВСЕ существующие задания из daily_tasks.
                           Используй с осторожностью!
    """
    if clear_existing:
        print("ВНИМАНИЕ: Удаление всех существующих заданий из daily_tasks...")
        try:
            # Безопаснее использовать TRUNCATE с CASCADE, если есть FK, или DELETE
            # db_manager.execute("TRUNCATE TABLE daily_tasks RESTART IDENTITY CASCADE;") # Опасно, если есть FK в user_daily_tasks без ON DELETE CASCADE
            db_manager.execute("DELETE FROM daily_tasks;") # Безопаснее, но медленнее на больших таблицах
            print("Существующие задания удалены.")
        except Exception as e:
            print(f"Ошибка при удалении существующих заданий: {e}")
            return

    print("Генерация вариаций ежедневных заданий...")
    tasks_to_insert = []
    existing_tasks_check = set() # Для проверки дубликатов (task_type, target, rarity)

    # --- Получаем существующие задания для проверки дублей (если не очищали) ---
    if not clear_existing:
         existing_rows = db_manager.execute("SELECT task_type, target, rarity_condition FROM daily_tasks", fetch='all')
         if existing_rows:
              for row in existing_rows:
                   key = (row['task_type'], row['target'], row.get('rarity_condition')) # Используем .get для NULL
                   existing_tasks_check.add(key)
         print(f"Найдено {len(existing_tasks_check)} существующих комбинаций заданий.")


    # --- Генерация заданий типа INVITE_FRIEND ---
    task_type = 'INVITE_FRIEND'
    for target in TARGETS_INVITE:
        key = (task_type, target, None)
        if key in existing_tasks_check: continue # Пропускаем дубль

        reward = REWARD_BASE[task_type] + int(target * REWARD_PER_TARGET_MULTIPLIER[task_type])
        description = DESCRIPTIONS[task_type].format(target=target)
        tasks_to_insert.append((description, task_type, target, None, reward))
        existing_tasks_check.add(key) # Добавляем в проверку

    # --- Генерация заданий типа GET_ANY_CARD ---
    task_type = 'GET_ANY_CARD'
    for target in TARGETS_GET_ANY:
        key = (task_type, target, None)
        if key in existing_tasks_check: continue

        reward = REWARD_BASE[task_type] + int(target * REWARD_PER_TARGET_MULTIPLIER[task_type])
        description = DESCRIPTIONS[task_type].format(target=target)
        tasks_to_insert.append((description, task_type, target, None, reward))
        existing_tasks_check.add(key)

    # --- Генерация заданий типа GET_RARITY_CARD ---
    task_type = 'GET_RARITY_CARD'
    for rarity in RARITIES:
        targets = TARGETS_GET_RARITY.get(rarity, [1]) # Получаем цели для редкости
        rarity_adj = RARITY_ADJECTIVES.get(rarity, rarity) # Получаем прилагательное

        for target in targets:
            key = (task_type, target, rarity)
            if key in existing_tasks_check: continue

            base_reward = REWARD_BASE[task_type].get(rarity, 5)
            multiplier = REWARD_PER_TARGET_MULTIPLIER[task_type].get(rarity, 1)
            reward = base_reward + int(target * multiplier)
            description = DESCRIPTIONS[task_type].format(target=target, rarity_adj=rarity_adj)
            tasks_to_insert.append((description, task_type, target, rarity, reward))
            existing_tasks_check.add(key)

    # --- Вставка сгенерированных заданий в БД ---
    if not tasks_to_insert:
        print("Нет новых вариаций заданий для добавления.")
        return

    print(f"Подготовлено {len(tasks_to_insert)} новых вариаций заданий для вставки...")
    conn = db_manager._get_connection()
    inserted_count = 0
    try:
        with conn.cursor() as cur:
            insert_query = """
                INSERT INTO daily_tasks (description, task_type, target, rarity_condition, reward_shards)
                VALUES (%s, %s, %s, %s, %s);
            """
            # Используем execute_batch для эффективности, если заданий много
            # psycopg2.extras.execute_batch(cur, insert_query, tasks_to_insert)
            # Или просто циклом для большей совместимости и контроля
            for task_data in tasks_to_insert:
                try:
                    cur.execute(insert_query, task_data)
                    inserted_count += 1
                except Exception as item_error:
                     # Логируем ошибку конкретного задания, но продолжаем другие
                     print(f"Ошибка при вставке задания {task_data}: {item_error}")
                     conn.rollback() # Откатываем вставку этого задания
                     conn.commit() # Начинаем новую мини-транзакцию для следующего
            conn.commit() # Коммитим последнюю успешную вставку (или пустую транзакцию)
        print(f"Успешно добавлено {inserted_count} новых вариаций заданий.")
    except Exception as e:
        conn.rollback() # Откатываем всю транзакцию в случае общей ошибки
        print(f"Ошибка при массовой вставке заданий: {e}")


# --- Пример использования ---
if __name__ == '__main__':

    # --- Конфигурация DSN ---
    DB_NAME = "postgres"
    DB_USER = "postgres"
    DB_PASSWORD = ""
    DB_HOST = "localhost"
    DB_PORT = "5432"
    DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    db_manager = None
    try:
        db_manager = DatabaseManager(DSN)

        # Вызываем функцию генерации
        # clear_existing=True удалит старые задания перед генерацией! Будь осторожен!
        generate_task_variations(db_manager, clear_existing=False)

        # Проверим, что задания добавились (опционально)
        all_tasks = db_manager.execute("SELECT * FROM daily_tasks ORDER BY id", fetch='all')
        if all_tasks:
            print(f"\n--- Текущие задания в БД ({len(all_tasks)} шт.) ---")
            for task in all_tasks[:10]: # Показать первые 10
                print(f"  ID: {task['id']}, Тип: {task['task_type']}, Цель: {task['target']}, Редкость: {task.get('rarity_condition', 'N/A')}, Награда: {task['reward_shards']}, Описание: {task['description']}")
            if len(all_tasks) > 10: print("  ...")
        else:
            print("\nВ таблице daily_tasks нет заданий.")


    except Exception as e:
        print(f"Ошибка при выполнении скрипта генерации: {e}")
    finally:
        if db_manager:
            db_manager.close()


# --- bot\handlers\admin_handlers.py ---
# --- bot\handlers\admin_handlers.py ---
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


# --- bot\handlers\arena.py ---
from collections import deque
import asyncio
from random import choice

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import StatesGroup, State

from bot.Classes.CommandManager import RARITY_EMOJIS
from bot.card_database import rarity_translate
from bot.common import bot
from aiogram.fsm.storage.base import StorageKey

from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram import Router

from bot.handlers.mainMenu import back_button, create_back_button
from bot.Classes.db_manager import task_manager, user_manager, command_manager, card_manager

arena_handler = Router()


class BattleState(StatesGroup):
    InBattle = State()

BATTLE_REWARD_SHARDS = 10

CARDS_PER_PAGE = 4


matchmaking_queue = deque()
matchmaking_lock = asyncio.Lock()
# Словарь для хранения сообщений "Ожидание..." для возможности их удаления/изменения
waiting_messages = {}

@arena_handler.callback_query(F.data == "find_opponent")
async def find_opponent_callback(callback: CallbackQuery, state: FSMContext): # Добавь нужные менеджеры
    user_id = callback.from_user.id
    user_name = callback.from_user.username

    await callback.answer("Ищем соперника...") # Ответ на нажатие кнопки

    async with matchmaking_lock:
        if user_id in [u_id for u_id, u_name, _ in matchmaking_queue]:
             await callback.message.edit_text("Вы уже в очереди!") # Редактируем исходное сообщение
             return

        if matchmaking_queue:
            # --- Найден соперник ---
            opponent_id, opponent_name, opponent_chat_id = matchmaking_queue.popleft() # Берем первого из очереди

            # Удаляем сообщения об ожидании, если они были
            if opponent_id in waiting_messages:
                try:
                    await bot.delete_message(chat_id=opponent_id, message_id=waiting_messages.pop(opponent_id))
                except Exception as e: print(f"Не удалось удалить сообщение ожидания для {opponent_id}: {e}")
            if user_id in waiting_messages: # На случай, если пользователь нажал дважды быстро
                try:
                    await bot.delete_message(chat_id=user_id, message_id=waiting_messages.pop(user_id))
                except Exception as e: print(f"Не удалось удалить сообщение ожидания для {user_id}: {e}")


            # Сообщаем об успехе (можно убрать или изменить)
            # await callback.message.edit_text(f"Найден соперник: {opponent_name}!") # Редактируем сообщение нажавшего
            # await bot.send_message(opponent_id, f"Найден соперник: {user_name}!") # Отправляем другому
            await callback.message.answer("⏳ Поиск соперника... Ожидайте.")

            await start_battle(user_id, opponent_id, callback.message.chat.id, opponent_chat_id, user_name, opponent_name, state)

        else:
            # --- Добавляем в очередь ---
            matchmaking_queue.append((user_id, user_name, callback.message.chat.id))
            # Сохраняем ID сообщения для возможности его удаления
            msg = await callback.message.answer("⏳ Поиск соперника... Ожидайте.", reply_markup=create_back_button("cancel_match"))
            waiting_messages[user_id] = msg.message_id
            print(f"User {user_id} ({user_name}) added to matchmaking queue.")

async def start_battle(user_id, opponent_id, user_chat_id, opponent_chat_id, user_name, opponent_name, state):
    # TODO: Доделать собственно
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔ Атаковать", callback_data="battle_attack"),
            InlineKeyboardButton(text="▶️ Пропустить", callback_data="battle_skip")
        ]
    ])
    
    p1_key = StorageKey(bot_id=bot.id, chat_id=user_chat_id, user_id=user_id)
    p2_key = StorageKey(bot_id=bot.id, chat_id=opponent_chat_id, user_id=opponent_id)
    
    user_data = command_manager.get_team_stats(user_id)
    opponent_data = command_manager.get_team_stats(opponent_id)

    p1_wins_instantly = user_data.attack >= opponent_data.health
    p2_wins_instantly = opponent_data.attack >= user_data.health

    if p1_wins_instantly and p2_wins_instantly:
        # Ничья или кто первый ударил? Для простоты - ничья, без наград/статистики
        await bot.send_message(user_id, f"⚔️ Битва с {opponent_name}!\nМгновенная ничья! Оба игрока слишком сильны!")
        await bot.send_message(opponent_id, f"⚔️ Битва с {user_name}!\nМгновенная ничья! Оба игрока слишком сильны!")
        return  # Завершаем без статистики
    elif p1_wins_instantly:
        battle_data = {  # Данные для сообщения о результате
            "p1_id": user_id, "p2_id": opponent_id, "p1_name": user_name, "p2_name": opponent_name,
            "p1_atk": user_data.attack, "p2_atk": opponent_data.attack, "initial_p1_hp": user_data.health, "initial_p2_hp": opponent_data.health,
            "final_p1_hp": user_data.health, "final_p2_hp": 0,  # Проигравший на 0 хп
            "damage_dealt_by_winner": user_data.attack, "damage_dealt_by_loser": 0, "rounds": 1
        }
        await end_battle(user_id, opponent_id, state, p1_key, p2_key, battle_data)  # user_manager нужен для наград
        return
    elif p2_wins_instantly:
        battle_data = {
            "p1_id": user_id, "p2_id": opponent_id, "p1_name": user_name, "p2_name": opponent_name,
            "p1_atk": user_data.attack, "p2_atk": opponent_data.attack, "initial_p1_hp": user_data.health, "initial_p2_hp": opponent_data.health,
            "final_p1_hp": 0, "final_p2_hp": opponent_data.health,
            "damage_dealt_by_winner": opponent_data.attack, "damage_dealt_by_loser": 0, "rounds": 1
        }
        await end_battle(opponent_id, user_id, state, p2_key, p1_key, battle_data)
        return

    first_turn_player_id = choice([user_id, opponent_id])

    initial_battle_data = {
        "opponent_id": opponent_id,
        "opponent_chat_id": opponent_chat_id,
        "opponent_name": opponent_name,
        "my_hp": user_data.health,
        "my_atk": user_data.attack,
        "opponent_hp": opponent_data.health,
        "opponent_atk": opponent_data.attack,
        "current_turn": first_turn_player_id,
        "round": 1,
        "initial_my_hp": user_data.health,
        "initial_opponent_hp": opponent_data.health,
        "total_my_damage": 0,
        "total_opponent_damage": 0,
        "last_log_message": None
    }

    await state.storage.set_state(key=p1_key, state=BattleState.InBattle)
    await state.storage.set_data(key=p1_key, data=initial_battle_data)

    # Зеркальные данные для оппонента
    initial_battle_data_opponent = {
        "opponent_id": user_id,
        "opponent_chat_id": user_chat_id,
        "opponent_name": user_name,
        "my_hp": opponent_data.health,
        "my_atk": opponent_data.attack,
        "opponent_hp": user_data.health,
        "opponent_atk": user_data.attack,
        "current_turn": first_turn_player_id,
        "round": 1,
        "initial_my_hp": opponent_data.health,
        "initial_opponent_hp": user_data.health,
        "total_my_damage": 0,
        "total_opponent_damage": 0,
        "last_log_message": None
    }

    await state.storage.set_state(key=p2_key, state=BattleState.InBattle)
    await state.storage.set_data(key=p2_key, data=initial_battle_data_opponent)

    await send_battle_turn_message(user_id, p1_key, state)
    await send_battle_turn_message(opponent_id, p2_key, state)  # Функция сама определит, чей ход

def get_battle_keyboard(my_turn: bool, opponent_id: int) -> InlineKeyboardMarkup:
    if not my_turn: # Если не наш ход, кнопок нет
        buttons = [
            [InlineKeyboardButton(text="⏳ Ждите своего хода", callback_data=f"wait")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    buttons = [
        [InlineKeyboardButton(text="⚔️ Атака", callback_data=f"battle_attack:{opponent_id}")],
        [InlineKeyboardButton(text="⏳ Пропустить", callback_data=f"battle_skip:{opponent_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def send_battle_turn_message(user_id: int, key: StorageKey, state: FSMContext,):
    # Получаем текущее состояние боя для этого игрока
    user_state_data = await state.storage.get_data(key=key)
    if not user_state_data: return  # Состояния нет

    my_turn = user_state_data['current_turn'] == user_id
    my_hp = user_state_data['my_hp']
    opponent_hp = user_state_data['opponent_hp']
    opponent_name = user_state_data['opponent_name']
    opponent_id = user_state_data['opponent_id']
    round_num = user_state_data['round']

    text = (
        f"⛩️ Раунд {round_num}\n\n"
        f"👤 {opponent_name}: ❤️{opponent_hp}\n"
        f"🙍‍♂️ Вы: ❤️{my_hp}\n\n"
    )
    if my_turn:
        text += "🔥 Ваш ход!"
    else:
        text += f"⏳ Ожидание хода {opponent_name}..."

    keyboard = get_battle_keyboard(my_turn, opponent_id)

    # Пытаемся отредактировать предыдущее сообщение боя, если возможно
    # Нужно хранить message_id в FSM или использовать edit_message_text по callback.message
    # Для простоты пока отправляем новое сообщение
    await bot.send_message(user_id, text, reply_markup=keyboard)

async def end_battle(winner_id: int, loser_id: int, state: FSMContext, winner_key: StorageKey, loser_key: StorageKey, battle_data: dict):
    winner_name = battle_data['p1_name'] if battle_data['p1_id'] == winner_id else battle_data['p2_name']
    print(battle_data)
    loser_name = battle_data['p2_name'] if battle_data['p1_id'] == winner_id else battle_data['p1_name']

    # todo засчитывание победы в статистику
    # try:
    #     with conn.cursor() as cur:
    #         # Увеличиваем победы победителю
    #         cur.execute("UPDATE users SET season_wins = season_wins + 1 WHERE user_id = %s", (winner_id,))
    #         # Увеличиваем поражения проигравшему
    #         cur.execute("UPDATE users SET season_losses = season_losses + 1 WHERE user_id = %s", (loser_id,))
    #         # Выдаем награду победителю
    #         user_manager.add_shards(winner_id, BATTLE_REWARD_SHARDS, cursor=cur)
    #     conn.commit()
    #     print(f"Stats updated for battle between {winner_id} and {loser_id}")
    # except Exception as e:
    #     conn.rollback()
    #     print(f"Error updating stats/rewards after battle: {e}")

    # --- Формируем финальное сообщение ---
    # Определяем, кто был P1, кто P2 в терминах battle_data
    p1_data_key = 'p1' if battle_data['p1_id'] == winner_id else 'p2'
    p2_data_key = 'p2' if battle_data['p1_id'] == winner_id else 'p1'

    winner_log_name = battle_data[f'{p1_data_key}_name']
    loser_log_name = battle_data[f'{p2_data_key}_name']
    winner_damage = battle_data['damage_dealt_by_winner']
    loser_damage = battle_data['damage_dealt_by_loser']
    loser_hp_before = battle_data[f'initial_{p2_data_key}_hp']
    loser_hp_after = battle_data[f'final_{p2_data_key}_hp'] # Должен быть <= 0
    winner_hp_final = battle_data[f'final_{p1_data_key}_hp'] # ХП победителя
    rounds = battle_data['rounds']

    # Ссылка на профиль проигравшего (для победителя)
    loser_tg_link = f"(tg://user?id={loser_id})" # Было tg://openmessage?user_id={loser_id}, но tg://user стандартнее

    result_message = f"""
🌄🌋 Сражение между игроками {winner_name} и {loser_name} {loser_tg_link}

✨ Победа! ✨

🙍‍♂️ {winner_name} (❤️{winner_hp_final})
\t\t┗⊳ Наносит ⚔️{winner_damage} урона

👤 {loser_name}
\t\t┗⊳〘💔{loser_hp_before}〙➠〘☠️{max(0, loser_hp_after)}〙

🗡️ Всего урона нанесено: {winner_damage}
🦴 Урона получено: {loser_damage}
⛩️ Всего раундов: {rounds}

🌺 Держи свою награду за победу
\t +{BATTLE_REWARD_SHARDS}🀄️ осколка
"""

    # --- Отправляем результат и сохраняем лог ---
    try:
        await bot.send_message(winner_id, result_message)
        # Отправляем проигравшему немного измененное сообщение
        result_message_loser = result_message.replace(f"✨ Победа! ✨", "🚫 Поражение! 🚫")
        result_message_loser = result_message_loser.replace("🌺 Держи свою награду за победу", " ") # Убираем строку с наградой
        result_message_loser = result_message_loser.replace(f"\t +{BATTLE_REWARD_SHARDS}🀄️ осколка", "")
        await bot.send_message(loser_id, result_message_loser)

        await state.storage.update_data(key=winner_key, data={"last_log_message": result_message})
        await state.storage.update_data(key=loser_key, data={"last_log_message": result_message_loser})

    except Exception as e:
        print(f"Error sending final battle messages: {e}")

    # --- Очищаем состояние FSM для обоих игроков ---
    await state.storage.set_state(key=winner_key, state=None)
    await state.storage.set_state(key=loser_key, state=None)
    # Данные можно не чистить явно, если используем MemoryStorage, но для Redis лучше чистить
    # await state.storage.set_data(key=f'fsm:{winner_id}:{winner_id}', data={})
    # await state.storage.set_data(key=f'fsm:{loser_id}:{loser_id}', data={})


@arena_handler.callback_query(F.data.startswith("cancel_match"))
async def show_rarity_cards(call: CallbackQuery):
    remove_from_queue(call.from_user.id)
    await call.message.edit_text("❌ Матч отменен")

@arena_handler.callback_query(F.data == "arena")
async def show_arena_menu(call: CallbackQuery):
    user_name = call.from_user.first_name
    team = command_manager.format_user_team(call.from_user.id)
    all_stats = command_manager.get_team_stats(call.from_user.id)

    attack = all_stats.attack
    health = all_stats.health

    team_text = (f"┏➤{team[0][0]} {team[0][1]}\n"
                 f"┣➤{team[1][0]} {team[1][1]}\n"
                 f"┣➤{team[2][0]} {team[2][1]}\n"
                 f"┣➤{team[3][0]} {team[3][1]}\n"
                 f"┗➤{team[4][0]} {team[4][1]}")

    text = (
        f"👾 <b>{user_name}</b>, ты можешь собрать команду из карт и сражаться с другими игроками\n\n"
        f"🤜 <b>Твоя команда</b>\n"
        f"{team_text}\n\n"
        f"🗡️ Атака: {attack}\n"
        f"❤️ Здоровье: {health}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Найти противника", callback_data="find_opponent")],
            [
                InlineKeyboardButton(text="🎴 Команда", callback_data="arena_team"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="arena_stats")
            ],
            [
                InlineKeyboardButton(text="🏆 Турнир", callback_data="arena_tournament"),
                InlineKeyboardButton(text="👾 Босс", callback_data="arena_boss")
            ],
            [back_button("menu")]
        ]
    )
    await call.message.edit_text(text, reply_markup=keyboard)

@arena_handler.callback_query(F.data.startswith("battle_attack:"), BattleState.InBattle)
async def battle_attack_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    #target_opponent_id = int(callback.data.split(":")[1])

    p1_key = StorageKey(bot_id=bot.id, chat_id=callback.message.chat.id, user_id=user_id)

    attacker_data = await state.storage.get_data(p1_key)

    p2_key = StorageKey(bot_id=bot.id, chat_id=attacker_data.get("opponent_chat_id"), user_id=attacker_data.get("opponent_id"))
    defender_id = attacker_data.get("opponent_id")

    # Проверки
    if not attacker_data: return await callback.answer("Ошибка: Состояние боя не найдено.", show_alert=True)
    if attacker_data['current_turn'] != user_id: return await callback.answer("Сейчас не ваш ход!", show_alert=True)
    if attacker_data['opponent_id'] != defender_id: return await callback.answer("Ошибка: Неверная цель атаки.", show_alert=True)

    await callback.answer("Атакуем...") # Ответ на кнопку

    # Данные для обновления

    damage = attacker_data['my_atk']
    attacker_data['total_my_damage'] += damage # Обновляем суммарный урон

    # Получаем состояние защищающегося, чтобы обновить его HP
    defender_data = await state.storage.get_data(key=p2_key)
    if not defender_data: return # Ошибка, бой должен прекратиться?


    new_defender_hp = defender_data['my_hp'] - damage
    attacker_data['opponent_hp'] = new_defender_hp
    defender_data['my_hp'] = new_defender_hp
    defender_data['total_opponent_damage'] += damage # Урон, полученный защищающимся

    # Обновляем данные FSM для обоих
    await state.storage.set_data(key=p1_key, data=attacker_data)
    await state.storage.set_data(key=p2_key, data=defender_data)

    # --- Проверяем конец боя ---
    if new_defender_hp <= 0:
        final_data = {
            "p1_id": user_id, "p2_id": defender_id,
            "p1_name": defender_data['opponent_name'], # Получаем имена снова или храним в FSM
            "p2_name": attacker_data['opponent_name'],
            "p1_atk": attacker_data['my_atk'], "p2_atk": defender_data['my_atk'],
            "initial_p1_hp": attacker_data['initial_my_hp'], "initial_p2_hp": defender_data['initial_my_hp'],
            "final_p1_hp": attacker_data['my_hp'], "final_p2_hp": max(0, new_defender_hp), # Не уходим в минус в логе
            "damage_dealt_by_winner": attacker_data['total_my_damage'],
            "damage_dealt_by_loser": defender_data['total_my_damage'],
            "rounds": attacker_data['round']
        }
        await end_battle(user_id, defender_id, state, p1_key, p2_key, final_data)
    else:
        # --- Бой продолжается, передаем ход ---
        attacker_data['current_turn'] = defender_id
        defender_data['current_turn'] = defender_id # Оба знают, чей ход
        # Увеличиваем раунд, если ход вернулся к P1 (или просто после хода P2)
        # Проще увеличивать каждый раз, когда ходит второй игрок
        # Или после каждого хода p2
        if attacker_data['opponent_id'] == defender_id: # Если p2 ходил
             defender_data['round'] += 1
             attacker_data['round'] = defender_data['round'] # Синхронизируем раунд


        # Обновляем данные FSM
        await state.storage.set_data(key=p1_key, data=attacker_data)
        await state.storage.set_data(key=p2_key, data=defender_data)

        # Обновляем сообщения для обоих игроков
        await send_battle_turn_message(user_id, p1_key, state)
        await send_battle_turn_message(defender_id, p2_key, state)


@arena_handler.callback_query(F.data.startswith("battle_skip:"), BattleState.InBattle)
async def battle_skip_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    target_opponent_id = int(callback.data.split(":")[1])

    p1_key = StorageKey(bot_id=bot.id, chat_id=callback.message.chat.id, user_id=user_id)
    skipper_data = await state.storage.get_data(p1_key)

    p2_key = StorageKey(bot_id=bot.id, chat_id=skipper_data.get("opponent_chat_id"), user_id=skipper_data.get("opponent_id"))

    # Проверки
    if not skipper_data: return await callback.answer("Ошибка: Состояние боя не найдено.", show_alert=True)
    if skipper_data['current_turn'] != user_id: return await callback.answer("Сейчас не ваш ход!", show_alert=True)
    if skipper_data['opponent_id'] != target_opponent_id: return await callback.answer("Ошибка: Неверная цель.", show_alert=True)

    await callback.answer("Пропускаем ход...")

    opponent_id = target_opponent_id
    opponent_data = await state.storage.get_data(key=p2_key)
    if not opponent_data: return

    # Передаем ход
    skipper_data['current_turn'] = opponent_id
    opponent_data['current_turn'] = opponent_id
    # Увеличиваем раунд, если нужно (логика как в атаке)
    if skipper_data['opponent_id'] == opponent_id: # Если p2 ходил (пропускал)
          opponent_data['round'] += 1
          skipper_data['round'] = opponent_data['round']

    # Обновляем данные FSM
    await state.storage.set_data(key=p1_key, data=skipper_data)
    await state.storage.set_data(key=p2_key, data=opponent_data)

    # Обновляем сообщения для обоих игроков
    await send_battle_turn_message(user_id, p1_key, state)
    await send_battle_turn_message(opponent_id, p2_key, state)


@arena_handler.callback_query(F.data == "arena_team")
async def pick_team(call: CallbackQuery):
    await show_team_cards(call)

@arena_handler.callback_query(F.data == "arena_stats")
async def pick_team(call: CallbackQuery):
    user_data = await user_manager.get_user_info(call.from_user.id)
    text = (
    f"📊 {user_data.nickname}, вот твоя статистика сражений\n\n"
    "📋 За этот сезон\n"
    '➖➖➖➖➖➖\n'
    f'✊ Побед: {user_data.season_wins}\n'
    f'☠️ Поражений: {user_data.season_losses}\n'
    #'🛡️ Отразил нападений: {seasonal["defended"]}'
    f'⛩️ Всего сражений: {user_data.season_wins + user_data.season_losses}\n\n'

    '📜 За всё время\n'
    '➖➖➖➖➖➖\n'
    f'✊ Побед: {user_data.all_wins}\n'
    f'☠️ Поражений: {user_data.all_losses}\n'
    #'🛡️ Отразил нападений: {total["defended"]}'
    f'⛩️ Всего сражений: {user_data.all_wins + user_data.all_losses}')
    await call.message.edit_text(text, reply_markup=create_back_button("arena"))

@arena_handler.callback_query(F.data == "arena_tournament")
async def pick_team(call: CallbackQuery):
    user_data = await user_manager.get_user_info(call.from_user.id)
    await call.message.edit_text(f"🏆 {user_data.nickname}, турнир на данный момент не протекает. Ожидай начала следующего.", reply_markup=create_back_button("arena"))

@arena_handler.callback_query(lambda c: c.data.startswith("choose_card_slot_"))
async def pick_team(call: CallbackQuery):
    user_id = call.from_user.id
    selected_slot, page = call.data.split("_")[3], call.data.split("_")[4]
    cards = card_manager.get_user_cards_ordered_by_value(user_id)
    deck = command_manager.get_user_deck(user_id)
    if deck:
        used_card_ids = {card["id"] for card in deck if card["id"] is not None}
        filtered_cards = []
        for card in cards:
            if card["id"] not in used_card_ids:
                filtered_cards.append(card)
    else:
        filtered_cards = cards
    if not cards:
        await call.message.edit_text(f"У тебя еще нет карт, получи их с помощью кнопки ниже")
        return
    await show_cards(call, filtered_cards, int(page), int(selected_slot))



async def show_cards(call, cards, page=0, selected_slot=5):


    total_pages = (len(cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    if total_pages == 0:
        total_pages = 1

    if page >= total_pages:
        page = 0
    elif page < 0:
        page = total_pages - 1

    # Получаем карты для текущей страницы
    page_cards = get_page_cards(cards, page)

    # Формируем текст с заголовком
    text = (
        f"🃏 Nick, выбери карту\n"
        f"➖➖➖➖➖➖\n"
        f"🛖 Выбран слот номер ➨ {selected_slot}\n"
        f"📋 Страница {page + 1} из {total_pages}\n\n"
    )

    card_buttons = []
    for i, card in enumerate(page_cards):
        card_row = [InlineKeyboardButton(
            text=f"{rarity_translate[card['rarity']][0:3]} {card['name']}",
            callback_data=f"select_card:{card['id']}:{selected_slot}"
        )]
        card_buttons.append(card_row)

    # Создаем кнопки навигации
    navigation_row = []
    if page > 0:
        navigation_row.append(InlineKeyboardButton(
            text="⬅️",
            callback_data=f"choose_card_slot_{selected_slot}_{page - 1}"
        ))

    if page < total_pages - 1:
        navigation_row.append(InlineKeyboardButton(
            text="➡️",
            callback_data=f"choose_card_slot_{selected_slot}_{page + 1}"
        ))

    # Добавляем кнопку освобождения слота
    release_slot_row = [InlineKeyboardButton(
        text="Освободить слот",
        callback_data=f"select_card:0:{selected_slot}"
    )]
    keyboard_rows = card_buttons + [navigation_row] + [release_slot_row] + [[back_button("arena_team")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    try:
        await call.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        # Если не удалось отредактировать, отправляем новое сообщение
        await call.message.answer(text, reply_markup=keyboard)

@arena_handler.callback_query(lambda c: c.data.startswith("select_card"))
async def pick_card(call: CallbackQuery):
    _, card_id, slot = call.data.split(":")
    command_manager.assign_card_to_position(
        call.from_user.id,
        None if card_id == "0" else int(card_id),
        int(slot)
    )
    await show_team_cards(call)

async def show_team_cards(call):
    team = command_manager.format_user_team(call.from_user.id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{emoji}", callback_data=f"choose_card_slot_{i + 1}_0   ") for i, (emoji, name)
             in enumerate(team)],
            [back_button("arena")]
        ]
    )

    team_text = (f"┏➤{team[0][0]} {team[0][1]}\n"
                 f"┣➤{team[1][0]} {team[1][1]}\n"
                 f"┣➤{team[2][0]} {team[2][1]}\n"
                 f"┣➤{team[3][0]} {team[3][1]}\n"
                 f"┗➤{team[4][0]} {team[4][1]}\n")
    # team_text = "\n".join([f"┏{emoji} {name}" for emoji, name in team])

    text = (f"🏕️ Nick, чтобы собрать команду, жми на слоты ниже и выбирай карту\n\n"
    "🍤 Твоя команда\n"
    f"{team_text}")
    await call.message.edit_text(text, reply_markup=keyboard)

def get_page_cards(cards, page):
    """Получаем карты для текущей страницы"""
    start_idx = page * CARDS_PER_PAGE
    end_idx = min(start_idx + CARDS_PER_PAGE, len(cards))
    return cards[start_idx:end_idx]

def remove_from_queue(user_id: int):
    global matchmaking_queue
    matchmaking_queue = deque(entry for entry in matchmaking_queue if entry[0] != user_id)





# --- bot\handlers\clans.py ---
from aiogram import Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.card_database import rarity_translate
from bot.handlers.mainMenu import back_button, create_back_button
from bot.Classes.db_manager import task_manager, user_manager, command_manager, card_manager

clan = Router()

@clan.callback_query(F.data == "clans")
async def menu_clans(call: CallbackQuery):
    user_name = call.from_user.first_name

    text = (
        f"🏰 <b><a href='tg://user?id={call.from_user.id}'>{user_name}</a></b>, "
        "ты можешь создать или вступить в клан и играть с другими игроками"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🏰 Создать клан", callback_data="create_clan")
    keyboard.button(text="🚩 Вступить в клан", callback_data="join_clan")
    keyboard.button(text="⬅️ Назад", callback_data="menu")
    keyboard.adjust(1)

    await call.message.edit_text(
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await call.answer()

@clan.callback_query(F.data == "create_clan")
async def create_clan(call: CallbackQuery):
    user_data = await user_manager.get_user_info(call.from_user.id)
    if user_data.has_battle_pass:
        print("yes")
    else:
        await call.message.edit_text(f"🔒🔑 <b><a href='tg://user?id={call.from_user.id}'>{call.from_user.first_name}</a></b>, "
                                     f"для создания клана необходимо иметь Aniverse pass", reply_markup=create_back_button("clans"))

@clan.callback_query(F.data == "join_clan")
async def join_clan(call: CallbackQuery):
    user_id = call.from_user.id
    user_name = call.from_user.first_name

    text = (
        f"🏰 <b>{user_name}</b>, чтобы вступить в клан, для начала найди главу клана, который будет готов принять тебя\n\n"
        f"📝 Если глава клана готов принять тебя, пусть напишет команду:\n"
        f"<code>Пригласить {user_id}</code> или <code>Пригласить @{call.from_user.username or 'твой_username'}</code>\n\n"
        f"📩 В лс бота тебе придёт сообщение, где ты сможешь принять или отвергнуть предложение вступить в клан\n\n"
        f"🆔 Твой ID: <code>{user_id}</code>"
    )

    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=create_back_button("clans")
    )
    await call.answer()

@clan.message(F.text.startswith("Пригласить"))
async def invite_to_clan_handler(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("⚠️ Укажи ID или @username пользователя для приглашения.")
        return

    target = parts[1].strip()

    # Попробуем получить ID
    try:
        if target.startswith("@"):
            # Допиши свой метод поиска ID по username
            # Пример: user_id = get_user_id_by_username(target[1:])
            await message.reply("🔍 Поиск по @username пока не реализован.")
            return
        else:
            user_id = int(target)
    except ValueError:
        await message.reply("⚠️ Неверный формат ID или username.")
        return

    # Отправим приглашение в ЛС пользователя
    text = (
        f"🏰 Тебя пригласили вступить в клан!\n\n"
        f"👤 Глава клана: <b>{message.from_user.full_name}</b>\n\n"
        f"Хочешь принять приглашение?"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_invite:{message.from_user.id}"),
            InlineKeyboardButton(text="❌ Отказаться", callback_data="decline_invite")
        ]
    ])

    try:
        await message.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await message.reply("📩 Приглашение отправлено!")
    except Exception as e:
        await message.reply(f"❌ Не удалось отправить приглашение: {e}")

@clan.callback_query(F.data.startswith("accept_invite:"))
async def accept_invite(call: CallbackQuery):
    leader_id = int(call.data.split(":")[1])
    # Тут логика добавления в клан
    await call.message.edit_text("🎉 Ты принял приглашение и вступил в клан!")
    await call.answer()

@clan.callback_query(F.data == "decline_invite")
async def decline_invite(call: CallbackQuery):
    await call.message.edit_text("❌ Ты отклонил приглашение.")
    await call.answer()



# --- bot\handlers\mainMenu.py ---
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F, Bot # Import Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram import Router
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging # Import logging

from bot.card_database import rarity_translate
from bot.keyboards.main_keyboard import main_menu
# Import case_manager
from bot.Classes.db_manager import task_manager, command_manager, user_manager, clan_manager, card_manager, case_manager

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

def get_pagination_keyboard(position: str, current_page: int, total_pages: int, extra_buttons: Optional[List[List[InlineKeyboardButton]]] = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav_row = []
    if current_page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"{position}:{current_page - 1}"))
    # Add page indicator button (non-clickable or specific action)
    nav_row.append(InlineKeyboardButton(text=f"Страница {current_page}/{total_pages}", callback_data="noop")) # noop = no operation
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"{position}:{current_page + 1}"))

    if nav_row:
        builder.row(*nav_row)

    if extra_buttons:
        for row in extra_buttons:
            builder.row(*row)

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



# --- bot\keyboards\main_keyboard.py ---
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🃏 Получить карточку"), KeyboardButton(text="💼 Мои карты")],
            [KeyboardButton(text="☁️ Меню"), KeyboardButton(text="⚙️ Настройки")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )
    return keyboard

