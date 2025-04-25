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

