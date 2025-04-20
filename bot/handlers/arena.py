from collections import deque
import asyncio
from random import choice

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import StatesGroup, State

from bot.Classes.CommandManager import RARITY_EMOJIS
from bot.card_database import rarity_translate
from bot.common import bot
from aiogram.fsm.storage.base import StorageKey

from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram import Router

from bot.handlers.mainMenu import back_button, create_back_button
from bot.Classes.db_manager import task_manager, user_manager, command_manager, card_manager

arena_handler = Router()


class BattleState(StatesGroup):
    InBattle = State()

BATTLE_REWARD_SHARDS = 10

CARDS_PER_PAGE = 4


matchmaking_queue = deque()
matchmaking_lock = asyncio.Lock()
# Словарь для хранения сообщений "Ожидание..." для возможности их удаления/изменения
waiting_messages = {}

@arena_handler.callback_query(F.data == "find_opponent")
async def find_opponent_callback(callback: CallbackQuery, state: FSMContext): # Добавь нужные менеджеры
    user_id = callback.from_user.id
    user_name = callback.from_user.username

    await callback.answer("Ищем соперника...") # Ответ на нажатие кнопки

    async with matchmaking_lock:
        if user_id in [u_id for u_id, u_name, _ in matchmaking_queue]:
             await callback.message.edit_text("Вы уже в очереди!") # Редактируем исходное сообщение
             return

        if matchmaking_queue:
            # --- Найден соперник ---
            opponent_id, opponent_name, opponent_chat_id = matchmaking_queue.popleft() # Берем первого из очереди

            # Удаляем сообщения об ожидании, если они были
            if opponent_id in waiting_messages:
                try:
                    await bot.delete_message(chat_id=opponent_id, message_id=waiting_messages.pop(opponent_id))
                except Exception as e: print(f"Не удалось удалить сообщение ожидания для {opponent_id}: {e}")
            if user_id in waiting_messages: # На случай, если пользователь нажал дважды быстро
                try:
                    await bot.delete_message(chat_id=user_id, message_id=waiting_messages.pop(user_id))
                except Exception as e: print(f"Не удалось удалить сообщение ожидания для {user_id}: {e}")


            # Сообщаем об успехе (можно убрать или изменить)
            # await callback.message.edit_text(f"Найден соперник: {opponent_name}!") # Редактируем сообщение нажавшего
            # await bot.send_message(opponent_id, f"Найден соперник: {user_name}!") # Отправляем другому
            await callback.message.answer("⏳ Поиск соперника... Ожидайте.")

            await start_battle(user_id, opponent_id, callback.message.chat.id, opponent_chat_id, user_name, opponent_name, state)

        else:
            # --- Добавляем в очередь ---
            matchmaking_queue.append((user_id, user_name, callback.message.chat.id))
            # Сохраняем ID сообщения для возможности его удаления
            msg = await callback.message.answer("⏳ Поиск соперника... Ожидайте.", reply_markup=create_back_button("cancel_match"))
            waiting_messages[user_id] = msg.message_id
            print(f"User {user_id} ({user_name}) added to matchmaking queue.")

