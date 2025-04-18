import psycopg2
import psycopg2.extras # для DictCursor
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

reward_levels = [
        (10, 5, 0),
        (50, 10, 0),
        (100, 15, 0),
        (350, 20, 50),
        (500, 50, 300),
        (1000, 100, 1000),
        (5000, 300, 5000),
    ]

# --- Конфигурация (лучше вынести в переменные окружения или .env файл) ---
# Пример использования переменных окружения:
# DB_NAME = os.getenv("DB_NAME", "cards_db")
# DB_USER = os.getenv("DB_USER", "user")
# DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
# DB_HOST = os.getenv("DB_HOST", "localhost")
# DB_PORT = os.getenv("DB_PORT", "5432")

# Для примера оставим строки здесь, но НЕ ДЕЛАЙ ТАК В ПРОДАКШЕНЕ!
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASSWORD = ""
DB_HOST = "localhost"
DB_PORT = "5432"

DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- Датаклассы и константы ---
@dataclass
class UserProfile:
    nickname: str
    cards_owned: int # Количество уникальных карт
    total_cards_received: int
    total_cards_in_game: int # Всего карт в игре
    season_wins: int
    season_losses: int
    has_battle_pass: bool
    all_wins: int
    all_losses: int
    season_points: int
    coins: int
    clan_name: Optional[str] = None
    clan_role: Optional[str] = None

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

