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