from aiogram import F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram import Router

from bot.card_database import CardDatabase, db


router = Router()


@router.message(F.text.startswith("/reset"))
async def reset_last_time(message: Message):
    db.reset_last_received_time(db, message.from_user.id)
    await message.answer("time reset")


@router.message(Command("add"))
async def handle_add_poti_coins(message: Message):
    args = message.text.strip().split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("❌ Использование: /add <сумма>")
        return

    amount = int(args[1])
    user_id = message.from_user.id

    db.add_poti_coins(user_id, amount)
    new_balance = db.get_user_poti_coins(user_id)

    await message.answer(f"✅ {amount} PoTi Coin добавлено!\n💰 Новый баланс: {new_balance}")
