import os
import math
import sqlite3
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, MenuButtonWebApp
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "2505")
PORT = int(os.getenv("PORT", 8080))
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://ВАШ_ЛОГИН.github.io/ВАШ_РЕПОЗИТОРИЙ/")

BOOKS_PER_PAGE = 3

def init_db():
    conn = sqlite3.connect("simple_gdz.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            subject TEXT,
            grade TEXT,
            year TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER,
            topic TEXT,
            task_type TEXT DEFAULT 'Задания',
            task_number TEXT,
            image_id TEXT,
            answer_text TEXT,
            FOREIGN KEY (book_id) REFERENCES books (id) ON DELETE CASCADE
        )
    """)
    
    # Авто-миграция: добавляем поле task_type, если его еще нет
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [column[1] for column in cursor.fetchall()]
    if "task_type" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN task_type TEXT DEFAULT 'Задания'")

    conn.commit()
    conn.close()

init_db()

class AdminStates(StatesGroup):
    auth = State()
    book_title = State()
    book_subject = State()
    book_grade = State()
    book_year = State()

    task_book_id = State()
    task_topic = State()
    task_type = State()
    task_number = State()
    task_photo = State()

    edit_task_id = State()
    edit_task_photo = State()

    delete_book_confirm = State()
    delete_task_confirm = State()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
authed_admins = set()

def get_main_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚡️ Открыть Simple. ГДЗ", web_app=WebAppInfo(url=MINI_APP_URL))],
            [KeyboardButton(text="📚 Каталог в чате"), KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )

def build_catalog_keyboard(page: int = 1):
    conn = sqlite3.connect("simple_gdz.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, grade FROM books ORDER BY id DESC")
    books = cursor.fetchall()
    conn.close()

    if not books:
        return None, 0

    total_books = len(books)
    total_pages = math.ceil(total_books / BOOKS_PER_PAGE)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * BOOKS_PER_PAGE
    end_idx = start_idx + BOOKS_PER_PAGE
    current_books = books[start_idx:end_idx]

    inline_buttons = []
    for b in current_books:
        inline_buttons.append([InlineKeyboardButton(text=f"📘 {b[1]} ({b[2]})", callback_data=f"open_book_{b[0]}={page}")])

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="«", callback_data=f"catalog_page_{page - 1}"))
    
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="ignore_page"))

    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="»", callback_data=f"catalog_page_{page + 1}"))

    if len(nav_buttons) > 1:
        inline_buttons.append(nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=inline_buttons), total_pages

# --- ПОЛЬЗОВАТЕЛЬСКИЕ ХЭНДЛЕРЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await bot.set_chat_menu_button(
        chat_id=message.chat.id,
        menu_button=MenuButtonWebApp(text="Simple. ГДЗ", web_app=WebAppInfo(url=MINI_APP_URL))
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚡️ Открыть Simple. ГДЗ", web_app=WebAppInfo(url=MINI_APP_URL))
    ]])
    await message.answer(
        "👋 Привет! Нажми на кнопку ниже, чтобы открыть решебник, или используй меню бота:",
        reply_markup=get_main_reply_keyboard()
    )
    await message.answer("Или открой WebApp прямо тут:", reply_markup=kb)

@dp.message(F.text == "📚 Каталог в чате")
async def btn_catalog_handler(message: types.Message):
    kb, total = build_catalog_keyboard(page=1)
    if not kb:
        await message.answer("📭 База решебников пока пуста.", reply_markup=get_main_reply_keyboard())
        return

    await message.answer("👋 **Выбери учебник из списка:**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("catalog_page_"))
async def process_catalog_page(call: types.CallbackQuery):
    page = int(call.data.split("_")[2])
    kb, _ = build_catalog_keyboard(page=page)
    if kb:
        await call.message.edit_text("👋 **Выбери учебник из списка:**", reply_markup=kb, parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "ignore_page")
async def ignore_page_click(call: types.CallbackQuery):
    await call.answer()

@dp.callback_query(F.data.startswith("open_book_"))
async def open_book(call: types.CallbackQuery):
    raw_data = call.data.split("_")[2]
    if "=" in raw_data:
        book_id, from_page = map(int, raw_data.split("="))
    else:
        book_id, from_page = int(raw_data), 1

    conn = sqlite3.connect("simple_gdz.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, topic, task_type, task_number FROM tasks WHERE book_id = ?", (book_id,))
    tasks = cursor.fetchall()
    conn.close()

    if not tasks:
        await call.answer("📭 В этом учебнике нет решений.", show_alert=True)
        return

    inline_buttons = []
    for t in tasks:
        t_type = t[2] or "Задания"
        inline_buttons.append([InlineKeyboardButton(text=f"📝 [{t_type}] {t[1]} — {t[3]}", callback_data=f"get_task_{t[0]}")])
        
    inline_buttons.append([InlineKeyboardButton(text="🔙 К учебникам", callback_data=f"back_to_books_{from_page}")])
    kb = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    await call.message.edit_text("🔢 **Выбери номер задания:**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("back_to_books_"))
async def back_to_books(call: types.CallbackQuery):
    page = int(call.data.split("_")[3])
    kb, _ = build_catalog_keyboard(page=page)
    await call.message.edit_text("👋 **Выбери учебник из списка:**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("get_task_"))
async def send_task_solution(call: types.CallbackQuery):
    task_id = int(call.data.split("_")[2])
    conn = sqlite3.connect("simple_gdz.db")
    cursor = conn.cursor()
    cursor.execute("SELECT image_id, answer_text, topic, task_type, task_number FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    conn.close()

    if task:
        t_type = task[3] or "Задания"
        caption = f"✅ **{task[2]}** ({t_type})\n📌 **Номер:** {task[4]}\n\n{task[1]}"
        await call.message.answer_photo(photo=task[0], caption=caption, parse_mode="Markdown")
        await call.answer()

# --- АДМИНКА ---
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if message.from_user.id in authed_admins:
        await send_admin_panel(message)
    else:
        await state.set_state(AdminStates.auth)
        await message.answer("🔒 Введи пароль админа:")

@dp.message(AdminStates.auth)
async def process_password(message: types.Message, state: FSMContext):
    if message.text.strip() == ADMIN_PASSWORD:
        authed_admins.add(message.from_user.id)
        await state.clear()
        await message.answer("✅ Вход выполнен!")
        await send_admin_panel(message)
    else:
        await message.answer("❌ Неверный пароль.")
        await state.clear()

async def send_admin_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Добавить учебник", callback_data="btn_add_book")],
        [InlineKeyboardButton(text="🖼 Добавить решение", callback_data="btn_add_task")],
        [InlineKeyboardButton(text="✏️ Заменить фото решения", callback_data="btn_edit_task")],
        [InlineKeyboardButton(text="🗑 Удалить решение", callback_data="btn_delete_task")],
        [InlineKeyboardButton(text="❌ Удалить учебник", callback_data="btn_delete_book")],
        [InlineKeyboardButton(text="📋 Все учебники и решения", callback_data="btn_list_all")]
    ])
    await message.answer("⚙️ **Панель управления Simple. ГДЗ**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "btn_admin_menu")
async def back_to_admin_menu(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await send_admin_panel(call.message)

@dp.callback_query(F.data == "btn_add_book")
async def start_add_book(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in authed_admins: return
    await state.set_state(AdminStates.book_title)
    await call.message.answer("📘 Название учебника (например: *Информатика*):", parse_mode="Markdown")

@dp.message(AdminStates.book_title)
async def process_book_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AdminStates.book_subject)
    await message.answer("📐 Предмет (например: *Информатика*):")

@dp.message(AdminStates.book_subject)
async def process_book_subject(message: types.Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await state.set_state(AdminStates.book_grade)
    await message.answer("🎓 Класс (например: *7 класс*):")

@dp.message(AdminStates.book_grade)
async def process_book_grade(message: types.Message, state: FSMContext):
    await state.update_data(grade=message.text.strip())
    await state.set_state(AdminStates.book_year)
    await message.answer("📅 Год издания (например: *2023*):")

@dp.message(AdminStates.book_year)
async def process_book_year(message: types.Message, state: FSMContext):
    data = await state.get_data()
    conn = sqlite3.connect("simple_gdz.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO books (title, subject, grade, year) VALUES (?, ?, ?, ?)",
        (data["title"], data["subject"], data["grade"], message.text.strip())
    )
    book_id = cursor.lastrowid
    conn.commit()
    conn.close()
    await message.answer(f"✅ Учебник добавлен! ID: `{book_id}`", parse_mode="Markdown")
    await state.clear()
    await send_admin_panel(message)

# --- ДОБАВЛЕНИЕ ЗАДАНИЯ С РУЧНЫМ ВВОДОМ ТИПА ---
@dp.callback_query(F.data == "btn_add_task")
async def start_add_task(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in authed_admins: return
    await state.set_state(AdminStates.task_book_id)
    await call.message.answer("🆔 Введи **book_id** учебника:")

@dp.message(AdminStates.task_book_id)
async def process_task_book_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(book_id=int(message.text))
    await state.set_state(AdminStates.task_topic)
    await message.answer("📖 Раздел/Параграф (например: *Параграф 5*):")

@dp.message(AdminStates.task_topic)
async def process_task_topic(message: types.Message, state: FSMContext):
    await state.update_data(topic=message.text.strip())
    await state.set_state(AdminStates.task_type)
    await message.answer(
        "✍️ **Введи тип/категорию задания вручную текстом**\n\n"
        "Например: `Контрольные вопросы`, `Упражнения`, `Домашнее задание`, `Практическая работа` и т.д.:",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.task_type)
async def process_task_type(message: types.Message, state: FSMContext):
    user_type = message.text.strip()
    await state.update_data(task_type=user_type)
    await state.set_state(AdminStates.task_number)
    await message.answer(
        f"Тип сохранён: *{user_type}*\n\n🔢 Введи номер или название задания (например: *№ 3* или *Вопрос 1*):",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.task_number)
async def process_task_number(message: types.Message, state: FSMContext):
    await state.update_data(task_number=message.text.strip())
    await state.set_state(AdminStates.task_photo)
    await message.answer("📸 Отправь **фотографию** решения:")

@dp.message(AdminStates.task_photo, F.photo)
async def process_task_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id
    caption = message.caption or ""

    conn = sqlite3.connect("simple_gdz.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (book_id, topic, task_type, task_number, image_id, answer_text) VALUES (?, ?, ?, ?, ?, ?)",
        (data["book_id"], data["topic"], data.get("task_type", "Задания"), data["task_number"], photo_id, caption)
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    await message.answer(f"✅ Решение сохранено! task_id: `{task_id}`", parse_mode="Markdown")
    await state.clear()
    await send_admin_panel(message)

# --- РЕДАКТИРОВАНИЕ И УДАЛЕНИЕ ---
@dp.callback_query(F.data == "btn_edit_task")
async def start_edit_task(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in authed_admins: return
    await state.set_state(AdminStates.edit_task_id)
    await call.message.answer("✏️ Введи **task_id** решения, которое хочешь обновить:")

@dp.message(AdminStates.edit_task_id)
async def process_edit_task_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await state.update_data(edit_task_id=int(message.text))
    await state.set_state(AdminStates.edit_task_photo)
    await message.answer("📸 Отправь новое фото задания:")

@dp.message(AdminStates.edit_task_photo, F.photo)
async def process_edit_task_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = message.photo[-1].file_id
    caption = message.caption or ""

    conn = sqlite3.connect("simple_gdz.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET image_id = ?, answer_text = ? WHERE id = ?", (photo_id, caption, data["edit_task_id"]))
    conn.commit()
    conn.close()

    await message.answer("✅ Решение успешно обновлено!")
    await state.clear()
    await send_admin_panel(message)

@dp.callback_query(F.data == "btn_delete_task")
async def start_delete_task(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in authed_admins: return
    await state.set_state(AdminStates.delete_task_confirm)
    await call.message.answer("🗑 Введи **task_id** решения для удаления:")

@dp.message(AdminStates.delete_task_confirm)
async def process_delete_task(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    conn = sqlite3.connect("simple_gdz.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (int(message.text),))
    conn.commit()
    conn.close()
    await message.answer("🗑 Решение удалено!")
    await state.clear()
    await send_admin_panel(message)

@dp.callback_query(F.data == "btn_delete_book")
async def start_delete_book(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in authed_admins: return
    await state.set_state(AdminStates.delete_book_confirm)
    await call.message.answer("❌ Введи **book_id** учебника для удаления:")

@dp.message(AdminStates.delete_book_confirm)
async def process_delete_book(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    book_id = int(message.text)
    conn = sqlite3.connect("simple_gdz.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE book_id = ?", (book_id,))
    cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()
    conn.close()
    await message.answer("❌ Учебник и его решения удалены!")
    await state.clear()
    await send_admin_panel(message)

@dp.callback_query(F.data == "btn_list_all")
async def list_all_content(call: types.CallbackQuery):
    if call.from_user.id not in authed_admins: return
    conn = sqlite3.connect("simple_gdz.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM books ORDER BY id DESC")
    books = [dict(b) for b in cursor.fetchall()]

    if not books:
        await call.message.answer("📭 База данных пуста.")
        return

    text = "📚 **Список учебников и решений:**\n\n"
    for b in books:
        text += f"📖 **[{b['id']}] {b['title']}** ({b['grade']})\n"
        cursor.execute("SELECT id, topic, task_type, task_number FROM tasks WHERE book_id = ?", (b["id"],))
        tasks = cursor.fetchall()
        for t in tasks:
            text += f"   └── 🖼 `task_id: {t['id']}` — {t['topic']} [{t['task_type']}] ({t['task_number']})\n"
        text += "\n"

    conn.close()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="btn_admin_menu")]])
    await call.message.answer(text, reply_markup=kb, parse_mode="Markdown")

# --- ВЕБ-СЕРВЕР ---
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "*"
}

async def handle_options(request):
    return web.Response(headers=CORS_HEADERS)

async def handle_get_data(request):
    conn = sqlite3.connect("simple_gdz.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM books ORDER BY id DESC")
    books = [dict(b) for b in cursor.fetchall()]

    for book in books:
        cursor.execute("SELECT * FROM tasks WHERE book_id = ? ORDER BY id ASC", (book["id"],))
        tasks = [dict(t) for t in cursor.fetchall()]
        for t in tasks:
            t["photo_url"] = f"/api/photo/{t['image_id']}" if t["image_id"] else None
        book["tasks"] = tasks

    conn.close()
    return web.json_response(books, headers=CORS_HEADERS)

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
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"🚀 Сервер запущен на порту {PORT}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
