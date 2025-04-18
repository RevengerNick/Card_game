from aiogram import Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.card_database import rarity_translate
from bot.handlers.mainMenu import back_button, create_back_button
from bot.Classes.db_manager import task_manager, user_manager, command_manager, card_manager

clan = Router()

@clan.callback_query(F.data == "clans")
async def menu_clans(call: CallbackQuery):
    user_name = call.from_user.first_name

    text = (
        f"🏰 <b><a href='tg://user?id={call.from_user.id}'>{user_name}</a></b>, "
        "ты можешь создать или вступить в клан и играть с другими игроками"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🏰 Создать клан", callback_data="create_clan")
    keyboard.button(text="🚩 Вступить в клан", callback_data="join_clan")
    keyboard.button(text="⬅️ Назад", callback_data="menu")
    keyboard.adjust(1)

    await call.message.edit_text(
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await call.answer()

@clan.callback_query(F.data == "create_clan")
async def create_clan(call: CallbackQuery):
    user_data = await user_manager.get_user_info(call.from_user.id)
    if user_data.has_battle_pass:
        print("yes")
    else:
        await call.message.edit_text(f"🔒🔑 <b><a href='tg://user?id={call.from_user.id}'>{call.from_user.first_name}</a></b>, "
                                     f"для создания клана необходимо иметь Aniverse pass", reply_markup=create_back_button("clans"))

@clan.callback_query(F.data == "join_clan")
async def join_clan(call: CallbackQuery):
    user_id = call.from_user.id
    user_name = call.from_user.first_name

    text = (
        f"🏰 <b>{user_name}</b>, чтобы вступить в клан, для начала найди главу клана, который будет готов принять тебя\n\n"
        f"📝 Если глава клана готов принять тебя, пусть напишет команду:\n"
        f"<code>Пригласить {user_id}</code> или <code>Пригласить @{call.from_user.username or 'твой_username'}</code>\n\n"
        f"📩 В лс бота тебе придёт сообщение, где ты сможешь принять или отвергнуть предложение вступить в клан\n\n"
        f"🆔 Твой ID: <code>{user_id}</code>"
    )

    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=create_back_button("clans")
    )
    await call.answer()

@clan.message(F.text.startswith("Пригласить"))
async def invite_to_clan_handler(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("⚠️ Укажи ID или @username пользователя для приглашения.")
        return

    target = parts[1].strip()

    # Попробуем получить ID
    try:
        if target.startswith("@"):
            # Допиши свой метод поиска ID по username
            # Пример: user_id = get_user_id_by_username(target[1:])
            await message.reply("🔍 Поиск по @username пока не реализован.")
            return
        else:
            user_id = int(target)
    except ValueError:
        await message.reply("⚠️ Неверный формат ID или username.")
        return

    # Отправим приглашение в ЛС пользователя
    text = (
        f"🏰 Тебя пригласили вступить в клан!\n\n"
        f"👤 Глава клана: <b>{message.from_user.full_name}</b>\n\n"
        f"Хочешь принять приглашение?"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_invite:{message.from_user.id}"),
            InlineKeyboardButton(text="❌ Отказаться", callback_data="decline_invite")
        ]
    ])

    try:
        await message.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await message.reply("📩 Приглашение отправлено!")
    except Exception as e:
        await message.reply(f"❌ Не удалось отправить приглашение: {e}")

@clan.callback_query(F.data.startswith("accept_invite:"))
async def accept_invite(call: CallbackQuery):
    leader_id = int(call.data.split(":")[1])
    # Тут логика добавления в клан
    await call.message.edit_text("🎉 Ты принял приглашение и вступил в клан!")
    await call.answer()

@clan.callback_query(F.data == "decline_invite")
async def decline_invite(call: CallbackQuery):
    await call.message.edit_text("❌ Ты отклонил приглашение.")
    await call.answer()
