# bot\Classes\CardManager.py
from datetime import timedelta, datetime, timezone # Use timezone from datetime
from typing import Optional, Any, List, Dict, Tuple # Добавил Tuple
import random
import logging

# Import necessary components from card_database
from bot.card_database import (
    DatabaseManager, RARITY_WEIGHTS, RARITY_CHOICES, reward_levels, db,
    rarity_translate # Keep db import if CardManager is instantiated elsewhere
)
# Import UserManager to interact with user data (like last received time)
from bot.Classes.UserManager import UserManager
import psycopg2
import psycopg2.extras # for DictCursor
from psycopg2 import tz as psycopg2_tz # For FixedOffsetTimezone

class CardManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        # Reference to UserManager will be set via db_manager.py instantiation
    @property
    def user_manager(self) -> UserManager:
        # Lazy load or ensure it's set by the time it's needed.
        if not hasattr(self, '_user_manager_instance'):
             from .db_manager import user_manager as um_instance
             self._user_manager_instance = um_instance
        return self._user_manager_instance


    def add_card(self, name: str, rarity: str, attack: int, health: int, value: int, image_path: Optional[str] = None) -> Optional[int]:
        """Добавляет новую карту в игру. Возвращает ID новой карты или None при ошибке/конфликте."""
        rarity = rarity.lower()
        if rarity not in RARITY_CHOICES:
            logging.error(f"Попытка добавить карту с неверной редкостью: {rarity}")
            return None

        drop_weight = RARITY_WEIGHTS.get(rarity, 1)
        query = """
            INSERT INTO cards (name, rarity, attack, health, value, image_path, drop_weight)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO NOTHING -- Prevent duplicates by name
            RETURNING id;
        """
        try:
            result = self.db.execute(query, (name, rarity, attack, health, value, image_path, drop_weight), fetch='one')
            if result:
                logging.info(f"Карта '{name}' (ID: {result['id']}) успешно добавлена.")
                return result['id']
            else:
                # This happens if ON CONFLICT DO NOTHING was triggered
                logging.warning(f"Карта с именем '{name}' уже существует. Вставка проигнорирована.")
                # Find the existing card ID if needed
                existing = self.db.execute("SELECT id FROM cards WHERE name = %s", (name,), fetch='one')
                return existing['id'] if existing else None
        except psycopg2.Error as e:
            logging.error(f"Ошибка psycopg2 при добавлении карты '{name}': {e}")
            return None
        except Exception as e:
            logging.error(f"Неожиданная ошибка при добавлении карты '{name}': {e}")
            return None

    def edit_card(self, card_id: int, name: Optional[str] = None, rarity: Optional[str] = None,
                  attack: Optional[int] = None, health: Optional[int] = None, value: Optional[int] = None,
                  image_path: Optional[str] = None) -> bool:
        """Редактирует существующую карту. Возвращает True при успехе, False при ошибке."""
        current_card = self.get_card_by_id(card_id)
        if not current_card:
            logging.error(f"Карта с ID {card_id} не найдена для редактирования.")
            return False

        updates = []
        params = []

        if name is not None and name != current_card['name']:
            # Check if new name conflicts with another card
            existing = self.db.execute("SELECT id FROM cards WHERE name = %s AND id != %s", (name, card_id), fetch='one')
            if existing:
                logging.error(f"Не удалось изменить имя карты {card_id}: имя '{name}' уже занято картой ID {existing['id']}.")
                return False
            updates.append("name = %s")
            params.append(name)

        if rarity is not None and rarity.lower() != current_card['rarity']:
            rarity_lower = rarity.lower()
            if rarity_lower not in RARITY_CHOICES:
                 logging.error(f"Попытка установить неверную редкость '{rarity}' для карты {card_id}")
                 return False
            updates.append("rarity = %s")
            params.append(rarity_lower)
            updates.append("drop_weight = %s")
            params.append(RARITY_WEIGHTS.get(rarity_lower, 1))

        if attack is not None and attack != current_card['attack']:
            if attack < 0: logging.warning("Attack should be non-negative"); return False
            updates.append("attack = %s")
            params.append(attack)
        if health is not None and health != current_card['health']:
            if health <= 0: logging.warning("Health must be positive"); return False
            updates.append("health = %s")
            params.append(health)
        if value is not None and value != current_card['value']:
            if value < 0: logging.warning("Value should be non-negative"); return False
            updates.append("value = %s")
            params.append(value)
        # Allow setting image_path to None or changing it
        if image_path is not None and image_path != current_card['image_path']:
            updates.append("image_path = %s")
            params.append(image_path)
        elif image_path == "" and current_card['image_path'] is not None: # Handle explicit empty string as setting to NULL
             updates.append("image_path = NULL")


        if not updates:
            logging.info(f"Нет полей для обновления карты {card_id}.")
            return True # No changes needed is considered success

        params.append(card_id) # Add ID for WHERE clause
        query = f"UPDATE cards SET {', '.join(updates)} WHERE id = %s"

        try:
             rows_affected = self.db.execute(query, tuple(params))
             if rows_affected is not None: # Should be 1 if update occurred
                 logging.info(f"Карта ID {card_id} успешно обновлена.")
                 return True
             else:
                 # This might happen if execute failed internally and returned None
                 logging.error(f"Не удалось обновить карту ID {card_id} (execute вернул None).")
                 return False
        except psycopg2.Error as e:
             logging.error(f"Ошибка psycopg2 при обновлении карты {card_id}: {e}")
             # Check for unique constraint violation if name was updated
             if "duplicate key value violates unique constraint" in str(e) and name is not None:
                  logging.error(f"Конфликт имени '{name}' при обновлении карты ID {card_id}.")
             return False
        except Exception as e:
             logging.error(f"Неожиданная ошибка при обновлении карты {card_id}: {e}")
             return False

    def get_card_by_id(self, card_id: int) -> Optional[Dict[str, Any]]:
        """Получает информацию о карте по ID."""
        query = "SELECT * FROM cards WHERE id = %s"
        result = self.db.execute(query, (card_id,), fetch='one')
        return dict(result) if result else None

    def get_all_cards(self) -> List[Dict[str, Any]]:
        """Получает список всех карт в игре, отсортированный."""
        rarity_order = {rarity: index for index, rarity in enumerate(RARITY_CHOICES)}
        query = "SELECT * FROM cards ORDER BY name" # Simple sort first
        results = self.db.execute(query, fetch='all') or []
        sorted_results = sorted(results, key=lambda card: (rarity_order.get(card['rarity'], 99), card['name']))
        return [dict(row) for row in sorted_results]

    def get_user_cards(self, user_id: int) -> List[Dict[str, Any]]:
        """Получает список карт пользователя (инвентарь) с их количеством."""
        query = """
            SELECT c.*, uc.amount, uc.obtained_at
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = %s
            ORDER BY c.id;
        """
        results = self.db.execute(query, (user_id,), fetch='all') or []
        return [dict(row) for row in results]


    def can_receive_card(self, user_id: int, cooldown_hours: int = 4) -> Tuple[bool, Optional[timedelta]]:
        """
        Проверяет, может ли пользователь получить карту (прошел ли кулдаун).
        Возвращает: (True, None) если можно получить, (False, remaining_time) если кулдаун активен.
        """
        last_time = self.user_manager.get_last_card_time(user_id)
        if not last_time:
            # ----- ИСПРАВЛЕНО ЗДЕСЬ -----
            return True, None # Никогда не получал карту -> Можно получить, времени ожидания нет

        if last_time.tzinfo is None:
             last_time = last_time.replace(tzinfo=timezone.utc)
             logging.warning(f"last_card_received for user {user_id} was naive, assuming UTC.")

        now_aware = datetime.now(timezone.utc)
        cooldown_duration = timedelta(hours=cooldown_hours)
        time_passed = now_aware - last_time

        if time_passed >= cooldown_duration:
            # ----- ИСПРАВЛЕНО ЗДЕСЬ -----
            return True, None # Кулдаун прошел -> Можно получить, времени ожидания нет
        else:
            remaining_time = cooldown_duration - time_passed
            if remaining_time.total_seconds() < 0:
                # ----- ИСПРАВЛЕНО ЗДЕСЬ -----
                # На случай расхождения времени, если remaining отрицательное - значит уже можно
                return True, None
            # ----- ИСПРАВЛЕНО ЗДЕСЬ -----
            return False, remaining_time # Кулдаун активен -> Нельзя получить, возвращаем оставшееся время

    def reset_last_received_time(self, user_id: int):
        """Сбрасывает таймер получения карты (для админских команд)."""
        reset_time = datetime.now(timezone.utc) - timedelta(hours=24)
        success = self.user_manager.update_last_card_time(user_id, reset_time)
        if success:
            logging.info(f"Время последнего получения карты для пользователя {user_id} сброшено.")
        else:
            logging.error(f"Не удалось сбросить время получения карты для пользователя {user_id}.")

    def give_card_to_user(self, user_id: int, card_id: int, rarity: str, amount: int = 1, source: str = 'spin') -> Dict[str, Any]:
        """
        Выдает карту пользователю, обновляет счетчики и проверяет/выдает награды за этапы.
        source: 'spin', 'reward', 'admin', 'case', 'craft' - влияет на обновление таймера кулдауна и проверку наград.
        Возвращает словарь с результатом и списком выданных наград.
        Пример: {'success': True, 'is_new': True, 'rewards': [{'type': 'coins', 'amount': 100, 'goal': 50}]}
        """
        if amount <= 0:
            return {'success': False, 'message': 'Amount must be positive'}

        rarity = rarity.lower()
        if rarity not in RARITY_CHOICES:
             return {'success': False, 'message': f'Invalid rarity: {rarity}'}

        now_utc = datetime.now(timezone.utc)
        conn = None
        try:
            conn = self.db._get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    "SELECT id, amount FROM user_cards WHERE user_id = %s AND card_id = %s FOR UPDATE",
                    (user_id, card_id)
                )
                existing_card_row = cur.fetchone()
                is_new_card_for_user = not bool(existing_card_row)
                is_duplicate_acquisition = not is_new_card_for_user

                if is_new_card_for_user:
                    cur.execute(
                        """INSERT INTO user_cards (user_id, card_id, amount, obtained_at)
                           VALUES (%s, %s, %s, %s)""",
                        (user_id, card_id, amount, now_utc)
                    )
                else:
                    new_amount = existing_card_row['amount'] + amount
                    cur.execute(
                        "UPDATE user_cards SET amount = %s, obtained_at = %s WHERE id = %s",
                        (new_amount, now_utc, existing_card_row['id'])
                    )

                duplicates_to_add_this_time = amount if is_duplicate_acquisition else 0
                cards_received_to_add = amount

                update_fields = [
                    "total_cards_received = total_cards_received + %s",
                    "total_duplicates_received = total_duplicates_received + %s"
                ]
                update_params = [cards_received_to_add, duplicates_to_add_this_time]

                # Обновляем таймер кулдауна только для 'spin' или 'buy_spin'
                sources_for_cooldown = ['spin', 'buy_spin']
                if source in sources_for_cooldown:
                    update_fields.append("last_card_received = %s")
                    update_params.append(now_utc)

                update_params.append(user_id) # For WHERE clause

                update_users_query = f"""
                    UPDATE users
                    SET {', '.join(update_fields)}
                    WHERE user_id = %s
                    RETURNING total_cards_received; -- Get NEW total after update
                """
                cur.execute(update_users_query, tuple(update_params))
                result = cur.fetchone()
                if result is None:
                    raise Exception(f"Пользователь {user_id} не найден при обновлении счетчиков.")

                new_total_received = result['total_cards_received']
                old_total_received = new_total_received - cards_received_to_add

                rewards_granted_list = []
                total_coins_reward = 0
                total_shards_reward = 0

                # Проверяем награды за этапы только для 'spin' или 'buy_spin'
                if source in sources_for_cooldown:
                    for goal, coins_reward, shards_reward in reward_levels:
                        if old_total_received < goal <= new_total_received:
                            logging.info(f"User {user_id} reached milestone {goal} cards (from {old_total_received} to {new_total_received})")
                            if coins_reward > 0:
                                 total_coins_reward += coins_reward
                                 rewards_granted_list.append({'type': 'coins', 'amount': coins_reward, 'goal': goal})
                            if shards_reward > 0:
                                total_shards_reward += shards_reward
                                rewards_granted_list.append({'type': 'shards', 'amount': shards_reward, 'goal': goal})

                # Применяем награды (если есть)
                if total_coins_reward > 0:
                    if not self.user_manager.add_coins(user_id, total_coins_reward):
                         raise Exception(f"Не удалось начислить {total_coins_reward} монет пользователю {user_id} в транзакции.")
                    logging.info(f"Начислено {total_coins_reward} монет пользователю {user_id} за достижение.")

                if total_shards_reward > 0:
                    if not self.user_manager.add_shards(user_id, total_shards_reward, cursor=cur):
                         raise Exception(f"Не удалось начислить {total_shards_reward} осколков пользователю {user_id} в транзакции.")
                    logging.info(f"Начислено {total_shards_reward} осколков пользователю {user_id} за достижение.")

                conn.commit()
                logging.info(f"Карта ID {card_id} ({amount} шт.) успешно выдана пользователю {user_id} (источник: {source}). Новая: {is_new_card_for_user}. Награды: {rewards_granted_list}")
                return {'success': True, 'is_new': is_new_card_for_user, 'rewards': rewards_granted_list}

        except psycopg2.Error as e:
            if conn: conn.rollback()
            logging.error(f"Ошибка psycopg2 при выдаче карты {card_id} пользователю {user_id}: {e}")
            return {'success': False, 'message': f"Ошибка базы данных: {e}"}
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"Неожиданная ошибка при выдаче карты {card_id} пользователю {user_id}: {e}", exc_info=True)
            return {'success': False, 'message': f"Внутренняя ошибка сервера: {e}"}


    def remove_card_from_user(self, user_id: int, card_id: int, amount: int = 1) -> bool:
        """Удаляет карту у пользователя или уменьшает ее количество."""
        if amount <= 0: return False
        conn = None
        try:
            conn = self.db._get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # Get current amount with row lock
                cur.execute("SELECT id, amount FROM user_cards WHERE user_id = %s AND card_id = %s FOR UPDATE", (user_id, card_id))
                existing = cur.fetchone()

                if not existing:
                    logging.warning(f"Попытка удалить карту {card_id}, которой нет у пользователя {user_id}.")
                    conn.rollback() # Release lock
                    return False
                if existing['amount'] < amount:
                    logging.warning(f"У пользователя {user_id} недостаточно карт {card_id} ({existing['amount']}) для удаления {amount} шт.")
                    conn.rollback() # Release lock
                    return False

                if existing['amount'] > amount:
                    # Decrease amount
                    cur.execute("UPDATE user_cards SET amount = amount - %s WHERE id = %s", (amount, existing['id']))
                    logging.info(f"Уменьшено количество карты {card_id} на {amount} у пользователя {user_id}.")
                else:
                    # Remove entry completely
                    cur.execute("DELETE FROM user_cards WHERE id = %s", (existing['id'],))
                    logging.info(f"Удалена карта {card_id} у пользователя {user_id}.")
                conn.commit()
                return True
        except psycopg2.Error as e:
            if conn: conn.rollback()
            logging.error(f"Ошибка psycopg2 при удалении карты {card_id} у пользователя {user_id}: {e}")
            return False
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"Неожиданная ошибка при удалении карты {card_id} у пользователя {user_id}: {e}")
            return False

    def get_random_card(self, user_id: Optional[int] = None, exclude_received: bool = False) -> Optional[Dict[str, Any]]:
        """
        Возвращает случайную карту с учетом веса редкости.
        exclude_received: Если True, пытается вернуть карту, которой у пользователя еще НЕТ (amount=0).
                          Если таких нет, возвращает любую случайную карту.
        """
        params = []
        base_query = "SELECT * FROM cards"
        possible_cards = []

        if exclude_received and user_id is not None:
            query_new = base_query + " WHERE id NOT IN (SELECT card_id FROM user_cards WHERE user_id = %s)"
            params.append(user_id)
            possible_cards = self.db.execute(query_new, tuple(params), fetch='all')

        if not possible_cards:
            if exclude_received and user_id is not None:
                 logging.debug(f"User {user_id} has received all unique cards, selecting from all cards now.")
            possible_cards = self.db.execute(base_query, fetch='all')

        if not possible_cards:
            logging.warning("В базе данных нет карт для выбора.")
            return None

        try:
             weights = [max(1, RARITY_WEIGHTS.get(card['rarity'].lower(), 1)) for card in possible_cards]
             if sum(weights) <= 0:
                  logging.error("Недопустимые веса для выбора случайной карты. Сумма весов <= 0.")
                  chosen_card = random.choice(possible_cards)
             else:
                  chosen_card = random.choices(possible_cards, weights=weights, k=1)[0]
             return dict(chosen_card)
        except IndexError:
             logging.error("Ошибка при выборе случайной карты (random.choices вернул пустой список).")
             return None
        except Exception as e:
             logging.error(f"Неожиданная ошибка при взвешенном выборе карты: {e}")
             return None


    def get_user_card_counts_by_rarity(self, user_id: int) -> Dict[str, int]:
        """
        Возвращает количество УНИКАЛЬНЫХ типов карт пользователя, сгруппированное по редкости.
        """
        query = """
            SELECT c.rarity, COUNT(DISTINCT uc.card_id) as count
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = %s
            GROUP BY c.rarity;
        """
        results = self.db.execute(query, (user_id,), fetch='all')
        counts_dict = {row['rarity']: row['count'] for row in results} if results else {}

        for rarity_key in RARITY_CHOICES:
             if rarity_key not in counts_dict:
                 counts_dict[rarity_key] = 0

        return counts_dict

    def get_user_cards_ordered_by_value(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Возвращает список карт пользователя (инвентарь), отсортированный по ценности (value) по убыванию.
        """
        query = """
            SELECT c.*, uc.amount, uc.obtained_at
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = %s
            ORDER BY c.value DESC, c.id ASC;
        """
        results = self.db.execute(query, (user_id,), fetch='all')
        return [dict(row) for row in results] if results else []

    def get_user_cards_by_rarity(self, user_id: int, rarity: str) -> List[Dict[str, Any]]:
        """
        Возвращает список карт пользователя (инвентарь) указанной редкости.
        """
        rarity_lower = rarity.lower()
        if rarity_lower not in RARITY_CHOICES:
            logging.warning(f"Запрос карт с неверной редкостью: {rarity}")
            return []

        query = """
            SELECT c.*, uc.amount, uc.obtained_at
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = %s AND c.rarity = %s
            ORDER BY c.name ASC;
        """
        results = self.db.execute(query, (user_id, rarity_lower), fetch='all')
        return [dict(row) for row in results] if results else []