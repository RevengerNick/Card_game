class CaseManager:
    def __init__(self, db_manager: DatabaseManager, user_manager: UserManager, card_manager: CardManager):
        self.db = db_manager
        self.user_manager = user_manager
        self.card_manager = card_manager

    # --- create_case, delete_case, add_card_to_case, remove_card_from_case, get_case_by_id, get_case_by_name, get_all_cases, get_cards_in_case (без изменений) ---
    # Используют self.db.execute()
    def create_case(self, name: str, description: Optional[str], card_count: int, price_coins: int, price_shards: int) -> Optional[int]:
        query = "INSERT INTO card_cases (name, description, card_count, price_coins, price_shards) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (name) DO NOTHING RETURNING id;"
        result = self.db.execute(query, (name, description, card_count, price_coins, price_shards), fetch='one')
        return result['id'] if result else None
    def delete_case(self, case_id: int) -> bool:
        result = self.db.execute("DELETE FROM card_cases WHERE id = %s", (case_id,))
        return result == 1
    def add_card_to_case(self, case_id: int, card_id: int, weight: int) -> bool:
        if weight <= 0: return False
        query = "INSERT INTO case_cards (case_id, card_id, drop_weight) VALUES (%s, %s, %s) ON CONFLICT (case_id, card_id) DO UPDATE SET drop_weight = EXCLUDED.drop_weight;"
        result = self.db.execute(query, (case_id, card_id, weight))
        return result is not None # True если нет ошибки psycopg2
    def remove_card_from_case(self, case_id: int, card_id: int) -> bool:
        result = self.db.execute("DELETE FROM case_cards WHERE case_id = %s AND card_id = %s", (case_id, card_id))
        return result == 1
    def get_case_by_id(self, case_id: int) -> Optional[Dict[str, Any]]:
        return self.db.execute("SELECT * FROM card_cases WHERE id = %s", (case_id,), fetch='one')
    def get_case_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        return self.db.execute("SELECT * FROM card_cases WHERE name = %s", (name,), fetch='one')
    def get_all_cases(self) -> List[Dict[str, Any]]:
        return self.db.execute("SELECT * FROM card_cases ORDER BY price_coins, price_shards, name", fetch='all') or []
    def get_cards_in_case(self, case_id: int) -> List[Dict[str, Any]]:
        query = "SELECT c.*, cc.drop_weight FROM case_cards cc JOIN cards c ON cc.card_id = c.id WHERE cc.case_id = %s AND cc.drop_weight > 0 ORDER BY cc.drop_weight DESC, c.id;"
        return self.db.execute(query, (case_id,), fetch='all') or []


    # --- open_case (требует ручного управления транзакцией) ---
    def open_case(self, user_id: int, case_id: int) -> Tuple[Optional[List[Dict[str, Any]]], str]:
        case_info = self.get_case_by_id(case_id)
        if not case_info: return None, "Кейс не найден."

        price_coins = case_info['price_coins']; price_shards = case_info['price_shards']
        card_count = case_info['card_count']
        conn = None; had_error = False; status_message = ""; purchase_currency = None; cost = 0

        try:
            conn = self.db.get_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # 1. Проверка баланса и блокировка пользователя
                cur.execute("SELECT coins, shards FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
                balance = cur.fetchone()
                if not balance: return None, "Пользователь не найден." # Не должно произойти

                # Определяем, можно ли купить и чем
                can_afford = False
                if price_coins > 0 and balance['coins'] >= price_coins: can_afford = True; purchase_currency = 'coins'; cost = price_coins
                elif price_shards > 0 and balance['shards'] >= price_shards: can_afford = True; purchase_currency = 'shards'; cost = price_shards
                elif price_coins == 0 and price_shards == 0: can_afford = True # Бесплатный кейс
                else:
                    funds = []
                    if price_coins > 0: funds.append(f"{price_coins} 🪙")
                    if price_shards > 0: funds.append(f"{price_shards} 🀄️")
                    return None, f"Недостаточно средств. Требуется: {' или '.join(funds)}."

                # 2. Списание средств
                if purchase_currency == 'coins':
                    if not self.user_manager.spend_coins(user_id, cost, cursor=cur): raise Exception("Failed to spend coins")
                    status_message = f"Кейс '{case_info['name']}' куплен за {cost} 🪙!"
                elif purchase_currency == 'shards':
                    if not self.user_manager.spend_shards(user_id, cost, cursor=cur): raise Exception("Failed to spend shards")
                    status_message = f"Кейс '{case_info['name']}' куплен за {cost} 🀄️!"
                else: status_message = f"Открыт бесплатный кейс '{case_info['name']}'!"

                # 3. Получение пула карт
                cur.execute("SELECT c.id as card_id, c.rarity, c.name, c.attack, c.health, c.value, c.image_path, cc.drop_weight FROM case_cards cc JOIN cards c ON cc.card_id = c.id WHERE cc.case_id = %s AND cc.drop_weight > 0", (case_id,))
                potential_cards_rows = cur.fetchall()
                if not potential_cards_rows:
                    # Кейс пуст! Откатываем списание средств
                    raise Exception("Кейс пуст!") # Это приведет к rollback

                potential_cards = [dict(row) for row in potential_cards_rows]
                weights = [card['drop_weight'] for card in potential_cards]

                # 4. Выбор карт
                try: chosen_cards_data = random.choices(potential_cards, weights=weights, k=card_count)
                except Exception as e: raise Exception(f"Ошибка выбора карт: {e}")

                # 5. Выдача карт (используем CardManager.give_card_to_user с source='case')
                obtained_cards_info = []
                for card_data in chosen_cards_data:
                    # Вызываем give_card_to_user, он сам управляет своей транзакцией (или используем курсор, если он адаптирован)
                    # Упрощение: вызываем give_card_to_user, предполагая, что он не будет коммитить/откатывать общую транзакцию
                    # или используем его с курсором.
                    # --- Переделаем на прямой вызов UserManager и обновление user_cards внутри этой транзакции ---
                    card_id = card_data['card_id']
                    now_ts = datetime.now(timezone.utc)
                    query_uc = "INSERT INTO user_cards (user_id, card_id, amount, obtained_at) VALUES (%s, %s, 1, %s) ON CONFLICT (user_id, card_id) DO UPDATE SET amount = user_cards.amount + 1, obtained_at = EXCLUDED.obtained_at RETURNING xmax;"
                    cur.execute(query_uc, (user_id, card_id, now_ts))
                    res_uc = cur.fetchone()
                    if res_uc is None: raise Exception(f"Failed user_cards update for card {card_id}")
                    is_duplicate = res_uc['xmax'] != 0
                    duplicates_to_add = 1 if is_duplicate else 0
                    # Обновляем счетчики пользователя (без last_received и наград)
                    cur.execute("UPDATE users SET total_cards_received = total_cards_received + 1, total_duplicates_received = total_duplicates_received + %s WHERE user_id = %s", (duplicates_to_add, user_id))

                    obtained_cards_info.append(card_data)

            conn.commit() # Коммитим все изменения
            return obtained_cards_info, status_message

        except Exception as e:
            if conn: conn.rollback(); had_error = True
            logging.error(f"Ошибка open_case для user {user_id}, case {case_id}: {e}", exc_info=True)
            # Возвращаем специфичное сообщение об ошибке
            if "Кейс пуст!" in str(e):
                return None, "Этот кейс пуст!"
            else:
                return None, f"Ошибка БД при открытии: {e}"
        finally:
            if conn: self.db.put_connection(conn, close_on_error=had_error)