from typing import Union

from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery

from bot.Classes.db_manager import user_manager
from bot.card_database import SUPER_ADMIN_ID


class IsAdminFilter(Filter):
    """Проверяет, является ли пользователь администратором."""
    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        if not event.from_user: return False
        return user_manager.is_admin(event.from_user.id)

class IsSuperAdminFilter(Filter):
    """Проверяет, является ли пользователь Супер Администратором."""
    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        if not event.from_user: return False
        if SUPER_ADMIN_ID == 0:
             # Log only once or less frequently if needed
             # logging.warning("SUPER_ADMIN_ID не установлен (равен 0). Фильтр IsSuperAdminFilter не будет работать.")
             return False
        return event.from_user.id in SUPER_ADMIN_ID