async def start_battle(user_id, opponent_id, user_chat_id, opponent_chat_id, user_name, opponent_name, state):
    # TODO: Доделать собственно
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔ Атаковать", callback_data="battle_attack"),
            InlineKeyboardButton(text="▶️ Пропустить", callback_data="battle_skip")
        ]
    ])
    
    p1_key = StorageKey(bot_id=bot.id, chat_id=user_chat_id, user_id=user_id)
    p2_key = StorageKey(bot_id=bot.id, chat_id=opponent_chat_id, user_id=opponent_id)
    
    user_data = command_manager.get_team_stats(user_id)
    opponent_data = command_manager.get_team_stats(opponent_id)

    p1_wins_instantly = user_data.attack >= opponent_data.health
    p2_wins_instantly = opponent_data.attack >= user_data.health

    if p1_wins_instantly and p2_wins_instantly:
        # Ничья или кто первый ударил? Для простоты - ничья, без наград/статистики
        await bot.send_message(user_id, f"⚔️ Битва с {opponent_name}!\nМгновенная ничья! Оба игрока слишком сильны!")
        await bot.send_message(opponent_id, f"⚔️ Битва с {user_name}!\nМгновенная ничья! Оба игрока слишком сильны!")
        return  # Завершаем без статистики
    elif p1_wins_instantly:
        battle_data = {  # Данные для сообщения о результате
            "p1_id": user_id, "p2_id": opponent_id, "p1_name": user_name, "p2_name": opponent_name,
            "p1_atk": user_data.attack, "p2_atk": opponent_data.attack, "initial_p1_hp": user_data.health, "initial_p2_hp": opponent_data.health,
            "final_p1_hp": user_data.health, "final_p2_hp": 0,  # Проигравший на 0 хп
            "damage_dealt_by_winner": user_data.attack, "damage_dealt_by_loser": 0, "rounds": 1
        }
        await end_battle(user_id, opponent_id, state, p1_key, p2_key, battle_data)  # user_manager нужен для наград
        return
    elif p2_wins_instantly:
        battle_data = {
            "p1_id": user_id, "p2_id": opponent_id, "p1_name": user_name, "p2_name": opponent_name,
            "p1_atk": user_data.attack, "p2_atk": opponent_data.attack, "initial_p1_hp": user_data.health, "initial_p2_hp": opponent_data.health,
            "final_p1_hp": 0, "final_p2_hp": opponent_data.health,
            "damage_dealt_by_winner": opponent_data.attack, "damage_dealt_by_loser": 0, "rounds": 1
        }
        await end_battle(opponent_id, user_id, state, p2_key, p1_key, battle_data)
        return

    first_turn_player_id = choice([user_id, opponent_id])

    initial_battle_data = {
        "opponent_id": opponent_id,
        "opponent_chat_id": opponent_chat_id,
        "opponent_name": opponent_name,
        "my_hp": user_data.health,
        "my_atk": user_data.attack,
        "opponent_hp": opponent_data.health,
        "opponent_atk": opponent_data.attack,
        "current_turn": first_turn_player_id,
        "round": 1,
        "initial_my_hp": user_data.health,
        "initial_opponent_hp": opponent_data.health,
        "total_my_damage": 0,
        "total_opponent_damage": 0,
        "last_log_message": None
    }

    await state.storage.set_state(key=p1_key, state=BattleState.InBattle)
    await state.storage.set_data(key=p1_key, data=initial_battle_data)

    # Зеркальные данные для оппонента
    initial_battle_data_opponent = {
        "opponent_id": user_id,
        "opponent_chat_id": user_chat_id,
        "opponent_name": user_name,
        "my_hp": opponent_data.health,
        "my_atk": opponent_data.attack,
        "opponent_hp": user_data.health,
        "opponent_atk": user_data.attack,
        "current_turn": first_turn_player_id,
        "round": 1,
        "initial_my_hp": opponent_data.health,
        "initial_opponent_hp": user_data.health,
        "total_my_damage": 0,
        "total_opponent_damage": 0,
        "last_log_message": None
    }

    await state.storage.set_state(key=p2_key, state=BattleState.InBattle)
    await state.storage.set_data(key=p2_key, data=initial_battle_data_opponent)

    await send_battle_turn_message(user_id, p1_key, state)
    await send_battle_turn_message(opponent_id, p2_key, state)  # Функция сама определит, чей ход

