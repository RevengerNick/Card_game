from typing import Optional, Tuple, Any, List, Dict

from bot.card_database import DatabaseManager


class ClanManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def create_clan(self, name: str, leader_id: int, description: Optional[str] = None) -> Optional[int]:
        """Создает новый клан и назначает пользователя лидером. Возвращает ID клана."""
        # 1. Проверить, не состоит ли лидер уже в клане
        user_info = self.db.execute("SELECT clan_id FROM users WHERE user_id = %s", (leader_id,), fetch='one')
        if user_info and user_info['clan_id'] is not None:
            print(f"Пользователь {leader_id} уже состоит в клане.")
            return None

        # 2. Создать клан
        clan_query = """
            INSERT INTO clans (name, leader_id, description) VALUES (%s, %s, %s)
            ON CONFLICT (name) DO NOTHING
            RETURNING id;
        """
        clan_result = self.db.execute(clan_query, (name, leader_id, description), fetch='one')

        if not clan_result:
            print(f"Клан с именем '{name}' уже существует или произошла ошибка.")
            # Нужно откатить транзакцию, если она была начата неявно в execute
            self.db._get_connection().rollback()
            return None

        clan_id = clan_result['id']

        # 3. Назначить пользователя лидером в таблице users
        user_update_query = "UPDATE users SET clan_id = %s, clan_role = 'leader' WHERE user_id = %s"
        self.db.execute(user_update_query, (clan_id, leader_id))
        # Коммит произойдет внутри execute user_update_query

        print(f"Клан '{name}' (ID: {clan_id}) успешно создан. Лидер: {leader_id}")
        return clan_id

    def get_clan_info(self, clan_id: int) -> Optional[Dict[str, Any]]:
        """Получает подробную информацию о клане."""
        clan_query = """
            SELECT c.*, u.username as leader_username
            FROM clans c
            LEFT JOIN users u ON c.leader_id = u.user_id
            WHERE c.id = %s;
        """
        clan = self.db.execute(clan_query, (clan_id,), fetch='one')
        if not clan:
            return None

        members_query = """
            SELECT user_id, username, rating, clan_role
            FROM users
            WHERE clan_id = %s
            ORDER BY clan_role DESC, rating DESC; -- Лидер и замы вверху, потом по рейтингу
        """
        members = self.db.execute(members_query, (clan_id,), fetch='all') or []

        deputies = [
            {"user_id": m["user_id"], "username": m["username"]}
            for m in members if m["clan_role"] == "deputy"
        ]

        # Топ-7 участников по рейтингу (исключая лидера/замов, если нужно другое поведение)
        top7_members = sorted(members, key=lambda x: x['rating'], reverse=True)[:7]

        return {
            "id": clan["id"],
            "name": clan["name"],
            "description": clan["description"],
            "points": clan["points"],
            "rank": clan["rank"],
            "leader_id": clan["leader_id"],
            "leader_username": clan["leader_username"],
            "deputies": deputies,
            "top7": [{"user_id": m["user_id"], "username": m["username"], "rating": m["rating"]} for m in top7_members],
            "members_count": len(members)
        }

    def get_top_clans(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает топ кланов по очкам."""
        query = """
            SELECT
                c.id,
                c.name,
                c.points,
                c.rank,
                (SELECT COUNT(*) FROM users u WHERE u.clan_id = c.id) as members_count
            FROM clans c
            ORDER BY c.points DESC, c.id ASC -- Добавим сортировку по ID для стабильности
            LIMIT %s;
        """
        clans = self.db.execute(query, (limit,), fetch='all')
        return [dict(clan) for clan in clans] if clans else []

    def add_user_to_clan(self, user_id: int, clan_id: int) -> bool:
        """Добавляет пользователя в клан."""
         # Проверить, не состоит ли уже в клане
        user_info = self.db.execute("SELECT clan_id FROM users WHERE user_id = %s", (user_id,), fetch='one')
        if user_info and user_info['clan_id'] is not None:
            print(f"Пользователь {user_id} уже состоит в клане.")
            return False

        query = "UPDATE users SET clan_id = %s, clan_role = 'member' WHERE user_id = %s"
        self.db.execute(query, (clan_id, user_id))
        # Проверить бы количество строк, обновленных execute, если бы он это возвращал
        return True # Упрощенно

    def remove_user_from_clan(self, user_id: int) -> bool:
        """Удаляет пользователя из клана."""
        query = "UPDATE users SET clan_id = NULL, clan_role = NULL WHERE user_id = %s"
        self.db.execute(query, (user_id,))
        # Проверить бы количество строк
        return True

    def set_clan_role(self, user_id: int, clan_id: int, role: Optional[str]) -> bool:
        """Устанавливает роль пользователя в клане (member, deputy, leader)."""
        # Проверка, что пользователь вообще в этом клане
        user_info = self.db.execute("SELECT clan_id FROM users WHERE user_id = %s", (user_id,), fetch='one')
        if not user_info or user_info['clan_id'] != clan_id:
            print(f"Пользователь {user_id} не состоит в клане {clan_id}.")
            return False

        valid_roles = ['member', 'deputy', 'leader', None] # None для удаления роли (но лучше remove_user_from_clan)
        if role not in valid_roles and role is not None:
             print(f"Недопустимая роль: {role}")
             return False

        if role is None: # Если хотят убрать роль - это равносильно удалению из клана
            return self.remove_user_from_clan(user_id)
        else:
            query = "UPDATE users SET clan_role = %s WHERE user_id = %s AND clan_id = %s"
            self.db.execute(query, (role, user_id, clan_id))
            return True

#clan_manager = ClanManager(db)