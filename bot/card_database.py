import sqlite3
import random
import string
from datetime import datetime, timedelta

from typing import Optional

from dataclasses import dataclass

@dataclass
class UserProfile:
    nickname: str
    cards_owned: int
    total_cards: int
    season_points: int
    coins: int


RARITY_WEIGHTS = {
    'common': 70,
    'rare': 40,
    'epic': 20,
    'legendary': 8,
    'mythical': 2
}

class CardDatabase:
    def __init__(self, db_path='cards.db'):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.create_tables()

    def create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                rarity TEXT NOT NULL,
                attack INTEGER NOT NULL,
                health INTEGER NOT NULL,
                value INTEGER NOT NULL,
                image_path TEXT,
                drop_weight INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS user_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                card_id INTEGER NOT NULL,
                amount INTEGER NOT NULL DEFAULT 1,
                obtained_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                registered_at TEXT NOT NULL,
                clan_id INTEGER,
                clan_role TEXT DEFAULT NULL,
                has_battle_pass INTEGER NOT NULL DEFAULT 0,
                rating INTEGER NOT NULL DEFAULT 0,
                coins INTEGER NOT NULL DEFAULT 0,
                last_card_received TEXT,
                referrals INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (clan_id) REFERENCES clans(id)
            );

            CREATE TABLE IF NOT EXISTS clans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                points INTEGER DEFAULT 0,
                rank INTEGER DEFAULT 0,
                leader_id INTEGER,
                FOREIGN KEY (leader_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS daily_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target INTEGER NOT NULL,
                reward INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_daily_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0,
                date TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (task_id) REFERENCES daily_tasks(id)
            );

            CREATE TABLE IF NOT EXISTS promo_achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                reward_amount INTEGER NOT NULL,
                uses_left INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_promos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                promo_id INTEGER NOT NULL,
                used_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (promo_id) REFERENCES promo_achievements(id)
            );
        """)
        self.conn.commit()

    def generate_promo_code(self, reward_amount: int, uses: int = 1, custom_code: str = None):
        code = custom_code or ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        try:
            self.conn.execute("""
                INSERT INTO promo_achievements (code, reward_amount, uses_left, created_at)
                VALUES (?, ?, ?, ?)
            """, (code, reward_amount, uses, datetime.utcnow().isoformat()))
            self.conn.commit()
            return code
        except sqlite3.IntegrityError:
            return None  # Код уже существует

    def check_promo_valid(self, user_id: int, code: str):
        promo = self.conn.execute("""
            SELECT * FROM promo_achievements WHERE code = ? AND uses_left > 0
        """, (code,)).fetchone()
        if not promo:
            return False, "Промокод недействителен или закончились использования."

        used = self.conn.execute("""
            SELECT 1 FROM user_promos WHERE user_id = ? AND promo_id = ?
        """, (user_id, promo['id'])).fetchone()
        if used:
            return False, "Вы уже использовали этот промокод."

        return True, promo

    def apply_promo_code(self, user_id: int, code: str):
        valid, result = self.check_promo_valid(user_id, code)
        if not valid:
            return False, result

        promo = result
        self.conn.execute("""
            INSERT INTO user_promos (user_id, promo_id, used_at)
            VALUES (?, ?, ?)
        """, (user_id, promo['id'], datetime.utcnow().isoformat()))

        self.conn.execute("""
            UPDATE promo_achievements SET uses_left = uses_left - 1 WHERE id = ?
        """, (promo['id'],))

        self.conn.execute("""
            UPDATE users SET coins = coins + ? WHERE user_id = ?
        """, (promo['reward_amount'], user_id))

        self.conn.commit()
        return True, f"Промокод успешно применён! Вы получили {promo['reward_amount']} 🪙."

    def get_active_promos(self):
        return self.conn.execute("""
            SELECT * FROM promo_achievements WHERE uses_left > 0
        """).fetchall()

    def get_used_promos_by_user(self, user_id: int):
        return self.conn.execute("""
            SELECT p.* FROM promo_achievements p
            JOIN user_promos u ON u.promo_id = p.id
            WHERE u.user_id = ?
        """, (user_id,)).fetchall()

# ---------------------- Пользователи ----------------------

    def register_user(self, user_id, username=None):
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, registered_at) VALUES (?, ?, ?)",
            (user_id, username, now)
        )
        self.conn.commit()

    def get_user_info(self, user_id: int) -> Optional[UserProfile]:
        cursor = self.conn.cursor()

        # Получаем имя пользователя и монеты
        cursor.execute("SELECT username, coins, rating FROM users WHERE user_id = ?", (user_id,))
        user_row = cursor.fetchone()
        if user_row is None:
            return None  # если пользователь не найден

        # Получаем количество карт у пользователя
        cursor.execute("SELECT COUNT(*) FROM user_cards WHERE user_id = ?", (user_id,))
        cards_owned = cursor.fetchone()[0]

        # Получаем общее количество карт
        cursor.execute("SELECT COUNT(*) FROM cards")
        total_cards = cursor.fetchone()[0]

        return UserProfile(
            nickname=user_row["username"] or "User",
            cards_owned=cards_owned,
            total_cards=total_cards,
            season_points=user_row["rating"],  # можно позже заменить, если появятся очки сезона
            coins=user_row["coins"]
        )

    def update_username(self, user_id, new_username):
        self.conn.execute(
            "UPDATE users SET username = ? WHERE user_id = ?",
            (new_username, user_id)
        )
        self.conn.commit()

    def update_rating(self, user_id, new_rating):
        self.conn.execute(
            "UPDATE users SET rating = ? WHERE user_id = ?",
            (new_rating, user_id)
        )
        self.conn.commit()

    def set_battle_pass(self, user_id, has_pass):
        self.conn.execute(
            "UPDATE users SET has_battle_pass = ? WHERE user_id = ?",
            (int(has_pass), user_id)
        )
        self.conn.commit()

    def add_referral(self, user_id):
        self.conn.execute(
            "UPDATE users SET referrals = referrals + 1 WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()

    def add_poti_coins(self, user_id, amount):
        self.conn.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
            (amount, user_id)
        )
        self.conn.commit()

    def get_user_poti_coins(self, user_id):
        result = self.conn.execute(
            "SELECT coins FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if result:
            return result['coins']
        return 0

    def spend_poti_coin(self, user_id, amount):
        current_coins = self.get_user_poti_coins(user_id)
        if current_coins >= amount:
            self.conn.execute(
                "UPDATE users SET coins = coins - ? WHERE user_id = ?",
                (amount, user_id)
            )
            self.conn.commit()
            return True
        return False


# ---------------------- Карты ----------------------

    def can_receive_card(self, user_id):
        result = self.conn.execute(
            "SELECT last_card_received FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if not result or result['last_card_received'] is None:
            return True
        last_time = datetime.fromisoformat(result['last_card_received'])
        return datetime.utcnow() - last_time >= timedelta(hours=4)

    def reset_last_received_time(self, user_id):
        new_time = datetime.utcnow() - timedelta(hours=5)
        self.conn.execute(
            "UPDATE users SET last_card_received = ? WHERE user_id = ?",
            (new_time.isoformat(), user_id)
        )
        self.conn.commit()

    def give_card_to_user(self, user_id, card_id):
        now = datetime.utcnow().isoformat()
        existing = self.conn.execute(
            "SELECT id, amount FROM user_cards WHERE user_id = ? AND card_id = ?",
            (user_id, card_id)
        ).fetchone()

        if existing:
            self.conn.execute(
                "UPDATE user_cards SET amount = amount + 1, obtained_at = ? WHERE id = ?",
                (now, existing['id'])
            )
        else:
            self.conn.execute(
                "INSERT INTO user_cards (user_id, card_id, amount, obtained_at) VALUES (?, ?, ?, ?)",
                (user_id, card_id, 1, now)
            )

        self.conn.execute(
            "UPDATE users SET last_card_received = ? WHERE user_id = ?",
            (now, user_id)
        )
        self.conn.commit()

    def get_random_card(self, user_id=None, exclude_received=True):
        query = "SELECT * FROM cards"
        params = []

        if exclude_received and user_id is not None:
            query += " WHERE id NOT IN (SELECT card_id FROM user_cards WHERE user_id = ?)"
            params.append(user_id)

        cards = self.conn.execute(query, params).fetchall()
        if not cards:
            return None

        weights = [RARITY_WEIGHTS.get(card['rarity'], 1) for card in cards]
        return random.choices(cards, weights=weights, k=1)[0]

    def remove_card_from_user(self, user_id, card_id):
        existing = self.conn.execute(
            "SELECT id, amount FROM user_cards WHERE user_id = ? AND card_id = ?",
            (user_id, card_id)
        ).fetchone()

        if existing:
            if existing['amount'] > 1:
                self.conn.execute(
                    "UPDATE user_cards SET amount = amount - 1 WHERE id = ?",
                    (existing['id'],)
                )
            else:
                self.conn.execute(
                    "DELETE FROM user_cards WHERE id = ?",
                    (existing['id'],)
                )
            self.conn.commit()

    def add_card(self, name, rarity, attack, health, value, image_path=None):
        drop_weight = RARITY_WEIGHTS.get(rarity, 1)
        self.conn.execute(
            """
            INSERT INTO cards (name, rarity, attack, health, value, image_path, drop_weight)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, rarity, attack, health, value, image_path, drop_weight)
        )
        self.conn.commit()

    def get_all_cards(self):
        return self.conn.execute("SELECT * FROM cards").fetchall()

    def get_user_cards(self, user_id):
        return self.conn.execute(
            "SELECT * FROM user_cards WHERE user_id = ?",
            (user_id,)
        ).fetchall()

    def edit_card(self, card_id, name=None, rarity=None, attack=None, health=None, value=None, image_path=None):
        card = self.conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        if not card:
            return

        name = name or card['name']
        rarity = rarity or card['rarity']
        attack = attack if attack is not None else card['attack']
        health = health if health is not None else card['health']
        value = value if value is not None else card['value']
        image_path = image_path or card['image_path']
        drop_weight = RARITY_WEIGHTS.get(rarity, 1)

        self.conn.execute(
            """
            UPDATE cards
            SET name = ?, rarity = ?, attack = ?, health = ?, value = ?, image_path = ?, drop_weight = ?
            WHERE id = ?
            """,
            (name, rarity, attack, health, value, image_path, drop_weight, card_id)
        )
        self.conn.commit()


