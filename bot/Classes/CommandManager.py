from typing import List, Tuple, Dict, Optional, Union
from bot.card_database import DatabaseManager, rarity_translate, DeckProfile

RARITY_EMOJIS = {
    "обычная": ["⚪", "обычная"],
    "редкая": "🩸",
    "эпическая": "🐉",
    "легендарная": "✨",
}


class CommandManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def format_user_team(self, user_id: int) -> List[tuple[str, str]]:
        team = self.get_user_deck(user_id)
        formatted_team = [('⚪️', 'Пусто')] * 5  # Позиции 1–5 => индексы 0–4

        if team:
            for card in team:
                pos = card.get("position")
                if pos is not None and 1 <= pos <= 5:
                    index = pos - 1
                    emoji = rarity_translate[card["rarity"]][:3]
                    name = card.get("name", "Без имени")
                    formatted_team[index] = (emoji, name)

        return formatted_team

    def get_user_deck(self, user_id: int) -> Optional[List[Dict]]:
        rows = self.db.execute(
            """
            SELECT c.*, ud.position 
            FROM cards c
            JOIN user_decks ud ON c.id = ud.card_id
            WHERE ud.user_id = %s
            ORDER BY ud.position;
            """,
            (user_id,),
            fetch='all'
        )
        if rows:

            return [dict(row) for row in rows]
        else:
            return None

    # Назначить карту на позицию (вставить или обновить)
    def assign_card_to_position(self, user_id: int, card_id: int, position: int):
        self.db.execute("""
            INSERT INTO user_decks (user_id, card_id, position)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, position) DO UPDATE SET card_id = EXCLUDED.card_id;
        """, (user_id, card_id, position))


    # Удалить карту с конкретной позиции у пользователя
    def remove_card_from_position(self, user_id: int, position: int):
        self.db.execute("""
            DELETE FROM user_decks
            WHERE user_id = %s AND position = %s;
        """, (user_id, position))

    # Посчитать суммарные характеристики команды
    def get_team_stats(self, user_id: int) -> Optional[DeckProfile]:
        row = self.db.execute("""
            SELECT 
                COALESCE(SUM(c.attack), 0) as total_attack,
                COALESCE(SUM(c.health), 0) as total_health,
                COALESCE(SUM(c.value), 0) as total_value
            FROM cards c
            JOIN user_decks ud ON c.id = ud.card_id
            WHERE ud.user_id = %s;
        """, (user_id,), fetch='one')
        if row:
            deck = DeckProfile(
                attack=row["total_attack"],
                health=row["total_health"],
                value=row["total_value"]
            )
            return deck
        else: return None