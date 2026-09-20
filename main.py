import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from dotenv import load_dotenv

import database as db

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "2505")
PORT = int(os.getenv("PORT", 8080))
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://ваш_логин.github.io/simple/")

class AdminStates(StatesGroup):
    auth = State()
    
    # Предмет
    subject_title = State()

    # Учебник
    book_subject_id = State()
    book_title = State()
    book_grade = State()
    book_year = State()
    book_cover = State()

    # Задание
    task_book_id = State()
    task_chapter = State()
    task_type = State()
    task_number = State()
    task_photo = State()

    # Удаление
    delete_id = State()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
authed_admins = set()

# --- КЛАВИАТУРЫ ---
def get_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📐 Добавить предмет", callback_data="add_subj")],
        [InlineKeyboardButton(text="📚 Добавить учебник (+Обложка)", callback_data="add_book")],
        [InlineKeyboardButton(text="🖼 Добавить решение (+Глава)", callback_data="add_task")],
        [InlineKeyboardButton(text="📋 Список всего", callback_data="list_all")],
        [InlineKeyboardButton(text="🗑 Удалить предмет/учебник/задание", callback_data="del_item")]
    ])

# --- ОБРАБОТКА АДМИНКИ ---
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if message.from_user.id in authed_admins:
        await message.answer("⚙️ Панель управления Simple. ГДЗ:", reply_markup=get_admin_menu())
    else:
        await state.set_state(AdminStates.auth)
        await message.answer("🔒 Введи пароль админа:")

@dp.message(AdminStates.auth)
async def process_auth(message: types.Message, state: FSMContext):
    if message.text.strip() == ADMIN_PASSWORD:
        authed_admins.add(message.from_user.id)
        await state.clear()
        await message.answer("✅ Авторизация успешна!", reply_markup=get_admin_menu())
    else:
        await message.answer("❌ Неверный пароль.")
        await state.clear()

# 1. Добавление предмета
@dp.callback_query(F.data == "add_subj")
async def start_add_subj(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.subject_title)
    await call.message.answer("📐 Введи название предмета (например: *Информатика*):", parse_mode="Markdown")
    await call.answer()

@dp.message(AdminStates.subject_title)
async def process_subj_title(message: types.Message, state: FSMContext):
    await db.add_subject(message.text.strip())
    await message.answer("✅ Предмет сохранен!", reply_markup=get_admin_menu())
    await state.clear()

# 2. Добавление учебника
@dp.callback_query(F.data == "add_book")
async def start_add_book(call: types.CallbackQuery, state: FSMContext):
    subjs = await db.get_all_subjects()
    if not subjs:
        await call.message.answer("⚠️ Сначала создай хотя бы один предмет!")
        await call.answer()
        return
    
    kb = []
    for s in subjs:
        kb.append([InlineKeyboardButton(text=s["title"], callback_data=f"sel_subj_{s['_id']}")])
    
    await state.set_state(AdminStates.book_subject_id)
    await call.message.answer("Выбери предмет для учебника:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(AdminStates.book_subject_id, F.data.startswith("sel_subj_"))
async def process_book_subj(call: types.CallbackQuery, state: FSMContext):
    subj_id = call.data.replace("sel_subj_", "")
    await state.update_data(subject_id=subj_id)
    await state.set_state(AdminStates.book_title)
    await call.message.answer("📘 Название учебника (например: *Босова Л.Л.*):")
    await call.answer()

@dp.message(AdminStates.book_title)
async def process_book_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AdminStates.book_grade)
    await message.answer("🎓 Класс (например: *7 класс*):")

@dp.message(AdminStates.book_grade)
async def process_book_grade(message: types.Message, state: FSMContext):
    await state.update_data(grade=message.text.strip())
    await state.set_state(AdminStates.book_year)
    await message.answer("📅 Год издания (например: *2023*):")

