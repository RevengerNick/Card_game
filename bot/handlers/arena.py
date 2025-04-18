from collections import deque
import asyncio

from aiogram.exceptions import TelegramBadRequest

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
        if user_id in [u_id for u_id, u_name in matchmaking_queue]:
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

            await start_battle(user_id, opponent_id, callback.message.chat.id, opponent_chat_id, user_name, opponent_name, state, db)

        else:
            # --- Добавляем в очередь ---
            matchmaking_queue.append((user_id, user_name, callback.message.chat.id))
            # Сохраняем ID сообщения для возможности его удаления
            msg = await callback.message.answer("⏳ Поиск соперника... Ожидайте.", reply_markup=create_back_button("cancel_match"))
            waiting_messages[user_id] = msg.message_id
            print(f"User {user_id} ({user_name}) added to matchmaking queue.")

async def start_battle(user_id, opponent_id, user_chat_id, opponent_chat_id, user_name, opponent_name, state, db_manager):
    # TODO: Доделать собственно
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔ Атаковать", callback_data="battle_attack"),
            InlineKeyboardButton(text="▶️ Пропустить", callback_data="battle_skip")
        ]
    ])
    p1_key = StorageKey(bot_id=bot.id, chat_id=user_chat_id, user_id=user_id)
    p2_key = StorageKey(bot_id=bot.id, chat_id=opponent_chat_id, user_id=opponent_id)

    user_data = user_manager.get_user_info(user_id)
    opponent_data = user_manager.get_user_info(opponent_id)
    battle_data = {
        "p1_id": user_id,
        "p2_id": opponent_id,
        "health_p1": health_p1,
        "health_p2": health_p2,
        "damage_p1": damage,
        "damage_p2": damage,
        "round": round_num
    }
    text = (f"🗡 <b>Сражение между игроками</b> {user_name} и {opponent_name}\n"
        f"⠀\n"
        f"✳ <b>Раунд round_num</b> ✳\n"
        f"👱‍♂️ {user_name}\n"
        f"┗ Наносит ⚔ <b>{attacker_damage} урона</b>\n"
        f"{opponent_name}\n"
        f"┗ {{[❤️{defender_hp}]}} ⟶ {{[💔{defender_hp_after}]}}\n"
        f"⠀\n"
        f"🧑‍🦱 {opponent_name}\n"
        f"┗ Наносит ⚔ <b>{defender_damage} урона</b>\n"
        f"{user_name}\n"
        f"┗ {{[❤️{attacker_hp}]}} ⟶ {{[💔{attacker_hp_after}]}}")
    await bot.send_message(user_id, "lets go")
    await bot.send_message(opponent_id, "lets go")

@arena_handler.callback_query(F.data.startswith("cancel_match"))
async def show_rarity_cards(call: CallbackQuery):
    remove_from_queue(call.from_user.id)
    await call.message.edit_text("❌ Матч отменен")

@arena_handler.callback_query(F.data == "arena")
async def show_arena_menu(call: CallbackQuery):
    user_name = call.from_user.first_name
    team = command_manager.format_user_team(call.from_user.id)
    all_stats = command_manager.get_team_stats(call.from_user.id)

    attack = all_stats.get("total_attack")
    health = all_stats.get("total_health")

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


