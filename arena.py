import asyncio
from collections import deque
from aiogram import Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

def remove_from_queue(user_id: int):
    global matchmaking_queue
    matchmaking_queue = deque(entry for entry in matchmaking_queue if entry[0] != user_id)

matchmaking_queue = deque()
matchmaking_lock = asyncio.Lock()
# Словарь для хранения сообщений "Ожидание..." для возможности их удаления/изменения
waiting_messages = {}

# --- Клавиатура для поиска ---
find_opponent_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="⚔️ Найти соперника", callback_data="find_opponent")]
])

pvp_router = Router()

@pvp_router.callback_query(F.data == "find_opponent")
async def find_opponent_callback(callback: CallbackQuery, state: FSMContext, bot: Bot, db_manager: 'DatabaseManager', user_manager: 'UserManager', task_manager: 'TaskManager'): # Добавь нужные менеджеры
    user_id = callback.from_user.id
    user_name = html.escape(callback.from_user.first_name or "Боец")

    await callback.answer("Ищем соперника...") # Ответ на нажатие кнопки

    async with matchmaking_lock:
        if user_id in [u_id for u_id, u_name in matchmaking_queue]:
             await callback.message.edit_text("Вы уже в очереди!") # Редактируем исходное сообщение
             return

        if matchmaking_queue:
            # --- Найден соперник ---
            opponent_id, opponent_name = matchmaking_queue.popleft() # Берем первого из очереди

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

            print(f"Match found: {user_id} ({user_name}) vs {opponent_id} ({opponent_name})")
            # --- Начинаем бой ---
            await start_battle(user_id, opponent_id, user_name, opponent_name, state, bot, db_manager)

        else:
            # --- Добавляем в очередь ---
            matchmaking_queue.append((user_id, user_name))
            # Сохраняем ID сообщения для возможности его удаления
            msg = await callback.message.edit_text("⏳ Поиск соперника... Ожидайте.")
            waiting_messages[user_id] = msg.message_id
            print(f"User {user_id} ({user_name}) added to matchmaking queue.")

            # TODO: Добавить таймаут ожидания? (например, через asyncio.sleep и проверку)


async def start_battle(p1_id: int, p2_id: int, p1_name: str, p2_name: str, state: FSMContext, bot: Bot, db_manager: 'DatabaseManager'):
    # Получаем статы (используя заглушки)
    p1_atk = await get_user_atk(p1_id, db_manager)
    p1_hp = await get_user_hp(p1_id, db_manager)
    p2_atk = await get_user_atk(p2_id, db_manager)
    p2_hp = await get_user_hp(p2_id, db_manager)

    print(f"Starting battle: P1({p1_name} {p1_hp}HP {p1_atk}ATK) vs P2({p2_name} {p2_hp}HP {p2_atk}ATK)")

    # --- Проверка на мгновенную победу ---
    p1_wins_instantly = p1_atk >= p2_hp
    p2_wins_instantly = p2_atk >= p1_hp

    if p1_wins_instantly and p2_wins_instantly:
        # Ничья или кто первый ударил? Для простоты - ничья, без наград/статистики
        await bot.send_message(p1_id, f"⚔️ Битва с {p2_name}!\nМгновенная ничья! Оба игрока слишком сильны!")
        await bot.send_message(p2_id, f"⚔️ Битва с {p1_name}!\nМгновенная ничья! Оба игрока слишком сильны!")
        print("Instant draw.")
        return # Завершаем без статистики
    elif p1_wins_instantly:
        print(f"{p1_name} wins instantly.")
        battle_data = { # Данные для сообщения о результате
            "p1_id": p1_id, "p2_id": p2_id, "p1_name": p1_name, "p2_name": p2_name,
            "p1_atk": p1_atk, "p2_atk": p2_atk, "initial_p1_hp": p1_hp, "initial_p2_hp": p2_hp,
            "final_p1_hp": p1_hp, "final_p2_hp": 0, # Проигравший на 0 хп
            "damage_dealt_by_winner": p1_atk, "damage_dealt_by_loser": 0, "rounds": 1
        }
        await end_battle(p1_id, p2_id, state, bot, db_manager, user_manager, battle_data) # user_manager нужен для наград
        return
    elif p2_wins_instantly:
        print(f"{p2_name} wins instantly.")
        battle_data = {
             "p1_id": p1_id, "p2_id": p2_id, "p1_name": p1_name, "p2_name": p2_name,
            "p1_atk": p1_atk, "p2_atk": p2_atk, "initial_p1_hp": p1_hp, "initial_p2_hp": p2_hp,
            "final_p1_hp": 0, "final_p2_hp": p2_hp,
            "damage_dealt_by_winner": p2_atk, "damage_dealt_by_loser": 0, "rounds": 1
        }
        await end_battle(p2_id, p1_id, state, bot, db_manager, user_manager, battle_data)
        return

    # --- Мгновенной победы нет, начинаем бой ---
    # Определяем, кто ходит первым (случайно)
    first_turn_player_id = choice([p1_id, p2_id])
    print(f"First turn: Player ID {first_turn_player_id}")

    # --- Сохраняем начальное состояние боя в FSM для ОБОИХ игроков ---
    initial_battle_data = {
        "opponent_id": p2_id, # Удобно хранить ID оппонента
        "opponent_name": p2_name,
        "my_hp": p1_hp,
        "my_atk": p1_atk,
        "opponent_hp": p2_hp,
        "opponent_atk": p2_atk,
        "current_turn": first_turn_player_id,
        "round": 1,
        "initial_my_hp": p1_hp, # Для финального сообщения
        "initial_opponent_hp": p2_hp,
        "total_my_damage": 0, # Суммарный урон
        "total_opponent_damage": 0,
        "last_log_message": None # Для истории боя
    }
    # Используем set_state для обоих, передавая user_id
    await state.storage.set_state(key=f'fsm:{p1_id}:{p1_id}', state=BattleState.InBattle) # Ключ: fsm:user_id:chat_id (chat_id=user_id для ЛС)
    await state.storage.set_data(key=f'fsm:{p1_id}:{p1_id}', data=initial_battle_data)

    # Состояние для второго игрока (зеркальное)
    initial_battle_data_p2 = initial_battle_data.copy()
    initial_battle_data_p2["opponent_id"] = p1_id
    initial_battle_data_p2["opponent_name"] = p1_name
    initial_battle_data_p2["my_hp"] = p2_hp
    initial_battle_data_p2["my_atk"] = p2_atk
    initial_battle_data_p2["opponent_hp"] = p1_hp
    initial_battle_data_p2["opponent_atk"] = p1_atk
    initial_battle_data_p2["initial_my_hp"] = p2_hp
    initial_battle_data_p2["initial_opponent_hp"] = p1_hp

    await state.storage.set_state(key=f'fsm:{p2_id}:{p2_id}', state=BattleState.InBattle)
    await state.storage.set_data(key=f'fsm:{p2_id}:{p2_id}', data=initial_battle_data_p2)

    # --- Отправляем сообщения и кнопки ---
    await send_battle_turn_message(first_turn_player_id, state, bot)
    # Сообщаем другому игроку, что ход не его
    other_player_id = p2_id if first_turn_player_id == p1_id else p1_id
    await send_battle_turn_message(other_player_id, state, bot) # Функция сама определит, чей ход