# ---------------------- Кланы ----------------------

    def get_clan_info(self, clan_id):
        clan = self.conn.execute("SELECT * FROM clans WHERE id = ?", (clan_id,)).fetchone()
        if not clan:
            return None

        leader = self.conn.execute("SELECT username FROM users WHERE user_id = ?", (clan['leader_id'],)).fetchone()

        members = self.conn.execute(
            "SELECT user_id, username, rating, clan_role FROM users WHERE clan_id = ? ORDER BY rating DESC",
            (clan_id,)
        ).fetchall()

        deputies = [
            {"user_id": m["user_id"], "username": m["username"]}
            for m in members if m["clan_role"] == "deputy"
        ]

        return {
            "id": clan["id"],
            "name": clan["name"],
            "description": clan["description"],
            "points": clan["points"],
            "rank": clan["rank"],
            "leader": leader["username"] if leader else None,
            "deputies": deputies,
            "top7": [{"user_id": m["user_id"], "username": m["username"], "rating": m["rating"]} for m in members[:7]],
            "members_count": len(members)
        }

    def get_top_clans(self, limit=10):
        clans = self.conn.execute(
            """
            SELECT 
                c.id, 
                c.name, 
                c.points, 
                c.rank,
                (SELECT COUNT(*) FROM users u WHERE u.clan_id = c.id) as members_count
            FROM clans c
            ORDER BY c.points DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

        return [
            {
                "id": clan["id"],
                "name": clan["name"],
                "points": clan["points"],
                "rank": clan["rank"],
                "members_count": clan["members_count"]
            }
            for clan in clans
        ]

    def add_user_to_clan(self, user_id, clan_id):
        self.conn.execute(
            "UPDATE users SET clan_id = ?, clan_role = 'member' WHERE user_id = ?",
            (clan_id, user_id)
        )
        self.conn.commit()

    def promote_to_deputy(self, user_id):
        self.conn.execute(
            "UPDATE users SET clan_role = 'deputy' WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()

    def remove_user_from_clan(self, user_id):
        self.conn.execute(
            "UPDATE users SET clan_id = NULL, clan_role = NULL WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()

db = CardDatabase()
