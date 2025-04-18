import asyncio
from flask import Flask, request, jsonify
from bot.main import bot, dp
from pydantic import BaseModel, ValidationError
import threading

app = Flask(__name__)

class User(BaseModel):
    id: int
    is_bot: bool
    first_name: str
    username: str

class Chat(BaseModel):
    id: int
    first_name: str
    type: str

class Message(BaseModel):
    message_id: int
    from_user: User
    chat: Chat
    date: int
    text: str

class Update(BaseModel):
    update_id: int
    message: Message

# Flask эндпоинт для получения обновлений
@app.route('/test-bot', methods=['POST'])
def test_bot():
    try:
        # Получаем данные из POST-запроса
        data = request.get_json()

        # Пытаемся преобразовать данные в объект Update
        update = Update(**data)

        # Обработка данных с помощью бота
        print(f"Received message: {update.message.text} from {update.message.from_user.username}")

        # Здесь можно добавить логику для взаимодействия с ботом, если необходимо.

        return jsonify({"status": "success", "message": "Data processed successfully"}), 200

    except ValidationError as e:
        # Обрабатываем ошибки валидации
        return jsonify({"status": "error", "message": "Invalid data", "details": e.errors()}), 400
    except Exception as e:
        # Общая ошибка
        return jsonify({"status": "error", "message": str(e)}), 500

# Функция для запуска Flask в отдельном потоке
def run_flask():
    app.run(debug=True, use_reloader=False)  # use_reloader=False для предотвращения второго запуска

# Функция для запуска бота
async def start_bot():
    await dp.start_polling(bot)

# Основная функция для запуска обоих процессов
def run():
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Запускаем Telegram-бота с использованием asyncio.run
    asyncio.run(start_bot())

if __name__ == '__main__':
    run()
