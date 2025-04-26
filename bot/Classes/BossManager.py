# bot\Classes\BossManager.py
import logging
from typing import Optional, List, Dict, Any, Tuple
import psycopg2
import psycopg2.extras
from psycopg2.extensions import cursor as Psycopg2Cursor
from datetime import datetime, timezone

from bot.card_database import DatabaseManager
from bot.Classes.UserManager import UserManager
from bot.Classes.CommandManager import CommandManager

# Определение структуры наград (можно вынести в конфиг/базу)
BOSS_REWARD_TIERS = [
    (10, 40),    # top 1-10: 40 spins
    (50, 30),    # top 11-50: 30 spins
    (150, 20),   # top 51-150: 20 spins
    (500, 10),   # top 151-500: 10 spins
]
PARTICIPATION_REWARD_SPINS = 3 # Награда за простое участие

class BossManager:
    def __init__(self, db_manager: DatabaseManager, user_manager: UserManager, command_manager: CommandManager):
        self.db = db_manager
        self.user_manager = user_manager
        self.command_manager = command_manager

    def get_active_boss(self) -> Optional[Dict[str, Any]]:
        """Возвращает данные текущего активного босса."""
        query = "SELECT * FROM world_bosses WHERE is_active = TRUE ORDER BY start_time DESC LIMIT 1"
        result = self.db.execute(query, fetch='one')
        return dict(result) if result else None

    def has_user_attacked(self, user_id: int, boss_instance_id: int) -> bool:
        """Проверяет, атаковал ли пользователь этого конкретного босса."""
        query = "SELECT 1 FROM world_boss_damage WHERE user_id = %s AND boss_instance_id = %s"
        result = self.db.execute(query, (user_id, boss_instance_id), fetch='one')
        return result is not None

    def deal_damage(self, user_id: int, damage: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Наносит урон активному боссу от пользователя.
        Обрабатывает первую атаку, обновление урона, проверку на убийство босса.
        Возвращает (успех, сообщение, данные_босса_после_атаки).
        """
        if damage <= 0:
            return False, "Урон должен быть положительным.", None

        conn = None
        try:
            conn = self.db._get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # 1. Найти активного босса и заблокировать строку
                cur.execute("SELECT * FROM world_bosses WHERE is_active = TRUE FOR UPDATE")
                active_boss = cur.fetchone()

                if not active_boss:
                    conn.rollback()
                    return False, "В данный момент нет активного мирового босса.", None

                boss_id = active_boss['id']
                current_hp = active_boss['current_health']

                # 2. Проверить, не был ли босс уже побежден (на всякий случай)
                if current_hp <= 0:
                    conn.rollback()
                    # Если босс уже побежден, но еще активен, деактивируем его
                    if active_boss['is_active']:
                         self.db.execute(
                             "UPDATE world_bosses SET is_active = FALSE, end_time = NOW() WHERE id = %s AND is_active = TRUE",
                             (boss_id,)
                         )
                    return False, f"Босс '{active_boss['name']}' уже побежден!", dict(active_boss)


                # 3. Проверить, атаковал ли пользователь этого босса ранее
                cur.execute("SELECT id, damage_dealt FROM world_boss_damage WHERE user_id = %s AND boss_instance_id = %s FOR UPDATE",
                            (user_id, boss_id))
                damage_record = cur.fetchone()

                if damage_record:
                    conn.rollback() # Пользователь уже атаковал
                    return False, "Вы уже атаковали этого босса.", dict(active_boss)

                # 4. Рассчитать новое ХП босса
                new_hp = max(0, current_hp - damage) # Не уходим в минус

                # 5. Обновить ХП босса
                cur.execute("UPDATE world_bosses SET current_health = %s WHERE id = %s", (new_hp, boss_id))
                if cur.rowcount != 1:
                    conn.rollback()
                    raise Exception("Не удалось обновить ХП босса.")

                # 6. Записать урон пользователя
                now_time = datetime.now(timezone.utc)
                cur.execute(
                    """INSERT INTO world_boss_damage (boss_instance_id, user_id, damage_dealt, last_attack_time)
                       VALUES (%s, %s, %s, %s)""",
                    (boss_id, user_id, damage, now_time)
                )
                if cur.rowcount != 1:
                    conn.rollback()
                    raise Exception("Не удалось записать урон пользователя.")

                boss_defeated = new_hp <= 0
                final_boss_data = dict(active_boss) # Копируем данные до изменения HP
                final_boss_data['current_health'] = new_hp # Обновляем для возврата

                # 7. Если босс побежден этой атакой
                if boss_defeated:
                    logging.info(f"Босс ID {boss_id} ({active_boss['name']}) побежден пользователем {user_id}!")
                    cur.execute("UPDATE world_bosses SET is_active = FALSE, end_time = NOW() WHERE id = %s", (boss_id,))
                    if cur.rowcount != 1:
                         logging.error(f"Не удалось деактивировать побежденного босса {boss_id}")
                         # Продолжаем, но логируем ошибку

                # 8. Коммитим транзакцию
                conn.commit()

                message = f"Вы успешно нанесли {damage} урона боссу '{active_boss['name']}'! Осталось {new_hp} HP."
                if boss_defeated:
                    message += "\n\n✨ Поздравляем! Босс побежден! Скоро начнется распределение наград."
                    # Запускаем распределение наград (можно асинхронно)
                    # asyncio.create_task(self.distribute_rewards_async(boss_id)) # Если делать асинхронно
                    # Пока делаем синхронно для простоты
                    self.distribute_rewards(boss_id)

                return True, message, final_boss_data

        except psycopg2.Error as e:
            if conn: conn.rollback()
            logging.error(f"Ошибка psycopg2 при нанесении урона боссу от {user_id}: {e}")
            return False, "Ошибка базы данных при атаке.", None
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"Неожиданная ошибка при нанесении урона боссу от {user_id}: {e}", exc_info=True)
            return False, "Внутренняя ошибка сервера.", None

    def get_boss_leaderboard(self, boss_instance_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает топ игроков по урону для указанного экземпляра босса."""
        query = """
            SELECT
                d.user_id,
                u.username,
                d.damage_dealt,
                RANK() OVER (ORDER BY d.damage_dealt DESC) as rank
            FROM world_boss_damage d
            JOIN users u ON d.user_id = u.user_id
            WHERE d.boss_instance_id = %s
            ORDER BY d.damage_dealt DESC
            LIMIT %s;
        """
        results = self.db.execute(query, (boss_instance_id, limit), fetch='all')
        return [dict(row) for row in results] if results else []

    def get_user_boss_rank_and_damage(self, user_id: int, boss_instance_id: int) -> Optional[Dict[str, Any]]:
         """Получает ранг и урон конкретного пользователя для конкретного босса."""
         # Используем подзапрос для получения ранга
         query = """
             WITH ranked_damage AS (
                 SELECT
                     user_id,
                     damage_dealt,
                     RANK() OVER (ORDER BY damage_dealt DESC) as rank
                 FROM world_boss_damage
                 WHERE boss_instance_id = %s
             )
             SELECT damage_dealt, rank
             FROM ranked_damage
             WHERE user_id = %s;
         """
         result = self.db.execute(query, (boss_instance_id, user_id), fetch='one')
         return dict(result) if result else None

    def distribute_rewards(self, boss_instance_id: int):
        """Распределяет награды (free_spins) после победы над боссом."""
        logging.info(f"Начало распределения наград для босса ID {boss_instance_id}...")

        # Проверяем, не были ли награды уже выданы
        boss_info = self.db.execute(
             "SELECT rewards_distributed, name FROM world_bosses WHERE id = %s",
             (boss_instance_id,), fetch='one'
        )
        if not boss_info:
             logging.error(f"Не найден босс ID {boss_instance_id} для распределения наград.")
             return
        if boss_info['rewards_distributed']:
             logging.warning(f"Награды для босса ID {boss_instance_id} уже были распределены.")
             return

        # Получаем всех участников битвы с их уроном и рангом
        participants_query = """
             SELECT
                 user_id,
                 damage_dealt,
                 RANK() OVER (ORDER BY damage_dealt DESC) as rank
             FROM world_boss_damage
             WHERE boss_instance_id = %s
             ORDER BY rank ASC;
        """
        participants = self.db.execute(participants_query, (boss_instance_id,), fetch='all')

        if not participants:
            logging.info(f"Нет участников для босса ID {boss_instance_id}. Награды не выдаются.")
            # Помечаем, что награды обработаны (хотя их и не было)
            self.db.execute("UPDATE world_bosses SET rewards_distributed = TRUE WHERE id = %s", (boss_instance_id,))
            return

        logging.info(f"Найдено {len(participants)} участников для босса ID {boss_instance_id}.")
        rewards_to_give = {} # user_id -> spins_to_add

        # Определяем награды по рангу
        for p in participants:
            user_id = p['user_id']
            rank = p['rank']
            spins = 0
            # Проверяем тиры наград
            for rank_limit, tier_spins in BOSS_REWARD_TIERS:
                if rank <= rank_limit:
                    spins = tier_spins
                    break # Берем первую подходящую награду (самую высокую)
            # Если не попал в тиры, но участвовал
            if spins == 0 and p['damage_dealt'] > 0:
                 spins = PARTICIPATION_REWARD_SPINS

            if spins > 0:
                 rewards_to_give[user_id] = spins

        # Начисляем награды (free_spins) через UserManager
        # Лучше делать это в одной транзакции для надежности
        conn = None
        success_count = 0
        fail_count = 0
        try:
             conn = self.db._get_connection()
             with conn.cursor() as cur:
                  for user_id, spins in rewards_to_give.items():
                       # Используем метод UserManager для добавления спинов
                       if self.user_manager.add_free_spins(user_id, spins, cursor=cur):
                            logging.debug(f"Начислено {spins} спинов пользователю {user_id} за босса {boss_instance_id}.")
                            success_count += 1
                            # TODO: Опционально отправить уведомление пользователю (может замедлить процесс)
                       else:
                            fail_count += 1
                            logging.error(f"Не удалось начислить {spins} спинов пользователю {user_id}.")

                  # Помечаем, что награды выданы
                  cur.execute("UPDATE world_bosses SET rewards_distributed = TRUE WHERE id = %s", (boss_instance_id,))
             conn.commit()
             logging.info(f"Распределение наград для босса {boss_instance_id} завершено. Успешно: {success_count}, Ошибок: {fail_count}.")

        except Exception as e:
             if conn: conn.rollback()
             logging.error(f"Ошибка при распределении наград для босса {boss_instance_id}: {e}", exc_info=True)

        # Опционально: Запуск спавна нового босса после паузы
        # asyncio.create_task(self.spawn_boss_after_delay(delay_seconds=3600))

    def create_new_boss(self, name: str, health: int, image_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Создает нового босса, деактивируя старого."""
        conn = None
        try:
            conn = self.db._get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # 1. Деактивировать всех текущих активных боссов
                cur.execute("UPDATE world_bosses SET is_active = FALSE WHERE is_active = TRUE")
                logging.info(f"Деактивировано {cur.rowcount} предыдущих боссов.")

                # 2. Создать нового босса
                cur.execute(
                    """INSERT INTO world_bosses (name, max_health, current_health, image_path, is_active, start_time)
                       VALUES (%s, %s, %s, %s, TRUE, NOW())
                       RETURNING *""",
                    (name, health, health, image_path) # Начинаем с полным здоровьем
                )
                new_boss = cur.fetchone()
                if not new_boss:
                     conn.rollback()
                     logging.error(f"Не удалось создать нового босса '{name}'.")
                     return None

            conn.commit()
            logging.info(f"Новый мировой босс '{name}' (ID: {new_boss['id']}) создан и активен.")
            return dict(new_boss)

        except psycopg2.Error as e:
            if conn: conn.rollback()
            logging.error(f"Ошибка psycopg2 при создании нового босса '{name}': {e}")
            return None
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"Неожиданная ошибка при создании нового босса '{name}': {e}", exc_info=True)
            return None