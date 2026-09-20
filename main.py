import os
import asyncio
import logging
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

import database as db

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "2505")
PORT = int(os.getenv("PORT", 8080))
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://ваш_логин.github.io/simple/")

class AdminStates(StatesGroup):
    auth = State()
    subject_title = State()

    book_subject_id = State()
    book_title = State()
    book_grade = State()
    book_year = State()
    book_cover = State()

    task_book_id = State()
    task_chapter = State()
    task_paragraph = State()
    task_category = State()
    task_number = State()
    task_photo = State()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
authed_admins = set()

# --- КЛАВИАТУРЫ ПОЛЬЗОВАТЕЛЯ ---
def get_main_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚡️ Открыть Simple. ГДЗ", web_app=WebAppInfo(url=MINI_APP_URL))],
            [KeyboardButton(text="📚 Каталог в чате")]
        ],
        resize_keyboard=True
    )

def get_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📐 Добавить предмет", callback_data="add_subj")],
        [InlineKeyboardButton(text="📚 Добавить учебник (+Обложка)", callback_data="add_book")],
        [InlineKeyboardButton(text="🖼 Добавить решение", callback_data="add_task")],
        [InlineKeyboardButton(text="📋 Список всего", callback_data="list_all")],
        [InlineKeyboardButton(text="🗑 Удаление элементов", callback_data="del_menu")]
    ])

# ==========================================
# 1. ПРИВЕТСТВИЕ И ПОЛЬЗОВАТЕЛЬСКАЯ ЧАСТЬ
# ==========================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Устанавливаем кнопку веб-аппа в меню чата (слева внизу)
    try:
        await bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonWebApp(text="Simple. ГДЗ", web_app=WebAppInfo(url=MINI_APP_URL))
        )
    except Exception as e:
        logging.warning(f"Не удалось установить кнопку меню: {e}")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚡️ Открыть Simple. ГДЗ", web_app=WebAppInfo(url=MINI_APP_URL))
    ]])

    await message.answer(
        "👋 **Привет! Добро пожаловать в Simple. ГДЗ!**\n\n"
        "Здесь ты можешь быстро найти решения к параграфам и упражнениям из своих учебников.\n\n"
        "📱 **Нажми на кнопку ниже**, чтобы открыть удобное приложение, или используй каталог прямо в чате!",
        reply_markup=get_main_reply_keyboard(),
        parse_mode="Markdown"
    )
    await message.answer("Открыть WebApp:", reply_markup=kb)


# --- ПРОСМОТР ГДЗ В ЧАТЕ ---

@dp.message(F.text == "📚 Каталог в чате")
async def show_chat_catalog(message: types.Message):
    subjs = await db.get_all_subjects()
    if not subjs:
        await message.answer("📭 База решебников пока пуста.")
        return

    kb = [[InlineKeyboardButton(text=f"📐 {s['title']}", callback_data=f"user_subj_{s['_id']}")] for s in subjs]
    await message.answer("📐 **Выбери предмет:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")


