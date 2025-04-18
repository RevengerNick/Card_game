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

    def give_card_to_user(self, user_id: int, card_id: int, amount: int = 1) -> Dict[str, Any]:
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
                reward_cards_to_add = [] # Список ID карт для награды

                for goal, card_reward_count, coins_reward in reward_levels:
                    # Проверяем, был ли порог ПЕРЕСЕЧЕН именно в этом вызове
                    if old_total_received < goal <= new_total_received:
                        print(f"Пользователь {user_id} достиг рубежа {goal} карт!") # Лог

                #         # Начисляем монеты
                #         if coins_reward > 0:
                #             total_coins_reward += coins_reward
                #             rewards_granted_list.append({'type': 'coins', 'amount': coins_reward, 'goal': goal})
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
                # if total_coins_reward > 0:
                #     cur.execute("UPDATE users SET coins = coins + %s WHERE user_id = %s", (total_coins_reward, user_id))
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