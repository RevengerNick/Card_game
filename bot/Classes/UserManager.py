# bot\Classes\UserManager.py
from typing import Optional, Tuple, Any, List, Dict, Union # Добавил Union
from datetime import datetime, timezone, timedelta
import logging
import psycopg2
import psycopg2.extras # для DictCursor
from psycopg2.extensions import cursor as Psycopg2Cursor # For type hinting

# Redis закомментирован, так как не используется активно
# from redis.asyncio import Redis
# redis = Redis(host="localhost", port=6379, decode_responses=True)

# Импорт из card_database
from bot.card_database import DatabaseManager, UserProfile, db, \
    SUPER_ADMIN_ID  # db здесь не нужен, если db_manager передается

class UserManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def register_user(self, user_id: int, username: Optional[str] = None) -> bool:
        """Регистрирует нового пользователя или обновляет его username. Возвращает True при успехе."""
        username = username if username else None
        query = """
            INSERT INTO users (user_id, username, registered_at) VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username
            RETURNING user_id; -- Возвращаем ID для подтверждения
        """
        now_utc = datetime.now(timezone.utc)
        try:
            result = self.db.execute(query, (user_id, username, now_utc), fetch='one')
            return result is not None # Если вернулся результат (ID), значит успешно
        except psycopg2.Error as e:
             logging.error(f"Ошибка psycopg2 при регистрации/обновлении пользователя {user_id}: {e}")
             return False
        except Exception as e:
             logging.error(f"Неожиданная ошибка при регистрации/обновлении пользователя {user_id}: {e}")
             return False

    def is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором."""
        query = "SELECT 1 FROM admins WHERE user_id = %s"
        result = self.db.execute(query, (user_id,), fetch='one')
        if user_id in SUPER_ADMIN_ID:
            return True
        else:
            return result is not None

    def add_free_spins(self, user_id: int, amount: int, cursor: Optional[Psycopg2Cursor] = None) -> bool:
        """Добавляет бесплатные прокрутки пользователю. Возвращает True при успехе."""
        if amount <= 0: return False
        query = "UPDATE users SET free_spins = free_spins + %s WHERE user_id = %s"
        try:
            if cursor:
                cursor.execute(query, (amount, user_id))
                # Проверяем, что строка была обновлена (пользователь существует)
                return cursor.rowcount == 1
            else:
                rows_affected = self.db.execute(query, (amount, user_id))
                # rows_affected будет 1 при успехе, 0 если user_id не найден, None при ошибке БД
                return rows_affected == 1
        except Exception as e:
            logging.error(f"Ошибка при добавлении {amount} бесплатных спинов пользователю {user_id}: {e}")
            return False

    def add_admin(self, user_id: int) -> bool:
        """Добавляет пользователя в администраторы. Возвращает True при успехе или если уже был админом."""
        if not self.get_user_raw(user_id):
             logging.error(f"Нельзя добавить админа: пользователь {user_id} не найден в таблице users.")
             return False

        query = "INSERT INTO admins (user_id, added_at) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING"
        now_utc = datetime.now(timezone.utc)
        try:
             rows_affected = self.db.execute(query, (user_id, now_utc))
             # rows_affected будет 1 если вставили, 0 если конфликт (уже админ), None при ошибке
             if rows_affected is not None: # Успешное выполнение запроса (0 или 1)
                 if rows_affected == 1:
                     logging.info(f"Пользователь {user_id} успешно добавлен в администраторы.")
                 else:
                     logging.info(f"Пользователь {user_id} уже был администратором.")
                 return True
             else: # Ошибка БД
                 logging.error(f"Не удалось добавить администратора {user_id} (execute вернул None).")
                 return False
        except psycopg2.Error as e: # Этот блок может быть избыточен, т.к. execute ловит ошибки
             logging.error(f"Ошибка psycopg2 при добавлении администратора {user_id}: {e}")
             return False
        except Exception as e:
             logging.error(f"Неожиданная ошибка при добавлении администратора {user_id}: {e}")
             return False

    def remove_admin(self, user_id: int) -> bool:
        """Удаляет пользователя из администраторов. Возвращает True, если строка была удалена."""
        query = "DELETE FROM admins WHERE user_id = %s"
        try:
             rows_affected = self.db.execute(query, (user_id,))
             if rows_affected == 1:
                 logging.info(f"Пользователь {user_id} успешно удален из администраторов.")
                 return True
             elif rows_affected == 0:
                 logging.warning(f"Пользователь {user_id} не найден в списке администраторов для удаления.")
                 return False # Указываем, что удаления не было
             else: # rows_affected is None (ошибка БД)
                 logging.error(f"Не удалось удалить администратора {user_id} (execute вернул None).")
                 return False
        except psycopg2.Error as e: # Избыточен, если execute ловит
             logging.error(f"Ошибка psycopg2 при удалении администратора {user_id}: {e}")
             return False
        except Exception as e:
             logging.error(f"Неожиданная ошибка при удалении администратора {user_id}: {e}")
             return False

    def get_user_raw(self, user_id: int) -> Optional[dict]:
         """Получает сырые данные пользователя из таблицы 'users'."""
         query = "SELECT * FROM users WHERE user_id = %s"
         result = self.db.execute(query, (user_id,), fetch='one')
         # Конвертируем DictRow в dict для единообразия, если нужно
         return dict(result) if result else None

    def get_user_info(self, user_id: int) -> Optional[UserProfile]:
        """
        Получает полную информацию о профиле пользователя.
        Возвращает None, если пользователь не найден или забанен.
        """
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
            logging.debug(f"Пользователь {user_id} не найден в БД.")
            return None

        if user_row['is_banned']:
            logging.info(f"Доступ запрещен: пользователь {user_id} забанен.")
            return None

        try:
             profile = UserProfile(
                 nickname=user_row["username"] or f"User_{user_id}",
                 total_cards_received=user_row["total_cards_received"],
                 cards_owned=user_row["cards_owned_count"],
                 total_cards_in_game=user_row["total_cards_in_game"],
                 season_points=user_row["season_rating"],
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
                 is_banned=user_row["is_banned"],
                 clan_name=user_row["clan_name"],
                 clan_role=user_row["clan_role"]
             )
             return profile
        except KeyError as e:
             logging.error(f"Ошибка при создании UserProfile для {user_id}: отсутствует ключ {e} в user_row.", exc_info=True)
             return None
        except Exception as e:
             logging.error(f"Неожиданная ошибка при создании UserProfile для {user_id}: {e}", exc_info=True)
             return None


    def update_username(self, user_id: int, new_username: str) -> bool:
        """Обновляет username. Возвращает True при успехе."""
        query = "UPDATE users SET username = %s WHERE user_id = %s"
        rows_affected = self.db.execute(query, (new_username, user_id))
        return rows_affected == 1

    def update_rating(self, user_id: int, delta_rating: int) -> bool:
        """Обновляет общий рейтинг. Возвращает True при успехе."""
        query = "UPDATE users SET rating = rating + %s WHERE user_id = %s"
        rows_affected = self.db.execute(query, (delta_rating, user_id))
        return rows_affected == 1

    def update_season_rating(self, user_id: int, delta_rating: int) -> bool:
        """Обновляет сезонный рейтинг. Возвращает True при успехе."""
        query = "UPDATE users SET season_rating = season_rating + %s WHERE user_id = %s"
        rows_affected = self.db.execute(query, (delta_rating, user_id))
        return rows_affected == 1

    def set_battle_pass(self, user_id: int, has_pass: bool) -> bool:
        """Устанавливает статус Battle Pass. Возвращает True при успехе."""
        query = "UPDATE users SET has_battle_pass = %s WHERE user_id = %s"
        rows_affected = self.db.execute(query, (has_pass, user_id))
        return rows_affected == 1

    def set_referrer(self, user_id: int, referrer_id: int) -> int:
        """Устанавливает реферера, если его нет. Возвращает количество обновленных строк (0 или 1)."""
        if user_id == referrer_id:
             logging.warning(f"Пользователь {user_id} не может быть реферером самого себя.")
             return 0
        query = "UPDATE users SET referrer_id = %s WHERE user_id = %s AND referrer_id IS NULL"
        rows_affected = self.db.execute(query, (referrer_id, user_id))
        return rows_affected if rows_affected is not None else 0

    def add_referral(self, user_id: int) -> bool:
        """Увеличивает счетчик рефералов. Возвращает True при успехе."""
        query = "UPDATE users SET referrals = referrals + 1 WHERE user_id = %s"
        rows_affected = self.db.execute(query, (user_id,))
        return rows_affected == 1

    def add_coins(self, user_id: int, amount: int, cursor: Optional[Psycopg2Cursor] = None) -> bool:
        """Добавляет монеты. Возвращает True при успехе."""
        if amount <= 0: return False
        query = "UPDATE users SET coins = coins + %s WHERE user_id = %s"
        try:
            if cursor:
                cursor.execute(query, (amount, user_id))
                return cursor.rowcount == 1
            else:
                rows_affected = self.db.execute(query, (amount, user_id))
                return rows_affected == 1
        except Exception as e:
            logging.error(f"Ошибка при добавлении {amount} монет пользователю {user_id}: {e}")
            return False

    def get_coins(self, user_id: int) -> int:
        """Получает баланс монет."""
        query = "SELECT coins FROM users WHERE user_id = %s"
        result = self.db.execute(query, (user_id,), fetch='one')
        return result['coins'] if result else 0

    def spend_coins(self, user_id: int, amount: int, cursor: Optional[Psycopg2Cursor] = None) -> bool:
        """Списывает монеты. Возвращает True при успехе."""
        if amount <= 0: return False

        query = "UPDATE users SET coins = coins - %s WHERE user_id = %s AND coins >= %s"
        try:
            if cursor:
                cursor.execute(query, (amount, user_id, amount))
                return cursor.rowcount == 1
            else:
                rows_affected = self.db.execute(query, (amount, user_id, amount))
                return rows_affected == 1
        except Exception as e:
            logging.error(f"Ошибка при списании {amount} монет у пользователя {user_id}: {e}")
            return False

    def get_total_cards_received(self, user_id: int) -> int:
        """Получает общее количество полученных карт."""
        query = "SELECT total_cards_received FROM users WHERE user_id = %s"
        result = self.db.execute(query, (user_id,), fetch='one')
        return result['total_cards_received'] if result else 0

    def get_last_card_time(self, user_id: int) -> Optional[datetime]:
        """Получает время последнего получения карты."""
        query = "SELECT last_card_received FROM users WHERE user_id = %s"
        result = self.db.execute(query, (user_id,), fetch='one')
        dt_obj = result['last_card_received'] if result and result['last_card_received'] else None
        if dt_obj and dt_obj.tzinfo is None:
             return dt_obj.replace(tzinfo=timezone.utc)
        return dt_obj

    def update_last_card_time(self, user_id: int, time: datetime) -> bool:
        """Обновляет время последнего получения карты. Возвращает True при успехе."""
        if time.tzinfo is None:
            logging.warning("update_last_card_time received a naive datetime. Assuming UTC.")
            time = time.replace(tzinfo=timezone.utc)
        query = "UPDATE users SET last_card_received = %s WHERE user_id = %s"
        rows_affected = self.db.execute(query, (time, user_id))
        return rows_affected == 1

    # --- Shard Management ---

    def add_shards(self, user_id: int, amount: int, cursor: Optional[Psycopg2Cursor] = None) -> bool:
        """Добавляет осколки. Возвращает True при успехе."""
        if amount <= 0: return False
        query = "UPDATE users SET shards = shards + %s WHERE user_id = %s"
        try:
            if cursor:
                cursor.execute(query, (amount, user_id))
                return cursor.rowcount == 1
            else:
                rows_affected = self.db.execute(query, (amount, user_id))
                return rows_affected == 1
        except Exception as e:
            logging.error(f"Ошибка при добавлении {amount} осколков пользователю {user_id}: {e}")
            return False

    def get_shards(self, user_id: int) -> int:
        """Получает баланс осколков."""
        query = "SELECT shards FROM users WHERE user_id = %s"
        result = self.db.execute(query, (user_id,), fetch='one')
        return result['shards'] if result else 0

    def spend_shards(self, user_id: int, amount: int, cursor: Optional[Psycopg2Cursor] = None) -> bool:
        """Списывает осколки. Возвращает True при успехе."""
        if amount <= 0: return False

        query = "UPDATE users SET shards = shards - %s WHERE user_id = %s AND shards >= %s"
        try:
            if cursor:
                cursor.execute(query, (amount, user_id, amount))
                return cursor.rowcount == 1
            else:
                rows_affected = self.db.execute(query, (amount, user_id, amount))
                return rows_affected == 1
        except Exception as e:
            logging.error(f"Ошибка при списании {amount} осколков у пользователя {user_id}: {e}")
            return False

    # --- Ban Management ---

    def ban_user(self, user_id: int) -> bool:
        """Банит пользователя. Возвращает True при успехе."""
        query = "UPDATE users SET is_banned = TRUE WHERE user_id = %s"
        rows_affected = self.db.execute(query, (user_id,))
        if rows_affected == 1:
             logging.info(f"Пользователь {user_id} забанен.")
             return True
        # Либо пользователь не найден (rows=0), либо ошибка БД (rows=None)
        logging.warning(f"Не удалось забанить пользователя {user_id} (затронуто строк: {rows_affected}).")
        return False


    def unban_user(self, user_id: int) -> bool:
        """Разбанивает пользователя. Возвращает True при успехе."""
        query = "UPDATE users SET is_banned = FALSE WHERE user_id = %s AND is_banned = TRUE"
        rows_affected = self.db.execute(query, (user_id,))
        if rows_affected == 1:
             logging.info(f"Пользователь {user_id} разбанен.")
             return True
        logging.info(f"Не удалось разбанить {user_id} (не найден, не забанен, или ошибка БД - строк: {rows_affected}).")
        return False

    def reset_user_account(self, user_id: int) -> bool:
        """Сбрасывает аккаунт пользователя. USE WITH CAUTION!"""
        logging.warning(f"!!! НАЧАТ СБРОС АККАУНТА ДЛЯ ПОЛЬЗОВАТЕЛЯ {user_id} !!!")
        conn = None
        try:
            conn = self.db._get_connection()
            with conn.cursor() as cur:
                # Удаляем связанные данные
                logging.debug(f"Удаление данных user_cards для {user_id}")
                cur.execute("DELETE FROM user_cards WHERE user_id = %s", (user_id,))
                logging.debug(f"Удаление данных user_decks для {user_id}")
                cur.execute("DELETE FROM user_decks WHERE user_id = %s", (user_id,))
                logging.debug(f"Удаление данных user_promos для {user_id}")
                cur.execute("DELETE FROM user_promos WHERE user_id = %s", (user_id,))
                logging.debug(f"Удаление данных user_daily_tasks для {user_id}")
                cur.execute("DELETE FROM user_daily_tasks WHERE user_id = %s", (user_id,))
                logging.debug(f"Удаление данных daily_bonus_claimed для {user_id}")
                cur.execute("DELETE FROM daily_bonus_claimed WHERE user_id = %s", (user_id,))

                # Сбрасываем поля в таблице users
                logging.debug(f"Сброс полей в таблице users для {user_id}")
                cur.execute("""
                    UPDATE users
                    SET
                        clan_id = NULL, clan_role = NULL, has_battle_pass = FALSE,
                        rating = 0, season_rating = 0, coins = 0, last_card_received = NULL,
                        referrals = 0, total_cards_received = 0, free_spins = 0,
                        shards = 0, shards_rare = 0, shards_epic = 0, shards_legendary = 0,
                        season_wins = 0, season_losses = 0, all_wins = 0, all_losses = 0,
                        total_duplicates_received = 0, is_banned = FALSE
                    WHERE user_id = %s;
                """, (user_id,))

                if cur.rowcount != 1:
                     logging.warning(f"Пользователь {user_id} не найден в таблице users во время сброса (UPDATE не затронул строки).")
                     # Тем не менее, коммитим удаления связанных данных

            conn.commit()
            logging.info(f"!!! Аккаунт пользователя {user_id} успешно сброшен. !!!")
            return True
        except psycopg2.Error as e:
            if conn: conn.rollback()
            logging.error(f"Ошибка psycopg2 при сбросе аккаунта пользователя {user_id}: {e}")
            return False
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"Неожиданная ошибка при сбросе аккаунта пользователя {user_id}: {e}", exc_info=True)
            return False

    def get_all_user_ids(self, include_banned=False) -> List[int]:
        """Получает список ID всех пользователей."""
        query = "SELECT user_id FROM users"
        if not include_banned:
            query += " WHERE is_banned = FALSE"
        results = self.db.execute(query, fetch='all')
        return [row['user_id'] for row in results] if results else []

    # --- Statistics Methods ---
    # ----- ИСПРАВЛЕНО ЗДЕСЬ: Добавлен аргумент include_banned -----
    def get_total_user_count(self, include_banned=False) -> int:
        """Получает общее количество зарегистрированных пользователей."""
        query = "SELECT COUNT(*) as count FROM users"
        params = None
        if not include_banned:
            query += " WHERE is_banned = FALSE"
        # Передаем params=None, если он не используется
        result = self.db.execute(query, params, fetch='one')
        return result['count'] if result else 0
    # ---------------------------------------------------------

    def get_total_cards_given_out(self) -> int:
        """Получает сумму total_cards_received по всем пользователям."""
        query = "SELECT SUM(total_cards_received) as total FROM users"
        result = self.db.execute(query, fetch='one')
        return result['total'] if result and result['total'] is not None else 0

    def get_battle_pass_count(self) -> int:
        """Получает количество пользователей с активным Battle Pass (не забаненных)."""
        query = "SELECT COUNT(*) as count FROM users WHERE has_battle_pass = TRUE AND is_banned = FALSE"
        result = self.db.execute(query, fetch='one')
        return result['count'] if result else 0

    def get_total_currency_in_system(self) -> Dict[str, int]:
        """Получает общее количество валюты у не забаненных пользователей."""
        query = """
            SELECT
                SUM(coins) as total_coins,
                SUM(shards) as total_shards,
                SUM(shards_rare) as total_shards_rare,
                SUM(shards_epic) as total_shards_epic,
                SUM(shards_legendary) as total_shards_legendary
            FROM users
            WHERE is_banned = FALSE;
        """
        result = self.db.execute(query, fetch='one')
        if result:
            # Используем .get() с default=0 для безопасности, если SUM вернет NULL
            return {
                "coins": result.get("total_coins", 0) or 0,
                "shards": result.get("total_shards", 0) or 0,
                "shards_rare": result.get("total_shards_rare", 0) or 0,
                "shards_epic": result.get("total_shards_epic", 0) or 0,
                "shards_legendary": result.get("total_shards_legendary", 0) or 0,
            }
        else:
             return {"coins": 0, "shards": 0, "shards_rare": 0, "shards_epic": 0, "shards_legendary": 0}


    # --- Ranking Methods ---

    def get_top_users_by_season(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает топ N пользователей по сезонному рейтингу (не забаненных)."""
        query = """
            SELECT user_id, username, season_rating
            FROM users WHERE is_banned = FALSE
            ORDER BY season_rating DESC, user_id ASC
            LIMIT %s;
        """
        results = self.db.execute(query, (limit,), fetch='all')
        return [dict(row) for row in results] if results else []

    def get_user_season_rank(self, user_id: int) -> Optional[int]:
        """Получает ранг пользователя по сезонному рейтингу."""
        user_data = self.db.execute(
            "SELECT season_rating FROM users WHERE user_id = %s AND is_banned = FALSE",
            (user_id,), fetch='one'
        )
        if not user_data:
            return None

        user_rating = user_data['season_rating']
        query = """
            SELECT COUNT(*) + 1 as rank
            FROM users
            WHERE season_rating > %s AND is_banned = FALSE;
        """
        result = self.db.execute(query, (user_rating,), fetch='one')
        # COUNT(*) всегда возвращает строку, поэтому rank должен быть
        return result['rank'] if result else None

    def get_top_users_alltime(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает топ N пользователей по общему рейтингу (не забаненных)."""
        query = """
            SELECT user_id, username, rating
            FROM users WHERE is_banned = FALSE
            ORDER BY rating DESC, user_id ASC
            LIMIT %s;
        """
        results = self.db.execute(query, (limit,), fetch='all')
        return [dict(row) for row in results] if results else []

    def get_user_alltime_rank(self, user_id: int) -> Optional[int]:
        """Получает ранг пользователя по общему рейтингу."""
        user_data = self.db.execute(
            "SELECT rating FROM users WHERE user_id = %s AND is_banned = FALSE",
            (user_id,), fetch='one'
        )
        if not user_data: return None

        user_rating = user_data['rating']
        query = """
            SELECT COUNT(*) + 1 as rank
            FROM users
            WHERE rating > %s AND is_banned = FALSE;
        """
        result = self.db.execute(query, (user_rating,), fetch='one')
        return result['rank'] if result else None