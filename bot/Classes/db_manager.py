# bot\Classes\db_manager.py
import logging
# Import Manager Classes
from bot.Classes.UserManager import UserManager
from bot.Classes.ClanManager import ClanManager
from bot.Classes.CardManager import CardManager
from bot.Classes.CommandManager import CommandManager
from bot.Classes.PromoManager import PromoManager
from bot.Classes.TaskManager import TaskManager
from bot.Classes.CaseManager import CaseManager
from bot.Classes.BossManager import BossManager # <-- Добавлен импорт

# Import the shared DatabaseManager instance
from bot.card_database import db

# Instantiate all managers using the single db instance
try:
    user_manager = UserManager(db)
    clan_manager = ClanManager(db)
    card_manager = CardManager(db)
    command_manager = CommandManager(db) # Deck manager
    promo_manager = PromoManager(db)
    task_manager = TaskManager(db, user_manager)
    case_manager = CaseManager(db, user_manager, card_manager)
    boss_manager = BossManager(db, user_manager, command_manager) # <-- Инициализация BossManager

    logging.info("Все менеджеры (..., CaseManager, BossManager) успешно инициализированы.")

except Exception as e:
    logging.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать один или несколько менеджеров: {e}", exc_info=True)
    # Set managers to None to indicate failure
    user_manager = None
    clan_manager = None
    card_manager = None
    command_manager = None
    promo_manager = None
    task_manager = None
    case_manager = None
    boss_manager = None # <-- Устанавливаем в None при ошибке

# Optional: Function to get managers
def get_managers() -> dict:
    """Returns a dictionary of all initialized managers. Raises RuntimeError if initialization failed."""
    # Проверяем, что все менеджеры созданы
    if not all([user_manager, clan_manager, card_manager, command_manager,
               promo_manager, task_manager, case_manager, boss_manager]): # <-- Добавлена проверка boss_manager
        raise RuntimeError("Менеджеры не были успешно инициализированы.")
    return {
        "user": user_manager,
        "clan": clan_manager,
        "card": card_manager,
        "command": command_manager,
        "promo": promo_manager,
        "task": task_manager,
        "case": case_manager,
        "boss": boss_manager, # <-- Добавлен boss_manager
    }