from aiogram.client.default import DefaultBotProperties
from aiogram import Bot
import os, json

# Загрузка конфигурации
file_path = os.getenv('python_conf')
with open(file_path, 'r') as file:
    config = json.load(file)
TOKEN = config.get("bot_revcard")


bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode='HTML'))