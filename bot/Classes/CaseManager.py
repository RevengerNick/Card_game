# --- START OF FILE bot\Classes\CaseManager.py ---
import random
import logging
from typing import Optional, List, Dict, Any, Tuple

from bot.card_database import DatabaseManager
# Import other managers needed
from bot.Classes.UserManager import UserManager
from bot.Classes.CardManager import CardManager # Needed to potentially get card info

import psycopg2
import psycopg2.extras # for DictCursor
from datetime import datetime, timezone

class CaseManager:
    def __init__(self, db_manager: DatabaseManager, user_manager: UserManager, card_manager: CardManager):
        self.db = db_manager
        self.user_manager = user_manager
        self.card_manager = card_manager # Store card manager instance

    def create_case(self, name: str, description: Optional[str], card_count: int, price_coins: int, price_shards: int) -> Optional[int]:
        """Creates a new card case. Returns the new case ID or None on failure/conflict."""
        if card_count <= 0 or price_coins < 0 or price_shards < 0:
            logging.error("Invalid parameters for create_case (count>0, prices>=0)")
            return None
        query = """
            INSERT INTO card_cases (name, description, card_count, price_coins, price_shards)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name) DO NOTHING
            RETURNING id;
        """
        try:
            result = self.db.execute(query, (name, description, card_count, price_coins, price_shards), fetch='one')
            if result:
                logging.info(f"Кейс '{name}' (ID: {result['id']}) успешно создан.")
                return result['id']
            else:
                logging.warning(f"Кейс с именем '{name}' уже существует. Создание пропущено.")
                # Fetch existing ID if needed
                existing = self.get_case_by_name(name)
                return existing['id'] if existing else None
        except psycopg2.Error as e:
            logging.error(f"Ошибка psycopg2 при создании кейса '{name}': {e}")
            return None
        except Exception as e:
            logging.error(f"Неожиданная ошибка при создании кейса '{name}': {e}")
            return None

    def delete_case(self, case_id: int) -> bool:
        """Deletes a case and its card associations. Returns True on success."""
        # Deleting from card_cases will CASCADE to case_cards due to FOREIGN KEY constraint
        try:
            # db.execute returns rowcount for DELETE
            rows_affected = self.db.execute("DELETE FROM card_cases WHERE id = %s", (case_id,))
            if rows_affected == 1:
                logging.info(f"Кейс ID {case_id} успешно удален.")
                return True
            elif rows_affected == 0:
                logging.warning(f"Попытка удаления несуществующего кейса ID {case_id}.")
                return False
            else:
                 # Should not happen with PRIMARY KEY delete, but log if it does
                 logging.error(f"Неожиданное количество удаленных строк ({rows_affected}) при удалении кейса ID {case_id}.")
                 return False # Indicate potential issue
        except psycopg2.Error as e:
            logging.error(f"Ошибка psycopg2 при удалении кейса ID {case_id}: {e}")
            return False
        except Exception as e:
            logging.error(f"Неожиданная ошибка при удалении кейса ID {case_id}: {e}")
            return False

    def add_card_to_case(self, case_id: int, card_id: int, weight: int) -> bool:
        """Adds or updates a card's drop weight in a specific case. Returns True on success."""
        if weight <= 0:
            logging.error("Вес выпадения карты должен быть положительным.")
            return False
        # Optional: Verify case and card exist before attempting insert/update? FK constraints handle it mostly.
        # if not self.get_case_by_id(case_id): return False
        # if not self.card_manager.get_card_by_id(card_id): return False

        query = """
            INSERT INTO case_cards (case_id, card_id, drop_weight) VALUES (%s, %s, %s)
            ON CONFLICT (case_id, card_id) DO UPDATE SET drop_weight = EXCLUDED.drop_weight;
        """
        try:
            # db.execute returns rowcount (usually 1 for insert/update) or None on error
            result = self.db.execute(query, (case_id, card_id, weight))
            if result is not None: # Check if execute succeeded (didn't return None)
                logging.info(f"Карта ID {card_id} добавлена/обновлена в кейсе ID {case_id} с весом {weight}.")
                return True
            else:
                logging.error(f"Не удалось добавить/обновить карту ID {card_id} в кейсе ID {case_id} (execute вернул None).")
                return False
        except psycopg2.Error as e:
            # Catch foreign key violations if case_id or card_id don't exist
            if isinstance(e, psycopg2.errors.ForeignKeyViolation):
                 logging.error(f"Ошибка внешнего ключа при добавлении карты {card_id} в кейс {case_id}: {e}")
            else:
                 logging.error(f"Ошибка psycopg2 при добавлении карты {card_id} в кейс {case_id}: {e}")
            return False
        except Exception as e:
            logging.error(f"Неожиданная ошибка при добавлении карты {card_id} в кейс {case_id}: {e}")
            return False

    def remove_card_from_case(self, case_id: int, card_id: int) -> bool:
        """Removes a card from a case's drop pool. Returns True on success."""
        try:
            # db.execute returns rowcount for DELETE
            rows_affected = self.db.execute("DELETE FROM case_cards WHERE case_id = %s AND card_id = %s", (case_id, card_id))
            if rows_affected == 1:
                logging.info(f"Карта ID {card_id} удалена из кейса ID {case_id}.")
                return True
            elif rows_affected == 0:
                logging.warning(f"Карта ID {card_id} не найдена в кейсе ID {case_id} для удаления.")
                return False # Not found is not an error, but action didn't happen
            else:
                logging.error(f"Неожиданное количество удаленных строк ({rows_affected}) при удалении карты {card_id} из кейса {case_id}.")
                return False
        except psycopg2.Error as e:
            logging.error(f"Ошибка psycopg2 при удалении карты {card_id} из кейса {case_id}: {e}")
            return False
        except Exception as e:
            logging.error(f"Неожиданная ошибка при удалении карты {card_id} из кейса {case_id}: {e}")
            return False

    def get_case_by_id(self, case_id: int) -> Optional[Dict[str, Any]]:
        """Gets case details by ID."""
        result = self.db.execute("SELECT * FROM card_cases WHERE id = %s", (case_id,), fetch='one')
        return dict(result) if result else None

    def get_case_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Gets case details by name (case-sensitive)."""
        result = self.db.execute("SELECT * FROM card_cases WHERE name = %s", (name,), fetch='one')
        return dict(result) if result else None

    def get_all_cases(self) -> List[Dict[str, Any]]:
        """Gets a list of all available cases, ordered."""
        results = self.db.execute("SELECT * FROM card_cases ORDER BY price_coins ASC, price_shards ASC, name ASC", fetch='all') or []
        return [dict(row) for row in results]

    def get_cards_in_case(self, case_id: int) -> List[Dict[str, Any]]:
        """Gets the list of cards and their weights within a specific case."""
        query = """
            SELECT c.*, cc.drop_weight
            FROM case_cards cc
            JOIN cards c ON cc.card_id = c.id
            WHERE cc.case_id = %s AND cc.drop_weight > 0 -- Ensure only valid weights are considered
            ORDER BY cc.drop_weight DESC, c.id ASC; -- Order for display/consistency
        """
        results = self.db.execute(query, (case_id,), fetch='all') or []
        return [dict(row) for row in results]

    def open_case(self, user_id: int, case_id: int) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        """
        Attempts to open a case for a user. Handles currency deduction and card awarding atomically.
        Returns: (list_of_obtained_card_dicts, success_message) or (None, error_message)
        """
        case_info = self.get_case_by_id(case_id)
        if not case_info:
            return None, "Кейс не найден."

        price_coins = case_info['price_coins']
        price_shards = case_info['price_shards']
        card_count = case_info['card_count']
        case_name = case_info['name']

        conn = None
        try:
            conn = self.db._get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # 1. Check balance and lock user row
                cur.execute("SELECT coins, shards FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
                balance = cur.fetchone()
                if not balance:
                    # This shouldn't happen if user exists, but good practice to check
                    conn.rollback() # Release lock
                    return None, "Пользователь не найден."

                # 2. Determine purchase currency and attempt deduction
                purchase_currency = None
                cost = 0
                status_message = ""

                if price_coins > 0 and balance['coins'] >= price_coins:
                    if self.user_manager.spend_coins(user_id, price_coins, cursor=cur):
                        purchase_currency = 'coins'
                        cost = price_coins
                        status_message = f"Кейс '{case_name}' куплен за {cost} 🪙!"
                    else: # Should not happen if balance check passed, but safety check
                        conn.rollback(); return None, "Не удалось списать монеты (ошибка баланса или БД)."
                elif price_shards > 0 and balance['shards'] >= price_shards:
                     if self.user_manager.spend_shards(user_id, price_shards, cursor=cur):
                         purchase_currency = 'shards'
                         cost = price_shards
                         status_message = f"Кейс '{case_name}' куплен за {cost} 🀄️!"
                     else:
                         conn.rollback(); return None, "Не удалось списать осколки (ошибка баланса или БД)."
                elif price_coins == 0 and price_shards == 0:
                    # Free case
                    status_message = f"Открыт бесплатный кейс '{case_name}'!"
                else:
                    # Insufficient funds
                    funds_needed = []
                    if price_coins > 0: funds_needed.append(f"{price_coins} 🪙")
                    if price_shards > 0: funds_needed.append(f"{price_shards} 🀄️")
                    required_str = ' или '.join(funds_needed)
                    conn.rollback() # Release lock
                    return None, f"Недостаточно средств. Требуется: {required_str}."

                # 3. Get potential cards from the case
                cur.execute("""
                    SELECT c.id as card_id, c.name, c.rarity, c.attack, c.health, c.value, c.image_path, cc.drop_weight
                    FROM case_cards cc
                    JOIN cards c ON cc.card_id = c.id
                    WHERE cc.case_id = %s AND cc.drop_weight > 0
                    """, (case_id,))
                potential_cards_rows = cur.fetchall()

                if not potential_cards_rows:
                    # Case is defined but contains no cards with weight > 0
                    conn.rollback() # Rollback currency deduction
                    logging.warning(f"Попытка открыть пустой кейс ID {case_id} пользователем {user_id}.")
                    return None, "Этот кейс пуст!"

                potential_cards = [dict(row) for row in potential_cards_rows]
                weights = [card['drop_weight'] for card in potential_cards]

                if sum(weights) <= 0:
                     conn.rollback()
                     logging.error(f"Сумма весов карт в кейсе {case_id} равна нулю или меньше.")
                     return None, "Ошибка конфигурации кейса (веса)."

                # 4. Choose cards randomly based on weights
                try:
                    # Ensure k is not greater than population size if choices should be unique (if needed)
                    # `random.choices` allows replacement by default, which is fine for case opening
                    chosen_cards_data = random.choices(potential_cards, weights=weights, k=card_count)
                except ValueError as e:
                    # Handle cases like k > population size if using sample, or empty population/weights
                    conn.rollback()
                    logging.error(f"Ошибка выбора карт из кейса {case_id} (k={card_count}, len={len(potential_cards)}): {e}")
                    return None, f"Ошибка при выборе карт: {e}"
                except Exception as e:
                    conn.rollback()
                    logging.error(f"Неожиданная ошибка выбора карт из кейса {case_id}: {e}")
                    return None, f"Ошибка при выборе карт: {e}"


                # 5. Award chosen cards to the user (within the transaction)
                # Use the full give_card_to_user method but pass the cursor and a specific source
                obtained_cards_info = [] # Keep track of full card info for return

                for card_data in chosen_cards_data:
                    # Call give_card_to_user, passing the cursor to ensure it runs within this transaction
                    # Use source='case' to prevent cooldown update and milestone double-triggering
                    # We assume give_card_to_user is adapted to accept a cursor and source,
                    # and will NOT commit/rollback itself when a cursor is provided.
                    # Let's simplify by directly calling user_manager methods inside the loop for this specific case.

                    card_id = card_data['card_id']
                    amount_to_add = 1 # Give one card at a time from the case draw
                    now_ts = datetime.now(timezone.utc)

                    # Update user_cards table
                    cur.execute("SELECT id, amount FROM user_cards WHERE user_id = %s AND card_id = %s FOR UPDATE", (user_id, card_id))
                    existing_card_row = cur.fetchone()
                    is_duplicate_acquisition = bool(existing_card_row)

                    if not is_duplicate_acquisition:
                         cur.execute("INSERT INTO user_cards (user_id, card_id, amount, obtained_at) VALUES (%s, %s, %s, %s)",
                                     (user_id, card_id, amount_to_add, now_ts))
                    else:
                         new_amount = existing_card_row['amount'] + amount_to_add
                         cur.execute("UPDATE user_cards SET amount = %s, obtained_at = %s WHERE id = %s",
                                     (new_amount, now_ts, existing_card_row['id']))
                    if cur.rowcount !=1:
                         raise Exception(f"Failed to update user_cards for user {user_id}, card {card_id}")


                    # Update user's total received/duplicates (important for stats, but NOT for milestones/cooldown)
                    duplicates_to_add_this_time = amount_to_add if is_duplicate_acquisition else 0
                    cur.execute("""
                        UPDATE users
                        SET total_cards_received = total_cards_received + %s,
                            total_duplicates_received = total_duplicates_received + %s
                        WHERE user_id = %s
                        """, (amount_to_add, duplicates_to_add_this_time, user_id))
                    if cur.rowcount != 1:
                        raise Exception(f"Failed to update user stats for {user_id} after case card")


                    # Add full data of the obtained card to the list to be returned
                    obtained_cards_info.append(card_data)

            # 6. Commit the entire transaction if all steps succeeded
            conn.commit()
            logging.info(f"Пользователь {user_id} успешно открыл кейс '{case_name}' (ID: {case_id}). Получено карт: {len(obtained_cards_info)}. Оплата: {cost} {purchase_currency if purchase_currency else 'free'}.")
            return obtained_cards_info, status_message

        except psycopg2.Error as e:
            if conn: conn.rollback()
            logging.error(f"Ошибка psycopg2 при открытии кейса {case_id} для пользователя {user_id}: {e}")
            # Check for specific errors like deadlock?
            # if e.pgcode == psycopg2.errorcodes.DEADLOCK_DETECTED: return None, "Ошибка блокировки, попробуйте еще раз."
            return None, f"Ошибка базы данных ({e.pgcode}) при открытии кейса."
        except Exception as e:
            if conn: conn.rollback()
            logging.error(f"Неожиданная ошибка при открытии кейса {case_id} для пользователя {user_id}: {e}", exc_info=True)
            # Specific message for empty case was handled earlier
            return None, f"Внутренняя ошибка сервера: {e}"
        # No finally block needed for connection closing, handled by db manager or main app lifecycle