@dp.callback_query(F.data.startswith("user_subj_"))
async def user_open_subject(call: types.CallbackQuery):
    subj_id = call.data.replace("user_subj_", "")
    books = await db.get_all_books()
    user_books = [b for b in books if b.get("subject_id") == subj_id]

    if not user_books:
        await call.answer(" В этом предмете пока нет учебников.", show_alert=True)
        return

    kb = [[InlineKeyboardButton(text=f"📘 {b['title']} ({b['grade']})", callback_data=f"user_book_{b['_id']}")] for b in user_books]
    kb.append([InlineKeyboardButton(text="🔙 К предметам", callback_data="user_back_subjs")])
    
    await call.message.edit_text("📘 **Выбери учебник:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data == "user_back_subjs")
async def user_back_subjs(call: types.CallbackQuery):
    subjs = await db.get_all_subjects()
    kb = [[InlineKeyboardButton(text=f"📐 {s['title']}", callback_data=f"user_subj_{s['_id']}")] for s in subjs]
    await call.message.edit_text("📐 **Выбери предмет:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data.startswith("user_book_"))
async def user_open_book(call: types.CallbackQuery):
    book_id = call.data.replace("user_book_", "")
    tasks = await db.get_all_tasks()
    book_tasks = [t for t in tasks if t.get("book_id") == book_id]

    if not book_tasks:
        await call.answer(" В этом учебнике пока нет загруженных решений.", show_alert=True)
        return

    kb = []
    for t in book_tasks:
        btn_title = f"📝 {t.get('paragraph', '')} ➔ {t.get('category', '')} ➔ {t.get('task_number', '')}"
        kb.append([InlineKeyboardButton(text=btn_title, callback_data=f"user_task_{t['_id']}")])

    subj_id = book_tasks[0].get("subject_id", "")
    kb.append([InlineKeyboardButton(text="🔙 К учебникам", callback_data=f"user_subj_{subj_id}")])

    await call.message.edit_text("🔢 **Выбери нужный номер / задание:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()


@dp.callback_query(F.data.startswith("user_task_"))
async def user_send_solution(call: types.CallbackQuery):
    task_id = call.data.replace("user_task_", "")
    tasks = await db.get_all_tasks()
    task = next((t for t in tasks if str(t["_id"]) == task_id), None)

    if not task:
        await call.answer("Решение не найдено.", show_alert=True)
        return

    caption = (
        f"📖 **{task.get('chapter', '')}**\n"
        f"📑 **{task.get('paragraph', '')}**\n"
        f"📌 **{task.get('category', '')}** — `{task.get('task_number', '')}`\n\n"
        f"{task.get('answer_text', '')}"
    )

    if task.get("image_id"):
        await call.message.answer_photo(photo=task["image_id"], caption=caption, parse_mode="Markdown")
    else:
        await call.message.answer(caption, parse_mode="Markdown")
    
    await call.answer()


# ==========================================
# 2. АДМИН-ПАНЕЛЬ
# ==========================================

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if message.from_user.id in authed_admins:
        await message.answer("⚙️ **Панель управления Simple. ГДЗ:**", reply_markup=get_admin_menu(), parse_mode="Markdown")
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

@dp.callback_query(F.data == "admin_menu")
async def back_to_menu(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("⚙️ **Панель управления Simple. ГДЗ:**", reply_markup=get_admin_menu(), parse_mode="Markdown")
    await call.answer()

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
    
    kb = [[InlineKeyboardButton(text=s["title"], callback_data=f"sel_subj_{s['_id']}")] for s in subjs]
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])
    
    await state.set_state(AdminStates.book_subject_id)
    await call.message.answer("Выбери предмет для учебника:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(AdminStates.book_subject_id, F.data.startswith("sel_subj_"))
async def process_book_subj(call: types.CallbackQuery, state: FSMContext):
    subj_id = call.data.replace("sel_subj_", "")
    await state.update_data(subject_id=subj_id)
    await state.set_state(AdminStates.book_title)
    await call.message.answer("📘 Название/Автор учебника (например: *Босова Л.Л.*):")
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
    cover_id = message.photo[-1].file_id if message.photo else None

    await db.add_book(
        subject_id=data["subject_id"],
        title=data["title"],
        grade=data["grade"],
        year=data["year"],
        cover_file_id=cover_id
    )
    await message.answer("✅ Учебник сохранен!", reply_markup=get_admin_menu())
    await state.clear()

# 3. Добавление решения
@dp.callback_query(F.data == "add_task")
async def start_add_task(call: types.CallbackQuery, state: FSMContext):
    books = await db.get_all_books()
    if not books:
        await call.message.answer("⚠️ Сначала создай хотя бы один учебник!")
        await call.answer()
        return
    
    kb = [[InlineKeyboardButton(text=f"{b['title']} ({b['grade']})", callback_data=f"sel_book_{b['_id']}")] for b in books]
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu")])

    await state.set_state(AdminStates.task_book_id)
    await call.message.answer("Выбери учебник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(AdminStates.task_book_id, F.data.startswith("sel_book_"))
async def process_task_book(call: types.CallbackQuery, state: FSMContext):
    book_id = call.data.replace("sel_book_", "")
    await state.update_data(book_id=book_id)
    await state.set_state(AdminStates.task_chapter)
    await call.message.answer("1️⃣ Введи **Главу** (например: *Глава 1. Информация и процессы*):", parse_mode="Markdown")
    await call.answer()

@dp.message(AdminStates.task_chapter)
async def process_task_chapter(message: types.Message, state: FSMContext):
    await state.update_data(chapter=message.text.strip())
    await state.set_state(AdminStates.task_paragraph)
    await message.answer("2️⃣ Введи **Параграф** (например: *§ 1.2 Носители информации*):", parse_mode="Markdown")

@dp.message(AdminStates.task_paragraph)
async def process_task_paragraph(message: types.Message, state: FSMContext):
    await state.update_data(paragraph=message.text.strip())
    await state.set_state(AdminStates.task_category)
    await message.answer("3️⃣ Введи **Категорию после параграфа** (например: *Вопросы и задания*, *Практикум*):", parse_mode="Markdown")

@dp.message(AdminStates.task_category)
async def process_task_category(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    await state.set_state(AdminStates.task_number)
    await message.answer("4️⃣ Введи **Номер / Вопрос** (например: *№ 5* или *Вопрос 2*):", parse_mode="Markdown")

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
        paragraph=data["paragraph"],
        category=data["category"],
        task_number=data["task_number"],
        image_id=photo_id,
        answer_text=message.caption or ""
    )
    await message.answer("✅ Решение успешно сохранено!", reply_markup=get_admin_menu())
    await state.clear()

# 4. Список всего
@dp.callback_query(F.data == "list_all")
async def list_all_content(call: types.CallbackQuery):
    if call.from_user.id not in authed_admins: return
    
    catalog = await db.get_full_catalog()
    if not catalog:
        await call.message.answer("📭 База данных полностью пуста.")
        await call.answer()
        return

    text = "📋 **ВСЯ БАЗА ДАННЫХ:**\n\n"
    for s in catalog:
        text += f"📐 **Предмет:** {s['title']}\n"
        for b in s['books']:
            text += f"  └── 📘 **Учебник:** {b['title']} ({b['grade']})\n"
            for t in b['tasks']:
                text += f"       └── 📝 `{t['chapter']}` ➔ `{t['paragraph']}` ➔ `{t['category']}` ➔ **{t['task_number']}**\n"
        text += "\n"

    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await call.message.answer(text[x:x+4000], parse_mode="Markdown")
    else:
        await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# 5. Интерактивное удаление
@dp.callback_query(F.data == "del_menu")
async def delete_menu(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить Предмет", callback_data="del_type_subj")],
        [InlineKeyboardButton(text="🗑 Удалить Учебник", callback_data="del_type_book")],
        [InlineKeyboardButton(text="🗑 Удалить Решение", callback_data="del_type_task")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="admin_menu")]
    ])
    await call.message.edit_text("Выбери категорию для удаления:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "del_type_subj")
async def del_subj_list(call: types.CallbackQuery):
    subjs = await db.get_all_subjects()
    if not subjs:
        await call.message.answer("Предметов нет.")
        await call.answer()
        return
    kb = [[InlineKeyboardButton(text=f"❌ {s['title']}", callback_data=f"confirm_del_subj_{s['_id']}")] for s in subjs]
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="del_menu")])
    await call.message.edit_text("Выбери предмет для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_del_subj_"))
