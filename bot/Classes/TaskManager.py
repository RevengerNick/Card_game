# task_manager.py

import datetime as dt
import random
from typing import List, Dict, Any, Optional, TYPE_CHECKING

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
            print(f"Пользователь {user_id} выполнил ВСЕ задания за {date}, получил бонус {self.BONUS_REWARD_SHARDS} осколков!")

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