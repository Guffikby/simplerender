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
    task_chapter_custom = State()
    task_paragraph = State()
    task_paragraph_custom = State()
    task_category = State()
    task_category_custom = State()
    task_number = State()
    task_photo = State()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
authed_admins = set()

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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    try:
        await bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonWebApp(text="Simple. ГДЗ", web_app=WebAppInfo(url=MINI_APP_URL))
        )
    except Exception as e:
        logging.warning(f"Ошибка кнопки меню: {e}")

    await message.answer(
        "👋 **Привет! Добро пожаловать в Simple. ГДЗ!**\n\n"
        "Нажми кнопку ниже, чтобы открыть приложение или просмотреть каталог в чате.",
        reply_markup=get_main_reply_keyboard(),
        parse_mode="Markdown"
    )

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

# --- ДОБАВЛЕНИЕ ПРЕДМЕТА И УЧЕБНИКА ---
@dp.callback_query(F.data == "add_subj")
async def start_add_subj(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.subject_title)
    await call.message.answer("📐 Введи название предмета:")
    await call.answer()

@dp.message(AdminStates.subject_title)
async def process_subj_title(message: types.Message, state: FSMContext):
    await db.add_subject(message.text.strip())
    await message.answer("✅ Предмет сохранен!", reply_markup=get_admin_menu())
    await state.clear()