async def process_del_subj(call: types.CallbackQuery):
    s_id = call.data.replace("confirm_del_subj_", "")
    await db.delete_subject(s_id)
    await call.message.answer("✅ Предмет удален!")
    await back_to_menu(call, None)

@dp.callback_query(F.data == "del_type_book")
async def del_book_list(call: types.CallbackQuery):
    books = await db.get_all_books()
    if not books:
        await call.message.answer("Учебников нет.")
        await call.answer()
        return
    kb = [[InlineKeyboardButton(text=f"❌ {b['title']} ({b['grade']})", callback_data=f"confirm_del_book_{b['_id']}")] for b in books]
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="del_menu")])
    await call.message.edit_text("Выбери учебник для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_del_book_"))
async def process_del_book(call: types.CallbackQuery):
    b_id = call.data.replace("confirm_del_book_", "")
    await db.delete_book(b_id)
    await call.message.answer("✅ Учебник и его решения удалены!")
    await back_to_menu(call, None)

@dp.callback_query(F.data == "del_type_task")
async def del_task_list(call: types.CallbackQuery):
    tasks = await db.get_all_tasks()
    if not tasks:
        await call.message.answer("Заданий нет.")
        await call.answer()
        return
    kb = []
    for t in tasks[:30]:
        btn_text = f"❌ {t.get('paragraph', '')} -> {t.get('task_number', '')}"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"confirm_del_task_{t['_id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="del_menu")])
    await call.message.edit_text("Выбери решение для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(F.data.startswith("confirm_del_task_"))
async def process_del_task(call: types.CallbackQuery):
    t_id = call.data.replace("confirm_del_task_", "")
    await db.delete_task(t_id)
    await call.message.answer("✅ Решение удалено!")
    await back_to_menu(call, None)


# ==========================================
# 3. API ЭНДПОИНТЫ ДЛЯ MINIAPP
# ==========================================

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
