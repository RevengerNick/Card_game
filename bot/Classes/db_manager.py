from bot.Classes.UserManager import UserManager
from bot.Classes.ClanManager import ClanManager
from bot.Classes.CardManager import CardManager
from bot.Classes.CommandManager import CommandManager # Assuming this is for deck/team commands
from bot.Classes.PromoManager import PromoManager
from bot.Classes.TaskManager import TaskManager
# Import CaseManager if you create it
# from bot.Classes.CaseManager import CaseManager

from bot.card_database import db # Import the single db instance

# Instantiate all managers using the shared db instance
user_manager = UserManager(db)
clan_manager = ClanManager(db)
card_manager = CardManager(db)
command_manager = CommandManager(db) # For deck management
promo_manager = PromoManager(db)
task_manager = TaskManager(db, user_manager) # TaskManager needs UserManager
# case_manager = CaseManager(db) # Instantiate if created

# You can optionally add a function to get all managers if needed elsewhere
# def get_managers():
#    return {
#        "user": user_manager,
#        "clan": clan_manager,
#        "card": card_manager,
#        "command": command_manager,
#        "promo": promo_manager,
#        "task": task_manager,
#        # "case": case_manager,
#    }