def get_battle_keyboard(my_turn: bool, opponent_id: int) -> InlineKeyboardMarkup:
    if not my_turn: # Если не наш ход, кнопок нет
        buttons = [
            [InlineKeyboardButton(text="⏳ Ждите своего хода", callback_data=f"wait")]
        ]
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    buttons = [
        [InlineKeyboardButton(text="⚔️ Атака", callback_data=f"battle_attack:{opponent_id}")],
        [InlineKeyboardButton(text="⏳ Пропустить", callback_data=f"battle_skip:{opponent_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def send_battle_turn_message(user_id: int, key: StorageKey, state: FSMContext,):
    # Получаем текущее состояние боя для этого игрока
    user_state_data = await state.storage.get_data(key=key)
    if not user_state_data: return  # Состояния нет

    my_turn = user_state_data['current_turn'] == user_id
    my_hp = user_state_data['my_hp']
    opponent_hp = user_state_data['opponent_hp']
    opponent_name = user_state_data['opponent_name']
    opponent_id = user_state_data['opponent_id']
    round_num = user_state_data['round']

    text = (
        f"⛩️ Раунд {round_num}\n\n"
        f"👤 {opponent_name}: ❤️{opponent_hp}\n"
        f"🙍‍♂️ Вы: ❤️{my_hp}\n\n"
    )
    if my_turn:
        text += "🔥 Ваш ход!"
    else:
        text += f"⏳ Ожидание хода {opponent_name}..."

    keyboard = get_battle_keyboard(my_turn, opponent_id)

    # Пытаемся отредактировать предыдущее сообщение боя, если возможно
    # Нужно хранить message_id в FSM или использовать edit_message_text по callback.message
    # Для простоты пока отправляем новое сообщение
    await bot.send_message(user_id, text, reply_markup=keyboard)

async def end_battle(winner_id: int, loser_id: int, state: FSMContext, winner_key: StorageKey, loser_key: StorageKey, battle_data: dict):
    winner_name = battle_data['p1_name'] if battle_data['p1_id'] == winner_id else battle_data['p2_name']
    loser_name = battle_data['p2_name'] if battle_data['p1_id'] == winner_id else battle_data['p1_name']

    # todo засчитывание победы в статистику
    # try:
    #     with conn.cursor() as cur:
    #         # Увеличиваем победы победителю
    #         cur.execute("UPDATE users SET season_wins = season_wins + 1 WHERE user_id = %s", (winner_id,))
    #         # Увеличиваем поражения проигравшему
    #         cur.execute("UPDATE users SET season_losses = season_losses + 1 WHERE user_id = %s", (loser_id,))
    #         # Выдаем награду победителю
    #         user_manager.add_shards(winner_id, BATTLE_REWARD_SHARDS, cursor=cur)
    #     conn.commit()
    #     print(f"Stats updated for battle between {winner_id} and {loser_id}")
    # except Exception as e:
    #     conn.rollback()
    #     print(f"Error updating stats/rewards after battle: {e}")

    # --- Формируем финальное сообщение ---
    # Определяем, кто был P1, кто P2 в терминах battle_data
    p1_data_key = 'p1' if battle_data['p1_id'] == winner_id else 'p2'
    p2_data_key = 'p2' if battle_data['p1_id'] == winner_id else 'p1'

    winner_log_name = battle_data[f'{p1_data_key}_name']
    loser_log_name = battle_data[f'{p2_data_key}_name']
    winner_damage = battle_data['damage_dealt_by_winner']
    loser_damage = battle_data['damage_dealt_by_loser']
    loser_hp_before = battle_data[f'initial_{p2_data_key}_hp']
    loser_hp_after = battle_data[f'final_{p2_data_key}_hp'] # Должен быть <= 0
    winner_hp_final = battle_data[f'final_{p1_data_key}_hp'] # ХП победителя
    rounds = battle_data['rounds']

    # Ссылка на профиль проигравшего (для победителя)
    loser_tg_link = f"(tg://user?id={loser_id})" # Было tg://openmessage?user_id={loser_id}, но tg://user стандартнее

    result_message = f"""
🌄🌋 Сражение между игроками {winner_name} и {loser_name} {loser_tg_link}

✨ Победа! ✨

🙍‍♂️ {winner_name} (❤️{winner_hp_final})
\t\t┗⊳ Наносит ⚔️{winner_damage} урона

👤 {loser_name}
\t\t┗⊳〘💔{loser_hp_before}〙➠〘☠️{max(0, loser_hp_after)}〙

🗡️ Всего урона нанесено: {winner_damage}
🦴 Урона получено: {loser_damage}
⛩️ Всего раундов: {rounds}

🌺 Держи свою награду за победу
\t +{BATTLE_REWARD_SHARDS}🀄️ осколка
"""

    # --- Отправляем результат и сохраняем лог ---
    try:
        await bot.send_message(winner_id, result_message)
        # Отправляем проигравшему немного измененное сообщение
        result_message_loser = result_message.replace(f"✨ Победа! ✨", "🚫 Поражение! 🚫")
        result_message_loser = result_message_loser.replace("🌺 Держи свою награду за победу", " ") # Убираем строку с наградой
        result_message_loser = result_message_loser.replace(f"\t +{BATTLE_REWARD_SHARDS}🀄️ осколка", "")
        await bot.send_message(loser_id, result_message_loser)

        # Сохраняем лог в FSM (для команды /lastbattle)
        await state.storage.update_data(key=winner_key, data={"last_log_message": result_message})
        await state.storage.update_data(key=loser_key, data={"last_log_message": result_message_loser})

    except Exception as e:
        print(f"Error sending final battle messages: {e}")

    # --- Очищаем состояние FSM для обоих игроков ---
    await state.storage.set_state(key=winner_key, state=None)
    await state.storage.set_state(key=loser_key, state=None)
    # Данные можно не чистить явно, если используем MemoryStorage, но для Redis лучше чистить
    # await state.storage.set_data(key=f'fsm:{winner_id}:{winner_id}', data={})
    # await state.storage.set_data(key=f'fsm:{loser_id}:{loser_id}', data={})
    print(f"FSM state cleared for users {winner_id} and {loser_id}")


@arena_handler.callback_query(F.data.startswith("cancel_match"))
async def show_rarity_cards(call: CallbackQuery):
    remove_from_queue(call.from_user.id)
    await call.message.edit_text("❌ Матч отменен")

@arena_handler.callback_query(F.data == "arena")
async def show_arena_menu(call: CallbackQuery):
    user_name = call.from_user.first_name
    team = command_manager.format_user_team(call.from_user.id)
    all_stats = command_manager.get_team_stats(call.from_user.id)

    attack = all_stats.attack
    health = all_stats.health

    team_text = (f"┏➤{team[0][0]} {team[0][1]}\n"
                 f"┣➤{team[1][0]} {team[1][1]}\n"
                 f"┣➤{team[2][0]} {team[2][1]}\n"
                 f"┣➤{team[3][0]} {team[3][1]}\n"
                 f"┗➤{team[4][0]} {team[4][1]}")

    text = (
        f"👾 <b>{user_name}</b>, ты можешь собрать команду из карт и сражаться с другими игроками\n\n"
        f"🤜 <b>Твоя команда</b>\n"
        f"{team_text}\n\n"
        f"🗡️ Атака: {attack}\n"
        f"❤️ Здоровье: {health}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Найти противника", callback_data="find_opponent")],
            [
                InlineKeyboardButton(text="🎴 Команда", callback_data="arena_team"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="arena_stats")
            ],
            [
                InlineKeyboardButton(text="🏆 Турнир", callback_data="arena_tournament"),
                InlineKeyboardButton(text="👾 Босс", callback_data="arena_boss")
            ],
            [back_button("menu")]
        ]
    )

    await call.message.edit_text(text, reply_markup=keyboard)