@dp.message(AdminStates.book_year)
async def process_book_year(message: types.Message, state: FSMContext):
    await state.update_data(year=message.text.strip())
    await state.set_state(AdminStates.book_cover)
    await message.answer("📸 Отправь фото обложки учебника (или отправь `-` чтобы пропустить):")

@dp.message(AdminStates.book_cover)
async def process_book_cover(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cover_id = None
    if message.photo:
        cover_id = message.photo[-1].file_id

    await db.add_book(
        subject_id=data["subject_id"],
        title=data["title"],
        grade=data["grade"],
        year=data["year"],
        cover_file_id=cover_id
    )
    await message.answer("✅ Учебник сохранен!", reply_markup=get_admin_menu())
    await state.clear()

# 3. Добавление задания с ГЛАВОЙ
@dp.callback_query(F.data == "add_task")
async def start_add_task(call: types.CallbackQuery, state: FSMContext):
    books = await db.get_all_books()
    if not books:
        await call.message.answer("⚠️ Сначала создай хотя бы один учебник!")
        await call.answer()
        return
    
    kb = []
    for b in books:
        kb.append([InlineKeyboardButton(text=f"{b['title']} ({b['grade']})", callback_data=f"sel_book_{b['_id']}")])

    await state.set_state(AdminStates.task_book_id)
    await call.message.answer("Выбери учебник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(AdminStates.task_book_id, F.data.startswith("sel_book_"))
async def process_task_book(call: types.CallbackQuery, state: FSMContext):
    book_id = call.data.replace("sel_book_", "")
    await state.update_data(book_id=book_id)
    await state.set_state(AdminStates.task_chapter)
    await call.message.answer("📖 Введи **Главу / Раздел** (например: *Глава 1. Информация и информационные процессы* или *Раздел 3*):", parse_mode="Markdown")
    await call.answer()

@dp.message(AdminStates.task_chapter)
async def process_task_chapter(message: types.Message, state: FSMContext):
    await state.update_data(chapter=message.text.strip())
    await state.set_state(AdminStates.task_type)
    await message.answer("✍️ Введи **тип подраздела** (например: *Параграф 5*, *Контрольные вопросы*, *Домашняя работа*):")

@dp.message(AdminStates.task_type)
async def process_task_type(message: types.Message, state: FSMContext):
    await state.update_data(task_type=message.text.strip())
    await state.set_state(AdminStates.task_number)
    await message.answer("🔢 Введи **номер/название упражнения** (например: *№ 12*, *Вопрос 3*):")

@dp.message(AdminStates.task_number)
async def process_task_number(message: types.Message, state: FSMContext):
    await state.update_data(task_number=message.text.strip())
    await state.set_state(AdminStates.task_photo)
    await message.answer("📸 Отправь **фотографию** решения:")

@dp.message(AdminStates.task_photo, F.photo)
async def process_task_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id

    await db.add_task(
        book_id=data["book_id"],
        chapter=data["chapter"],
        task_type=data["task_type"],
        task_number=data["task_number"],
        image_id=photo_id,
        answer_text=message.caption or ""
    )
    await message.answer("✅ Решение успешно сохранено!", reply_markup=get_admin_menu())
    await state.clear()

# --- API ЭНДПОИНТЫ ---
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "*"
}

async def handle_options(request):
    return web.Response(headers=CORS_HEADERS)

async def handle_get_data(request):
    catalog = await db.get_full_catalog()
    return web.json_response(catalog, headers=CORS_HEADERS)

async def handle_get_photo(request):
    file_id = request.match_info.get('file_id')
    try:
        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        return web.Response(
            body=file_bytes.read(),
            content_type='image/jpeg',
            headers=CORS_HEADERS
        )
    except Exception:
        return web.Response(status=404, headers=CORS_HEADERS)

app = web.Application()
app.router.add_options('/{tail:.*}', handle_options)
app.router.add_get('/api/data', handle_get_data)
app.router.add_get('/api/photo/{file_id}', handle_get_photo)

async def main():
    logging.basicConfig(level=logging.INFO)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"🚀 API запущен на порту {PORT}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

