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
        """Регистрирует нового пользователя или игнорирует, если он уже существует."""
        query = """
            INSERT INTO users (user_id, username) VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING;
        """
        # Execute возвращает None при INSERT/UPDATE/DELETE, если fetch не указан
        # Для проверки, была ли вставка, можно было бы использовать RETURNING user_id,
        # но ON CONFLICT DO NOTHING не возвращает ничего, если конфликт произошел.
        # Проще выполнить и не проверять результат в данном случае.
        self.db.execute(query, (user_id, username))
        # Можно считать успешным, если не было исключения psycopg2.Error
        return True # Упрощенно считаем, что всегда успешно (либо уже есть, либо вставили)

    async def get_user_info(self, user_id: int) -> Optional[UserProfile]:
        """Получает полную информацию о профиле пользователя."""

        # cached = await redis.hgetall(f"user:{user_id}:profile")
        # if cached:
        #     return UserProfile(
        #         nickname=cached.get("nickname"),
        #         total_cards_received=int(cached.get("total_cards_received", 0)),
        #         cards_owned=int(cached.get("cards_owned", 0)),
        #         total_cards_in_game=int(cached.get("total_cards_in_game", 0)),
        #         season_points=int(cached.get("season_points", 0)),
        #         coins=int(cached.get("coins", 0)),
        #         clan_name=cached.get("clan_name"),
        #         clan_role=cached.get("clan_role"),
        #     )


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
            # Возможно, стоит зарегистрировать пользователя, если он не найден?
            # self.register_user(user_id)
            # user_row = self.db.execute(query, (user_id,), fetch='one')
            # if user_row is None: return None # Если и после регистрации нет
            return None

        profile = UserProfile(
            nickname=user_row["username"] or f"User_{user_id}",
            total_cards_received=user_row["total_cards_received"],
            cards_owned=user_row["cards_owned_count"],
            total_cards_in_game=user_row["total_cards_in_game"],
            season_points=user_row["rating"],
            has_battle_pass=user_row["has_battle_pass"],
            season_wins=user_row["season_wins"],
            season_losses=user_row["season_losses"],
            all_wins=user_row["all_wins"],
            all_losses=user_row["all_losses"],
            coins=user_row["coins"],
            clan_name=user_row["clan_name"],
            clan_role=user_row["clan_role"]
        )

        await redis.hset(f"user:{user_id}:profile", mapping={
            "nickname": profile.nickname,
            "total_cards_received": profile.total_cards_received,
            "cards_owned": profile.cards_owned,
            "total_cards_in_game": profile.total_cards_in_game,
            "season_points": profile.season_points,
            "coins": profile.coins,
            "clan_name": profile.clan_name or "",
            "clan_role": profile.clan_role or "",
        })

        return profile

    def update_username(self, user_id: int, new_username: str):
        query = "UPDATE users SET username = %s WHERE user_id = %s"
        self.db.execute(query, (new_username, user_id))

    def update_rating(self, user_id: int, delta_rating: int):
        """Изменяет рейтинг пользователя на указанную дельту."""
        query = "UPDATE users SET rating = rating + %s WHERE user_id = %s"
        self.db.execute(query, (delta_rating, user_id))

    def set_battle_pass(self, user_id: int, has_pass: bool):
        query = "UPDATE users SET has_battle_pass = %s WHERE user_id = %s"
        self.db.execute(query, (has_pass, user_id))

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

        # Важно: Проверка баланса и списание в одной транзакции
        conn = self.db._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # Проверяем баланс
                cur.execute("SELECT coins FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
                result = cur.fetchone()
                if result is None or result['coins'] < amount:
                    conn.rollback() # Откатываем, т.к. FOR UPDATE заблокировал строку
                    return False # Пользователь не найден или недостаточно средств

                # Списываем монеты
                cur.execute("UPDATE users SET coins = coins - %s WHERE user_id = %s", (amount, user_id))
                conn.commit()
                return True
        except psycopg2.Error as e:
            conn.rollback()
            print(f"Ошибка при списании монет: {e}")
            return False

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
            else:
                # Здесь нужно быть осторожным, т.к. db.execute коммитит сам
                # Если add_shards вызывается не из транзакции TaskManager, это ОК
                # Если вызывается изнутри транзакции БЕЗ курсора, это может нарушить транзакцию.
                # Лучше всегда передавать курсор из TaskManager.
                self.db.execute(query, (amount, user_id))  # Используем db.execute для простоты, если нет курсора
            return True
        except Exception as e:
            print(f"Ошибка при добавлении {amount} осколков пользователю {user_id}: {e}")
            # Не откатываем транзакцию здесь, т.к. она управляется извне (в TaskManager)
            return False

    def get_shards(self, user_id: int) -> int:
        """Получает баланс осколков пользователя."""
        query = "SELECT shards FROM users WHERE user_id = %s"
        result = self.db.execute(query, (user_id,), fetch='one')
        return result['shards'] if result else 0

    def get_top_users_by_season(self, limit=10):
        return self.db.execute(
            """
            SELECT user_id, username, season_rating
            FROM users
            ORDER BY season_rating DESC
            LIMIT %s;
            """,
            (limit,),
            fetch='all'
        )

    def get_user_season_rank(self, user_id):
        return self.db.execute(
            """
            SELECT COUNT(*) + 1
            FROM users
            WHERE season_rating > (
                SELECT season_rating FROM users WHERE user_id = %s
            );
            """,
            (user_id,),
            fetch='one'
        )[0]

    def get_top_users_alltime(self, limit=10):
        return self.db.execute(
            """
            SELECT user_id, username, rating
            FROM users
            ORDER BY rating DESC
            LIMIT %s;
            """,
            (limit,),
            fetch='all'
        )

    def get_user_alltime_rank(self, user_id):
        return self.db.execute(
            """
            SELECT COUNT(*) + 1
            FROM users
            WHERE rating > (
                SELECT rating FROM users WHERE user_id = %s
            );
            """,
            (user_id,),
            fetch='one'
        )[0]
#user_manager = UserManager(db)