@arena_handler.callback_query(F.data.startswith("battle_attack:"), BattleState.InBattle)
async def battle_attack_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    target_opponent_id = int(callback.data.split(":")[1])

    p1_key = StorageKey(bot_id=bot.id, chat_id=callback.message.chat.id, user_id=user_id)

    attacker_data = await state.storage.get_data(p1_key)

    p2_key = StorageKey(bot_id=bot.id, chat_id=attacker_data.get("opponent_chat_id"), user_id=attacker_data.get("opponent_id"))


    # Проверки
    if not attacker_data: return await callback.answer("Ошибка: Состояние боя не найдено.", show_alert=True)
    if attacker_data['current_turn'] != user_id: return await callback.answer("Сейчас не ваш ход!", show_alert=True)
    if attacker_data['opponent_id'] != target_opponent_id: return await callback.answer("Ошибка: Неверная цель атаки.", show_alert=True)

    await callback.answer("Атакуем...") # Ответ на кнопку

    # Данные для обновления
    defender_id = target_opponent_id
    damage = attacker_data['my_atk']
    attacker_data['total_my_damage'] += damage # Обновляем суммарный урон

    # Получаем состояние защищающегося, чтобы обновить его HP
    defender_data = await state.storage.get_data(key=p2_key)
    if not defender_data: return # Ошибка, бой должен прекратиться?

    new_defender_hp = defender_data['my_hp'] - damage
    defender_data['my_hp'] = new_defender_hp
    defender_data['total_opponent_damage'] += damage # Урон, полученный защищающимся

    # Обновляем данные FSM для обоих
    await state.storage.set_data(key=p1_key, data=attacker_data)
    await state.storage.set_data(key=p2_key, data=defender_data)

    # --- Проверяем конец боя ---
    if new_defender_hp <= 0:
        print(f"Battle end: {user_id} defeated {defender_id}")
        # Собираем финальные данные
        final_data = {
            "p1_id": user_id, "p2_id": defender_id,
            "p1_name": callback.from_user.first_name, # Получаем имена снова или храним в FSM
            "p2_name": defender_data['opponent_name'],
            "p1_atk": attacker_data['my_atk'], "p2_atk": defender_data['my_atk'],
            "initial_p1_hp": attacker_data['initial_my_hp'], "initial_p2_hp": defender_data['initial_my_hp'],
            "final_p1_hp": attacker_data['my_hp'], "final_p2_hp": max(0, new_defender_hp), # Не уходим в минус в логе
            "damage_dealt_by_winner": attacker_data['total_my_damage'],
            "damage_dealt_by_loser": defender_data['total_my_damage'],
            "rounds": attacker_data['round']
        }
        await end_battle(user_id, defender_id, state, p1_key, p2_key, final_data)
    else:
        # --- Бой продолжается, передаем ход ---
        attacker_data['current_turn'] = defender_id
        defender_data['current_turn'] = defender_id # Оба знают, чей ход
        # Увеличиваем раунд, если ход вернулся к P1 (или просто после хода P2)
        # Проще увеличивать каждый раз, когда ходит второй игрок
        # Или после каждого хода p2
        if attacker_data['opponent_id'] == defender_id: # Если p2 ходил
             defender_data['round'] += 1
             attacker_data['round'] = defender_data['round'] # Синхронизируем раунд


        # Обновляем данные FSM
        await state.storage.set_data(key=p1_key, data=attacker_data)
        await state.storage.set_data(key=p2_key, data=defender_data)

        # Обновляем сообщения для обоих игроков
        await send_battle_turn_message(user_id, p1_key, state)
        await send_battle_turn_message(defender_id, p2_key, state)


