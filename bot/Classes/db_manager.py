from bot.Classes.UserManager import UserManager
from bot.Classes.ClanManager import ClanManager
from bot.Classes.CardManager import CardManager
from bot.Classes.CommandManager import CommandManager
from bot.Classes.PromoManager import PromoManager
from bot.Classes.TaskManager import TaskManager
from bot.card_database import db

command_manager = CommandManager(db)
user_manager = UserManager(db)
card_manager = CardManager(db)
task_manager = TaskManager(db, user_manager)
clan_manager = ClanManager(db)
promo_manager = PromoManager(db)