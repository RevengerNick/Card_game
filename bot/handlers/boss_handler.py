# bot/handlers/boss_handler.py
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramAPIError

# Импортируем менеджеры и хелперы
from bot.Classes.db_manager import boss_manager, user_manager, command_manager
from bot.handlers.mainMenu import back_button # Используем общую кнопку Назад

boss_router = Router()

# --- Хелпер для форматирования ХП ---
def format_boss_health(current: int, max_hp: int) -> str:
    """Форматирует здоровье босса, например, в M или B."""
    if max_hp == 0: return "0/0 HP"

    def format_num(n):
        if n >= 1_000_000_000: return f"{n / 1_000_000_000:.1f}B".replace(".0B", "B")
        if n >= 1_000_000: return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
        if n >= 1_000: return f"{n / 1_000:.1f}K".replace(".0K", "K")
        return str(n)

    percentage = (current / max_hp) * 100
    # Создаем простой progress bar (можно усложнить)
    bar_len = 10
    filled_len = int(bar_len * current // max_hp)
    bar = '🟩' * filled_len + '🟥' * (bar_len - filled_len)

    return f"{bar} {format_num(current)}/{format_num(max_hp)} HP ({percentage:.1f}%)"

# --- Основной обработчик меню босса ---
@boss_router.callback_query(F.data == "arena_boss") # Перехватываем нажатие на кнопку "Босс" из меню Арены
async def show_boss_menu(call: CallbackQuery):
    user_id = call.from_user.id
    active_boss = boss_manager.get_active_boss()

    if not active_boss:
        await call.message.edit_text(
            "👾 Мировой босс сейчас отдыхает. Загляните позже!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[back_button("arena")]]) # Кнопка назад в меню арены
        )
        await call.answer()
        return

    boss_id = active_boss['id']
    boss_name = active_boss['name']
    max_hp = active_boss['max_health']
    current_hp = active_boss['current_health']
    boss_image = active_boss.get('image_path') # Получаем картинку босса, если есть

    # Получаем данные атаки пользователя
    user_team_stats = command_manager.get_team_stats(user_id)
    user_attack = user_team_stats.attack if user_team_stats else 0

    # Проверяем, атаковал ли пользователь уже этого босса
    has_attacked = boss_manager.has_user_attacked(user_id, boss_id)

    # Собираем текст сообщения
    health_display = format_boss_health(current_hp, max_hp)
    text = (
        f"👹 <b>Мировой Босс: {boss_name}</b>\n\n"
        f"{health_display}\n\n"
        f"Ваша сила атаки: ⚔️ {user_attack}\n\n"
    )
    if has_attacked:
        text += "✅ Вы уже атаковали этого босса. Ожидайте завершения битвы для получения наград."
    else:
        text += "Готовы внести свой вклад в победу?"

    # Собираем клавиатуру
    builder = InlineKeyboardBuilder()
    if not has_attacked and current_hp > 0: # Кнопка атаки только если не атаковал и босс жив
        builder.button(text="💥 Атаковать Босса!", callback_data=f"boss_attack:{boss_id}")

    builder.button(text="🏆 Топ Урона", callback_data=f"boss_top:{boss_id}")
    builder.button(text="📜 Мой урон", callback_data=f"boss_my_damage:{boss_id}")
    # builder.button(text="📜 История Боссов", callback_data="boss_history") # Можно добавить позже
    builder.row(back_button("arena")) # Кнопка назад в меню арены
    builder.adjust(1) # Располагаем кнопки по одной в строке

    # Пытаемся отправить с картинкой или редактировать текст
    try:
        if boss_image:
            # Если было текстовое сообщение, удаляем его
            if not call.message.photo:
                try: await call.message.delete()
                except Exception: pass
                await call.message.answer_photo(photo=boss_image, caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
            else: # Если уже было фото, редактируем подпись
                await call.message.edit_caption(caption=text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
             # Если было фото, но у нового босса нет, удаляем фото
             if call.message.photo:
                  try: await call.message.delete()
                  except Exception: pass
                  await call.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
             else: # Если текста и было и стало, редактируем текст
                  await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except TelegramAPIError as e:
        logging.error(f"Ошибка при отображении меню босса: {e}")
        # Fallback на отправку нового сообщения текстом
        await call.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

    await call.answer()


# --- Обработчик атаки на босса ---
@boss_router.callback_query(F.data.startswith("boss_attack:"))
async def attack_boss(call: CallbackQuery):
    user_id = call.from_user.id
    try:
        boss_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        await call.answer("Ошибка: Неверный ID босса.", show_alert=True)
        return

    # Получаем силу атаки пользователя
    user_team_stats = command_manager.get_team_stats(user_id)
    user_attack_power = user_team_stats.attack if user_team_stats else 0

    if user_attack_power <= 0:
        await call.answer("Ваша сила атаки равна нулю. Соберите команду!", show_alert=True)
        return

    await call.answer("Атакуем босса...")

    # Выполняем атаку через BossManager
    success, message, updated_boss_data = boss_manager.deal_damage(user_id, user_attack_power)

    if success:
        logging.info(f"User {user_id} attacked boss {boss_id} for {user_attack_power} damage.")
        # Обновляем сообщение меню босса, чтобы показать новый статус и убрать кнопку атаки
        await show_boss_menu(call) # Переиспользуем функцию отображения меню
        # Дополнительно отправляем сообщение о результате атаки
        await call.message.answer(message)
    else:
        logging.warning(f"User {user_id} failed to attack boss {boss_id}: {message}")
        await call.answer(message, show_alert=True)
        # Обновляем меню на случай, если причина неудачи - босс уже побежден
        await show_boss_menu(call)


# --- Обработчик топа урона ---
@boss_router.callback_query(F.data.startswith("boss_top:"))
async def show_boss_top(call: CallbackQuery):
    user_id = call.from_user.id
    try:
        boss_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        await call.answer("Ошибка: Неверный ID босса.", show_alert=True)
        return

    boss_info = boss_manager.db.execute("SELECT name FROM world_bosses WHERE id = %s", (boss_id,), fetch='one')
    if not boss_info:
        await call.answer("Босс не найден.", show_alert=True)
        return
    boss_name = boss_info['name']

    limit = 10 # Показываем топ-10
    leaderboard = boss_manager.get_boss_leaderboard(boss_id, limit=limit)

    text = f"🏆 <b>Топ-{limit} по урону\nБосс: {boss_name}</b>\n\n"
    if not leaderboard:
        text += "<i>Пока никто не атаковал этого босса.</i>"
    else:
        for entry in leaderboard:
            username = entry.get('username') or f"User_{entry['user_id']}"
            damage = entry['damage_dealt']
            rank = entry['rank']
            text += f"{rank}. {username} - ⚔️ {damage:,}\n".replace(',', ' ') # Форматируем урон

    # Добавляем информацию о текущем пользователе
    user_rank_info = boss_manager.get_user_boss_rank_and_damage(user_id, boss_id)
    text += "\n➖➖➖➖➖➖\n"
    if user_rank_info:
        text += f"👤 Ваше место: {user_rank_info['rank']} (Урон: {user_rank_info['damage_dealt']:,})\n".replace(',', ' ')
    else:
        text += "👤 Вы еще не атаковали этого босса.\n"

    # Кнопка назад к информации о боссе
    builder = InlineKeyboardBuilder()
    builder.row(back_button(f"boss_show_menu")) # Нужен обработчик для boss_show_menu или использовать arena_boss

    # Редактируем сообщение
    try:
        await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except TelegramAPIError as e:
        logging.error(f"Ошибка при отображении топа босса: {e}")
        await call.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML") # Fallback

    await call.answer()

# --- Обработчик моего урона ---
@boss_router.callback_query(F.data.startswith("boss_my_damage:"))
async def show_my_boss_damage(call: CallbackQuery):
    user_id = call.from_user.id
    try:
        boss_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        await call.answer("Ошибка: Неверный ID босса.", show_alert=True)
        return

    boss_info = boss_manager.db.execute("SELECT name FROM world_bosses WHERE id = %s", (boss_id,), fetch='one')
    if not boss_info:
        await call.answer("Босс не найден.", show_alert=True)
        return
    boss_name = boss_info['name']

    user_rank_info = boss_manager.get_user_boss_rank_and_damage(user_id, boss_id)

    if user_rank_info:
        text = (
            f"📜 <b>Ваш результат (Босс: {boss_name})</b>\n\n"
            f"⚔️ Нанесенный урон: {user_rank_info['damage_dealt']:,}\n".replace(',', ' ') +
            f"🏆 Ваше место в топе: {user_rank_info['rank']}"
        )
    else:
        text = f"📜 Вы еще не атаковали босса '{boss_name}'."

    builder = InlineKeyboardBuilder()
    builder.row(back_button(f"boss_show_menu"))

    try:
        await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except TelegramAPIError as e:
        logging.error(f"Ошибка при отображении урона пользователя по боссу: {e}")
        await call.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML") # Fallback

    await call.answer()

# --- Обработчик для возврата в меню босса ---
# Нужен, чтобы кнопка "Назад" из топа/моего урона работала
@boss_router.callback_query(F.data == "boss_show_menu")
async def back_to_boss_menu(call: CallbackQuery):
    # Просто вызываем основную функцию отображения меню босса
    await show_boss_menu(call)

# TODO: Теперь у вас есть основа для механики Мирового Босса.
# Нужно будет протестировать и, возможно, доработать логику спавна новых боссов (например,
# автоматически через asyncio.sleep после победы над предыдущим или по расписанию)
# и отправку уведомлений игрокам о наградах.