@arena_handler.callback_query(F.data.startswith("battle_skip:"), BattleState.InBattle)
async def battle_skip_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    target_opponent_id = int(callback.data.split(":")[1])

    p1_key = StorageKey(bot_id=bot.id, chat_id=callback.message.chat.id, user_id=user_id)
    skipper_data = await state.storage.get_data(p1_key)

    # Проверки
    if not skipper_data: return await callback.answer("Ошибка: Состояние боя не найдено.", show_alert=True)
    if skipper_data['current_turn'] != user_id: return await callback.answer("Сейчас не ваш ход!", show_alert=True)
    if skipper_data['opponent_id'] != target_opponent_id: return await callback.answer("Ошибка: Неверная цель.", show_alert=True)

    await callback.answer("Пропускаем ход...")

    opponent_id = target_opponent_id
    opponent_data = await state.storage.get_data(key=f'fsm:{opponent_id}:{opponent_id}')
    if not opponent_data: return

    # Передаем ход
    skipper_data['current_turn'] = opponent_id
    opponent_data['current_turn'] = opponent_id
    # Увеличиваем раунд, если нужно (логика как в атаке)
    if skipper_data['opponent_id'] == opponent_id: # Если p2 ходил (пропускал)
          opponent_data['round'] += 1
          skipper_data['round'] = opponent_data['round']

    # Обновляем данные FSM
    await state.storage.set_data(key=f'fsm:{user_id}:{user_id}', data=skipper_data)
    await state.storage.set_data(key=f'fsm:{opponent_id}:{opponent_id}', data=opponent_data)

    # Обновляем сообщения для обоих игроков
    await send_battle_turn_message(user_id, state, bot)
    await send_battle_turn_message(opponent_id, state, bot)


@arena_handler.callback_query(F.data == "arena_team")
async def pick_team(call: CallbackQuery):
    await show_team_cards(call)

@arena_handler.callback_query(F.data == "arena_stats")
async def pick_team(call: CallbackQuery):
    user_data = await user_manager.get_user_info(call.from_user.id)
    # TODO: Сделать вывод статистики
    text = (
    f"📊 {user_data.nickname}, вот твоя статистика сражений\n\n"
    "📋 За этот сезон\n"
    '➖➖➖➖➖➖\n'
    f'✊ Побед: {user_data.season_wins}\n'
    f'☠️ Поражений: {user_data.season_losses}\n'
    #'🛡️ Отразил нападений: {seasonal["defended"]}'
    f'⛩️ Всего сражений: {user_data.season_wins + user_data.season_losses}\n\n'

    '📜 За всё время\n'
    '➖➖➖➖➖➖\n'
    f'✊ Побед: {user_data.all_wins}\n'
    f'☠️ Поражений: {user_data.all_losses}\n'
    #'🛡️ Отразил нападений: {total["defended"]}'
    f'⛩️ Всего сражений: {user_data.all_wins + user_data.all_losses}')
    await call.message.edit_text(text, reply_markup=create_back_button("arena"))

@arena_handler.callback_query(F.data == "arena_tournament")
async def pick_team(call: CallbackQuery):
    user_data = await user_manager.get_user_info(call.from_user.id)
    await call.message.edit_text(f"🏆 {user_data.nickname}, турнир на данный момент не протекает. Ожидай начала следующего.", reply_markup=create_back_button("arena"))

