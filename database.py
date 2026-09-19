import os
from motor.motor_asyncio import AsyncIOMotorClient

# Читаем ссылку подключения из переменных окружения Render
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise ValueError("Переменная окружения MONGO_URI не установлена!")

# Инициализируем клиент MongoDB
cluster = AsyncIOMotorClient(MONGO_URI)

# Выбираем базу данных и коллекции (таблицы)
db = cluster["bot_database"]
users_collection = db["users"]


# Пример асинхронных функций для работы с базой

async def save_user(user_id: int, username: str, full_name: str):
    """Сохранить или обновить данные пользователя"""
    await users_collection.update_one(
        {"_id": user_id},
        {"$set": {
            "username": username,
            "full_name": full_name
        }},
        upsert=True  # Создаст запись, если пользователя еще нет
    )


async def get_user(user_id: int):
    """Получить данные пользователя по его ID"""
    return await users_collection.find_one({"_id": user_id})


async def delete_user(user_id: int):
    """Удалить пользователя"""
    await users_collection.delete_one({"_id": user_id})
