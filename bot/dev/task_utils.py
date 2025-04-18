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