@arena_handler.callback_query(lambda c: c.data.startswith("choose_card_slot_"))
async def pick_team(call: CallbackQuery):
    user_id = call.from_user.id
    selected_slot, page = call.data.split("_")[3], call.data.split("_")[4]
    cards = card_manager.get_user_cards_ordered_by_value(user_id)
    deck = command_manager.get_user_deck(user_id)
    if deck:
        used_card_ids = {card["id"] for card in deck if card["id"] is not None}
        filtered_cards = []
        for card in cards:
            if card["id"] not in used_card_ids:
                filtered_cards.append(card)
    else:
        filtered_cards = cards
    if not cards:
        await call.message.edit_text(f"У тебя еще нет карт, получи их с помощью кнопки ниже")
        return
    await show_cards(call, filtered_cards, int(page), int(selected_slot))



async def show_cards(call, cards, page=0, selected_slot=5):


    total_pages = (len(cards) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    if total_pages == 0:
        total_pages = 1

    if page >= total_pages:
        page = 0
    elif page < 0:
        page = total_pages - 1

    # Получаем карты для текущей страницы
    page_cards = get_page_cards(cards, page)

    # Формируем текст с заголовком
    text = (
        f"🃏 Nick, выбери карту\n"
        f"➖➖➖➖➖➖\n"
        f"🛖 Выбран слот номер ➨ {selected_slot}\n"
        f"📋 Страница {page + 1} из {total_pages}\n\n"
    )

    card_buttons = []
    for i, card in enumerate(page_cards):
        card_row = [InlineKeyboardButton(
            text=f"{rarity_translate[card['rarity']][0:3]} {card['name']}",
            callback_data=f"select_card:{card['id']}:{selected_slot}"
        )]
        card_buttons.append(card_row)

    # Создаем кнопки навигации
    navigation_row = []
    if page > 0:
        navigation_row.append(InlineKeyboardButton(
            text="⬅️",
            callback_data=f"choose_card_slot_{selected_slot}_{page - 1}"
        ))

    if page < total_pages - 1:
        navigation_row.append(InlineKeyboardButton(
            text="➡️",
            callback_data=f"choose_card_slot_{selected_slot}_{page + 1}"
        ))

    # Добавляем кнопку освобождения слота
    release_slot_row = [InlineKeyboardButton(
        text="Освободить слот",
        callback_data=f"select_card:0:{selected_slot}"
    )]


    # Собираем все ряды кнопок вместе
    keyboard_rows = card_buttons + [navigation_row] + [release_slot_row] + [[back_button("arena_team")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    # Определяем, новое это сообщение или обновление


    try:
        await call.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        # Если не удалось отредактировать, отправляем новое сообщение
        await call.message.answer(text, reply_markup=keyboard)

@arena_handler.callback_query(lambda c: c.data.startswith("select_card"))
async def pick_card(call: CallbackQuery):
    _, card_id, slot = call.data.split(":")
    command_manager.assign_card_to_position(
        call.from_user.id,
        None if card_id == "0" else int(card_id),
        int(slot)
    )
    await show_team_cards(call)

async def show_team_cards(call):
    team = command_manager.format_user_team(call.from_user.id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{emoji}", callback_data=f"choose_card_slot_{i + 1}_0   ") for i, (emoji, name)
             in enumerate(team)],
            [back_button("arena")]
        ]
    )

    team_text = (f"┏➤{team[0][0]} {team[0][1]}\n"
                 f"┣➤{team[1][0]} {team[1][1]}\n"
                 f"┣➤{team[2][0]} {team[2][1]}\n"
                 f"┣➤{team[3][0]} {team[3][1]}\n"
                 f"┗➤{team[4][0]} {team[4][1]}\n")
    # team_text = "\n".join([f"┏{emoji} {name}" for emoji, name in team])

    text = (f"🏕️ Nick, чтобы собрать команду, жми на слоты ниже и выбирай карту\n\n"
    "🍤 Твоя команда\n"
    f"{team_text}")
    await call.message.edit_text(text, reply_markup=keyboard)

def get_page_cards(cards, page):
    """Получаем карты для текущей страницы"""
    start_idx = page * CARDS_PER_PAGE
    end_idx = min(start_idx + CARDS_PER_PAGE, len(cards))
    return cards[start_idx:end_idx]

def remove_from_queue(user_id: int):
    global matchmaking_queue
    matchmaking_queue = deque(entry for entry in matchmaking_queue if entry[0] != user_id)