@dp.callback_query(F.data == "add_book")
async def start_add_book(call: types.CallbackQuery, state: FSMContext):
    subjs = await db.get_all_subjects()
    if not subjs:
        await call.message.answer("⚠️ Сначала создай предмет!")
        await call.answer()
        return
    kb = [[InlineKeyboardButton(text=s["title"], callback_data=f"sel_subj_{s['_id']}")] for s in subjs]
    await state.set_state(AdminStates.book_subject_id)
    await call.message.answer("Выбери предмет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(AdminStates.book_subject_id, F.data.startswith("sel_subj_"))
async def process_book_subj(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(subject_id=call.data.replace("sel_subj_", ""))
    await state.set_state(AdminStates.book_title)
    await call.message.answer("📘 Название/Автор учебника:")
    await call.answer()

@dp.message(AdminStates.book_title)
async def process_book_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AdminStates.book_grade)
    await message.answer("🎓 Класс:")

@dp.message(AdminStates.book_grade)
async def process_book_grade(message: types.Message, state: FSMContext):
    await state.update_data(grade=message.text.strip())
    await state.set_state(AdminStates.book_year)
    await message.answer("📅 Год издания:")

@dp.message(AdminStates.book_year)
async def process_book_year(message: types.Message, state: FSMContext):
    await state.update_data(year=message.text.strip())
    await state.set_state(AdminStates.book_cover)
    await message.answer("📸 Отправь фото обложки (или `-` для пропуска):")

@dp.message(AdminStates.book_cover)
async def process_book_cover(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cover_id = message.photo[-1].file_id if message.photo else None
    await db.add_book(data["subject_id"], data["title"], data["grade"], data["year"], cover_id)
    await message.answer("✅ Учебник сохранен!", reply_markup=get_admin_menu())
    await state.clear()


# --- ДОБАВЛЕНИЕ РЕШЕНИЯ (С ВЫБОРОМ ИЛИ СОЗДАНИЕМ ГЛАВ/ПАРАГРАФОВ) ---

@dp.callback_query(F.data == "add_task")
async def start_add_task(call: types.CallbackQuery, state: FSMContext):
    books = await db.get_all_books()
    if not books:
        await call.message.answer("⚠️ Создай сначала учебник!")
        await call.answer()
        return
    kb = [[InlineKeyboardButton(text=f"{b['title']} ({b['grade']})", callback_data=f"task_book_{b['_id']}")] for b in books]
    await state.set_state(AdminStates.task_book_id)
    await call.message.answer("Выбери учебник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

# 1. Выбор или создание ГЛАВЫ
@dp.callback_query(AdminStates.task_book_id, F.data.startswith("task_book_"))
async def process_task_book(call: types.CallbackQuery, state: FSMContext):
    book_id = call.data.replace("task_book_", "")
    await state.update_data(book_id=book_id)
    
    # Ищем существующие главы
    tasks = await db.get_all_tasks()
    chapters = sorted(list(set([t["chapter"] for t in tasks if t.get("book_id") == book_id and t.get("chapter")])))

    kb = [[InlineKeyboardButton(text=f"📖 {ch}", callback_data=f"sel_ch_{ch}")] for ch in chapters]
    kb.append([InlineKeyboardButton(text="➕ Создать новую главу", callback_data="new_chapter")])

    await state.set_state(AdminStates.task_chapter)
    await call.message.answer("📖 Выбери существующую **Главу** или создай новую:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(AdminStates.task_chapter, F.data == "new_chapter")
async def ask_new_chapter(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.task_chapter_custom)
    await call.message.answer("Введи название новой главы (например: *Глава 1. Информация*):")
    await call.answer()

@dp.message(AdminStates.task_chapter_custom)
async def process_custom_chapter(message: types.Message, state: FSMContext):
    await state.update_data(chapter=message.text.strip())
    await ask_paragraph_step(message, state)

@dp.callback_query(AdminStates.task_chapter, F.data.startswith("sel_ch_"))
async def process_select_chapter(call: types.CallbackQuery, state: FSMContext):
    ch = call.data.replace("sel_ch_", "")
    await state.update_data(chapter=ch)
    await ask_paragraph_step(call.message, state)
    await call.answer()

# 2. Выбор или создание ПАРАГРАФА
async def ask_paragraph_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    book_id = data["book_id"]
    chapter = data["chapter"]

    tasks = await db.get_all_tasks()
    paragraphs = sorted(list(set([t["paragraph"] for t in tasks if t.get("book_id") == book_id and t.get("chapter") == chapter and t.get("paragraph")])))

    kb = [[InlineKeyboardButton(text=f"📑 {p}", callback_data=f"sel_p_{p}")] for p in paragraphs]
    kb.append([InlineKeyboardButton(text="➕ Создать новый параграф", callback_data="new_paragraph")])

    await state.set_state(AdminStates.task_paragraph)
    await message.answer(f"Глава: *{chapter}*\n\n📑 Выбери **Параграф** или создай новый:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@dp.callback_query(AdminStates.task_paragraph, F.data == "new_paragraph")
async def ask_new_paragraph(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.task_paragraph_custom)
    await call.message.answer("Введи название нового параграфа (например: *§ 1.2 Носители информации*):")
    await call.answer()

@dp.message(AdminStates.task_paragraph_custom)
async def process_custom_paragraph(message: types.Message, state: FSMContext):
    await state.update_data(paragraph=message.text.strip())
    await ask_category_step(message, state)

@dp.callback_query(AdminStates.task_paragraph, F.data.startswith("sel_p_"))
async def process_select_paragraph(call: types.CallbackQuery, state: FSMContext):
    p = call.data.replace("sel_p_", "")
    await state.update_data(paragraph=p)
    await ask_category_step(call.message, state)
    await call.answer()

# 3. Выбор или создание КАТЕГОРИИ
async def ask_category_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    book_id = data["book_id"]
    chapter = data["chapter"]
    paragraph = data["paragraph"]

    tasks = await db.get_all_tasks()
    categories = sorted(list(set([t["category"] for t in tasks if t.get("book_id") == book_id and t.get("chapter") == chapter and t.get("paragraph") == paragraph and t.get("category")])))

    kb = [[InlineKeyboardButton(text=f"📌 {cat}", callback_data=f"sel_cat_{cat}")] for cat in categories]
    kb.append([InlineKeyboardButton(text="➕ Создать новую категорию", callback_data="new_category")])

    await state.set_state(AdminStates.task_category)
    await message.answer(f"Параграф: *{paragraph}*\n\n📌 Выбери **Категорию** или создай новую:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@dp.callback_query(AdminStates.task_category, F.data == "new_category")
async def ask_new_category(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.task_category_custom)
    await call.message.answer("Введи название новой категории (например: *Задания*, *Вопросы*, *Практикум*):")
    await call.answer()

@dp.message(AdminStates.task_category_custom)
async def process_custom_category(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    await ask_task_number_step(message, state)

@dp.callback_query(AdminStates.task_category, F.data.startswith("sel_cat_"))
async def process_select_category(call: types.CallbackQuery, state: FSMContext):
    cat = call.data.replace("sel_cat_", "")
    await state.update_data(category=cat)
    await ask_task_number_step(call.message, state)
    await call.answer()

# 4. Номер упражнения и Фото
async def ask_task_number_step(message: types.Message, state: FSMContext):
    await state.set_state(AdminStates.task_number)
    await message.answer("🔢 Введи **номер упражнения / вопроса** (например: *№1 с. 14* или *Вопрос 3*):")

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
    await message.answer("✅ Решение успешно добавлено!", reply_markup=get_admin_menu())
    await state.clear()


# --- СПИСОК ВСЕГО И УДАЛЕНИЕ ---
@dp.callback_query(F.data == "list_all")
async def list_all_content(call: types.CallbackQuery):
    catalog = await db.get_full_catalog()
    if not catalog:
        await call.message.answer("📭 База пуста.")
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
    await db.delete_subject(call.data.replace("confirm_del_subj_", ""))
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
    await db.delete_book(call.data.replace("confirm_del_book_", ""))
    await call.message.answer("✅ Учебник удален!")
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
    await db.delete_task(call.data.replace("confirm_del_task_", ""))
    await call.message.answer("✅ Решение удалено!")
    await back_to_menu(call, None)


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
