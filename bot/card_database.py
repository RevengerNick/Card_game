import psycopg2
import psycopg2.extras # для DictCursor
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import os
import logging # Import logging

# ... (rest of your imports and dataclasses) ...

# --- Конфигурация ---
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASSWORD = ""
DB_HOST = "localhost"
DB_PORT = "5432"
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))

DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

@dataclass
class DeckProfile:
    attack: int
    health: int
    value: int

# --- Датаклассы и константы ---
@dataclass
class UserProfile:
    nickname: str
    total_cards_received: int
    cards_owned: int
    total_cards_in_game: int
    season_points: int
    has_battle_pass: bool
    season_wins: int
    season_losses: int
    all_wins: int
    all_losses: int
    free_spins: int
    coins: int
    shards: int # General shards
    shards_rare: int # Specific rarity shards (if used differently)
    shards_epic: int
    shards_legendary: int
    is_banned: bool # Added ban status
    clan_name: Optional[str] = None
    clan_role: Optional[str] = None

reward_levels = [
        (10, 5, 0),
        (50, 10, 0),
        (100, 15, 0),
        (350, 20, 50),
        (500, 50, 300),
        (1000, 100, 1000),
        (5000, 300, 5000),
    ]


rarity_translate = {
    'common': ' ⚜️ Обычная',
    'rare': '⚡️ Редкая',
    'epic': ' 🐉 Эпическая',
    'legendary': '🩸 Легендарная',
    'mythical': '✨ Мифическая'
}

RARITY_WEIGHTS = {
    'common': 40,
    'rare': 25,
    'epic': 20,
    'legendary': 10,
    'mythical': 5
}

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

    def _get_connection(self):
        """Возвращает активное соединение, переподключается при необходимости."""
        try:
            # Проверяем, живо ли соединение (ping)
            if self._conn is None or self._conn.closed != 0:
                self._connect()
            # Можно добавить более надежную проверку:
            # self._conn.cursor().execute("SELECT 1")
        except psycopg2.OperationalError:
            print("Переподключение к PostgreSQL...")
            self._connect()
        return self._conn

    def drop_all_tables(self):
        """Удаляет все таблицы в схеме public."""
        conn = self._get_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                DO $$
                DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                        EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
            """)
            conn.commit()
            return "Все таблицы были удалены."

    def execute(self, query: str, params: tuple = None, fetch: str = None) -> Any:
        """
        Выполняет SQL-запрос.
        :param query: SQL-запрос с плейсхолдерами %s.
        :param params: Кортеж параметров для запроса.
        :param fetch: 'one', 'all' или None.
        :return: Результат запроса или None.
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(query, params)
                if fetch == 'one':
                    result = cur.fetchone()
                elif fetch == 'all':
                    result = cur.fetchall()
                else:
                    result = None # Для INSERT, UPDATE, DELETE
                conn.commit() # Коммитим изменения после успешного выполнения
                return result
        except psycopg2.Error as e:
            conn.rollback() # Откатываем транзакцию в случае ошибки
            print(f"Ошибка выполнения запроса: {e}")
            print(f"Запрос: {query}")
            print(f"Параметры: {params}")
            # Можно перевыбросить ошибку или вернуть маркер ошибки
            # raise e
            return None # Или специфический маркер ошибки

    def executescript(self, script: str):
         """Выполняет несколько SQL-запросов."""
         conn = self._get_connection()
         try:
             with conn.cursor() as cur:
                 cur.execute(script)
             conn.commit()
         except psycopg2.Error as e:
             conn.rollback()
             print(f"Ошибка выполнения скрипта: {e}")
             # raise e

    def close(self):
        """Закрывает соединение с БД."""
        if self._conn and self._conn.closed == 0:
            self._conn.close()
            print("Соединение с PostgreSQL закрыто")

    # В классе DatabaseManager

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