# --- Базовый класс для управления БД ---
class DatabaseManager:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._conn = None
        self._connect()
        self.create_tables()

    def _connect(self):
        """Устанавливает соединение с БД."""
        try:
            self._conn = psycopg2.connect(self.dsn)
            print("Успешное подключение к PostgreSQL")
        except psycopg2.OperationalError as e:
            print(f"Ошибка подключения к PostgreSQL: {e}")
            # Здесь можно добавить логику повторного подключения или выхода
            raise

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

    def create_tables(self):
        """Создает все необходимые таблицы с нуля (если они не существуют)."""
        script = """
        -- Таблица карт
        CREATE TABLE IF NOT EXISTS cards (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            rarity TEXT NOT NULL,
            attack INTEGER NOT NULL,
            health INTEGER NOT NULL,
            value INTEGER NOT NULL,
            image_path TEXT,
            drop_weight INTEGER DEFAULT 1
        );

        -- Таблица кланов создается до таблицы пользователей
        CREATE TABLE IF NOT EXISTS clans (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            description TEXT,
            points INTEGER DEFAULT 0,
            rank INTEGER DEFAULT 0,
            leader_id BIGINT -- FK constraint added later
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
            total_cards_received INTEGER NOT NULL DEFAULT 0,
            season_wins INTEGER NOT NULL DEFAULT 0,
            season_losses INTEGER NOT NULL DEFAULT 0,
            all_wins INTEGER NOT NULL DEFAULT 0,
            all_losses INTEGER NOT NULL DEFAULT 0,
            total_duplicates_received INTEGER NOT NULL DEFAULT 0,
            shards INTEGER NOT NULL DEFAULT 0
        );

        -- Таблица колод пользователей - исправлена ссылка на user_id
        CREATE TABLE IF NOT EXISTS user_decks (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            card_id INTEGER REFERENCES cards(id) ON DELETE CASCADE,
            position INTEGER NOT NULL, -- позиция карты в команде (1-5)
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, position) -- один пользователь не может иметь две карты на одной позиции
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
            reward_amount INTEGER NOT NULL, -- Награда в монетах
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

        -- 1. Справочник заданий
        CREATE TABLE IF NOT EXISTS daily_tasks (
            id SERIAL PRIMARY KEY,
            description TEXT NOT NULL, -- "Получи {target} обычные карты"
            task_type TEXT NOT NULL, -- 'GET_RARITY_CARD', 'GET_ANY_CARD', 'INVITE_FRIEND'
            target INTEGER NOT NULL,
            rarity_condition TEXT DEFAULT NULL, -- 'common', 'rare', etc.
            reward_shards INTEGER NOT NULL DEFAULT 5
        );

        -- 2. Прогресс пользователя по заданиям
        CREATE TABLE IF NOT EXISTS user_daily_tasks (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            task_id INTEGER NOT NULL REFERENCES daily_tasks(id) ON DELETE CASCADE,
            progress INTEGER NOT NULL DEFAULT 0,
            target INTEGER NOT NULL, -- Цель (дублируем для удобства)
            completed BOOLEAN NOT NULL DEFAULT FALSE,
            reward_claimed BOOLEAN NOT NULL DEFAULT FALSE, -- Получена ли награда за это задание
            date DATE NOT NULL DEFAULT CURRENT_DATE,
            UNIQUE (user_id, task_id, date) -- Уникальный прогресс по заданию на день
        );

        -- 3. Активные задания на день (для общего подхода)
        CREATE TABLE IF NOT EXISTS daily_active_tasks (
            date DATE PRIMARY KEY,
            task_ids INTEGER[] NOT NULL -- Массив ID заданий из daily_tasks
        );

        -- 4. Отметка получения бонуса за все задания дня
        CREATE TABLE IF NOT EXISTS daily_bonus_claimed (
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            date DATE NOT NULL DEFAULT CURRENT_DATE,
            claimed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (user_id, date)
        );

        -- === Индексы ===
        CREATE INDEX IF NOT EXISTS idx_user_decks_user_id ON user_decks(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_decks_card_id ON user_decks(card_id);
        CREATE INDEX IF NOT EXISTS idx_user_cards_user_id ON user_cards(user_id);
        CREATE INDEX IF NOT EXISTS idx_users_clan_id ON users(clan_id);
        CREATE INDEX IF NOT EXISTS idx_user_daily_tasks_user_date ON user_daily_tasks(user_id, date);
        CREATE INDEX IF NOT EXISTS idx_promo_achievements_code ON promo_achievements(code);
        CREATE INDEX IF NOT EXISTS idx_daily_tasks_type ON daily_tasks(task_type); -- Для TaskManager
        """

        # Выполняем весь скрипт создания таблиц
        self.executescript(script)
        print("Создание базовых таблиц и таблиц заданий выполнено.")

        # --- Добавляем внешний ключ для clans.leader_id ---
        # Добавляем проверку существования таблицы clans
        check_clans = self.execute("SELECT to_regclass('public.clans') IS NOT NULL AS exists", fetch='one')

        if check_clans and check_clans['exists']:
            self.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_name = 'fk_clans_leader' AND table_name = 'clans'
                ) THEN
                    ALTER TABLE clans ADD CONSTRAINT fk_clans_leader
                    FOREIGN KEY (leader_id) REFERENCES users(user_id) ON DELETE SET NULL;
                    RAISE NOTICE 'Добавлен внешний ключ fk_clans_leader.';
                ELSE
                    RAISE NOTICE 'Внешний ключ fk_clans_leader уже существует.';
                END IF;
            END $$;
            """)
            print("Внешний ключ для clans.leader_id обработан.")
        else:
            print("Таблица clans не найдена, пропуск добавления внешнего ключа.")

        print("--- Проверка и создание всех таблиц завершены ---")

db = DatabaseManager(DSN)

if __name__ == '__main__':
    pass
    #
    #     # --- Работа с пользователями ---
    #     print("\n--- Пользователи ---")
    #     user_id_1 = 1001
    #     user_id_2 = 1002
    #     user_manager.register_user(user_id_1, "Alice")
    #     user_manager.register_user(user_id_2, "Bob")
    #     print(f"Профиль Alice: {user_manager.get_user_info(user_id_1)}")
    #     user_manager.add_coins(user_id_1, 50)
    #     print(f"Монеты Alice: {user_manager.get_coins(user_id_1)}")
    #     if user_manager.spend_coins(user_id_1, 20):
    #          print("Alice потратила 20 монет.")
    #     else:
    #          print("У Alice не хватило монет.")
    #     print(f"Монеты Alice после траты: {user_manager.get_coins(user_id_1)}")
    #
    #     # --- Работа с картами ---
    #     print("\n--- Карты ---")
    #     # Добавим пару карт, если их нет
    #     if not card_manager.get_all_cards():
    #          card1_id = card_manager.add_card("Warrior", "common", 10, 5, 100)
    #          card2_id = card_manager.add_card("Mage", "rare", 5, 10, 250)
    #          print(f"Добавлены карты с ID: {card1_id}, {card2_id}")
    #     else:
    #          cards_list = card_manager.get_all_cards()
    #          card1_id = cards_list[0]['id']
    #          card2_id = cards_list[1]['id'] if len(cards_list) > 1 else card1_id
    #
    #
    #     if card_manager.can_receive_card(user_id_1):
    #         random_card = card_manager.get_random_card()
    #         if random_card:
    #              print(f"Alice может получить карту. Выпала: {random_card['name']}")
    #              card_manager.give_card_to_user(user_id_1, random_card['id'])
    #              print(f"Карты Alice: {card_manager.get_user_cards(user_id_1)}")
    #         else:
    #              print("Нет доступных карт для выдачи.")
    #     else:
    #         print("Alice еще не может получить карту (кулдаун).")
    #
    #     # --- Работа с кланами ---
    #     print("\n--- Кланы ---")
    #     # Создадим клан, если у Боба его нет
    #     bob_info = user_manager.get_user_info(user_id_2)
    #     if bob_info and bob_info.clan_name is None:
    #          clan_id = clan_manager.create_clan("Dragons", user_id_2, "Mighty clan")
    #          if clan_id:
    #               print(f"Создан клан Dragons (ID: {clan_id})")
    #               # Добавим Алису в клан
    #               clan_manager.add_user_to_clan(user_id_1, clan_id)
    #               print("Алиса добавлена в клан Dragons")
    #               # Повысим Алису
    #               clan_manager.set_clan_role(user_id_1, clan_id, "deputy")
    #               print("Алиса повышена до deputy")
    #
    #               print(f"Инфо о клане Dragons: {clan_manager.get_clan_info(clan_id)}")
    #          else:
    #               print("Не удалось создать клан (возможно, имя занято).")
    #     else:
    #          print("Боб уже в клане или не зарегистрирован.")
    #
    #     print(f"Топ кланов: {clan_manager.get_top_clans()}")
    #
    #
    #     # --- Работа с промокодами ---
    #     print("\n--- Промокоды ---")
    #     promo = promo_manager.generate_promo_code(reward_amount=100, uses=2, custom_code="WELCOME100")
    #     if promo:
    #         print(f"Сгенерирован промокод: {promo}")
    #
    #         # Алиса применяет промокод
    #         success, message = promo_manager.apply_promo_code(user_id_1, promo)
    #         print(f"Алиса применяет {promo}: {message}")
    #
    #         # Боб применяет промокод
    #         success, message = promo_manager.apply_promo_code(user_id_2, promo)
    #         print(f"Боб применяет {promo}: {message}")
    #
    #         # Третья попытка (должна быть неудачной)
    #         success, message = promo_manager.apply_promo_code(9999, promo) # Несуществующий юзер
    #         print(f"Третья попытка применить {promo}: {message}") # Ошибка, т.к. кончились использования
    #
    #         print(f"Активные промо: {promo_manager.get_active_promos()}")
    #         print(f"Промо Алисы: {promo_manager.get_used_promos_by_user(user_id_1)}")
    #
    # except psycopg2.OperationalError as e:
    #     print(f"Критическая ошибка подключения к БД. Проверьте настройки DSN. Ошибка: {e}")
    # except Exception as e:
    #     print(f"Произошла непредвиденная ошибка: {e}")
    # finally:
    #     # Закрываем соединение при выходе
    #     if 'db_manager' in locals() and db:
    #         db.close()