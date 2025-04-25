from aiogram import F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram import Router

from bot.Classes.db_manager import user_manager, card_manager, db
from bot.dev.card_generator import generate_random_cards
from bot.dev.task_utils import generate_task_variations

router = Router()


@router.message(F.text.startswith("/get_all"))
async def cmd_generate(message: Message):
    print(card_manager.get_all_cards())

@router.message(F.text == "/quest_generate")
async def questing(message: Message):
    generate_task_variations(db_manager=db, clear_existing=True)

@router.message(F.text.startswith("/generate"))
async def cmd_generate(message: Message):
    try:
        amount = message.text.split()[1]
        generate_random_cards(int(amount))
        await message.answer(f"✅ Успешно сгенерировано {amount} случайных карт!")
    except (ValueError, TypeError) as e:
        await message.answer("❌ Пожалуйста, укажи количество карт. Пример: /generate 30" + str(e))

@router.message(F.text.startswith("/give_bp"))
async def reset_last_time(message: Message):
    print(db.execute("UPDATE users SET has_battle_pass = TRUE WHERE user_id = %s", (message.from_user.id,)))
    await message.answer("Боевой пропуск выдан успешно")

@router.message(F.text.startswith("/discard_bp"))
async def reset_last_time(message: Message):
    print(db.execute("UPDATE users SET has_battle_pass = FALSE WHERE user_id = %s", (message.from_user.id,)))
    await message.answer("Боевой пропуск аннулирован")

@router.message(F.text.startswith("/drop_bd"))
async def reset_last_time(message: Message):
    await message.answer(db.drop_all_tables())

@router.message(F.text.startswith("/reset"))
async def reset_last_time(message: Message):
    card_manager.reset_last_received_time(message.from_user.id)
    await message.answer("time reset")

@router.message(F.text.startswith("/get_cards"))
async def reset_last_time(message: Message):
    if int(message.text[10:])> 100:
        await message.answer(f"Да вы ахуели сударь")
        return
    for i in range(0, int(message.text[10:])):
        card = card_manager.get_random_card(user_id=message.from_user.id, exclude_received=True)
        if card:
            card_manager.give_card_to_user(message.from_user.id, card['id'], card["rarity"])

    await message.answer(f"Отдал кровные {message.text[10:]} карт")


@router.message(Command("add"))
async def handle_add_poti_coins(message: Message):
    args = message.text.strip().split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("❌ Использование: /add <сумма>")
        return

    amount = int(args[1])
    user_id = message.from_user.id

    user_manager.add_coins(user_id, amount)
    new_balance = user_manager.get_coins(user_id)

    await message.answer(f"✅ {amount} PoTi Coin добавлено!\n💰 Новый баланс: {new_balance}")