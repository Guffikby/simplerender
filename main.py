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
    task_chapter_select = State()
    task_chapter_custom = State()
    task_paragraph_select = State()
    task_paragraph_custom = State()
    task_category_select = State()
    task_category_custom = State()
    task_number = State()
    task_photo = State()

    # Пошаговое обновление решения: Класс -> Предмет -> Учебник -> Задание -> Фото
    edit_grade = State()
    edit_subj = State()
    edit_book = State()
    edit_task = State()
    edit_photo = State()

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
        [InlineKeyboardButton(text="✏️ Обновить фото решения", callback_data="edit_start")],
        [InlineKeyboardButton(text="📋 Список всего", callback_data="list_all")],
        [InlineKeyboardButton(text="🗑 Удаление элементов", callback_data="del_menu")]
    ])

# ==========================================
# 1. ПОЛЬЗОВАТЕЛЬСКАЯ ЧАСТЬ (Класс -> Предмет -> Учебник)
# ==========================================

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
        "Открывай приложение по кнопке ниже или ищи решения в чате.",
        reply_markup=get_main_reply_keyboard(),
        parse_mode="Markdown"
    )

# ШАГ 1: Выбор Класса
@dp.message(F.text == "📚 Каталог в чате")
async def show_chat_catalog(message: types.Message):
    grades = await db.get_all_grades()
    if not grades:
        await message.answer("📭 В базе пока нет материалов.")
        return

    kb = [[InlineKeyboardButton(text=f"🎓 {g}", callback_data=f"u_g_{i}")] for i, g in enumerate(grades)]
    await message.answer("🎓 **Выбери свой класс:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# ШАГ 2: Выбор Предмета в этом классе
@dp.callback_query(F.data.startswith("u_g_"))
async def user_select_grade(call: types.CallbackQuery):
    g_idx = int(call.data.replace("u_g_", ""))
    grades = await db.get_all_grades()
    selected_grade = grades[g_idx]

    books = await db.get_all_books()
    grade_books = [b for b in books if b.get("grade") == selected_grade]
    subj_ids = list(set([b.get("subject_id") for b in grade_books]))

    subjs = await db.get_all_subjects()
    grade_subjs = [s for s in subjs if str(s["_id"]) in subj_ids]

    if not grade_subjs:
        await call.answer("В этом классе нет предметов.", show_alert=True)
        return

    kb = [[InlineKeyboardButton(text=s["title"], callback_data=f"u_s_{g_idx}_{s['_id']}")] for s in grade_subjs]
    kb.append([InlineKeyboardButton(text="🔙 К классам", callback_data="u_back_grades")])

    await call.message.edit_text(f"Класс: *{selected_grade}*\n\n📐 **Выбери предмет:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(F.data == "u_back_grades")
async def user_back_grades(call: types.CallbackQuery):
    grades = await db.get_all_grades()
    kb = [[InlineKeyboardButton(text=f"🎓 {g}", callback_data=f"u_g_{i}")] for i, g in enumerate(grades)]
    await call.message.edit_text("🎓 **Выбери свой класс:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()

# ШАГ 3: Выбор Учебника
@dp.callback_query(F.data.startswith("u_s_"))
async def user_select_subj(call: types.CallbackQuery):
    _, _, g_idx, subj_id = call.data.split("_")
    g_idx = int(g_idx)
    grades = await db.get_all_grades()
    selected_grade = grades[g_idx]

    books = await db.get_all_books()
    target_books = [b for b in books if b.get("grade") == selected_grade and b.get("subject_id") == subj_id]

    kb = [[InlineKeyboardButton(text=f"📘 {b['title']}", callback_data=f"u_b_{b['_id']}")] for b in target_books]
    kb.append([InlineKeyboardButton(text="🔙 К предметам", callback_data=f"u_g_{g_idx}")])

    await call.message.edit_text("📘 **Выбери учебник:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()

# ШАГ 4: Выбор Параграфа
@dp.callback_query(F.data.startswith("u_b_"))
async def user_select_book(call: types.CallbackQuery):
    book_id = call.data.replace("u_b_", "")
    tasks = await db.get_all_tasks()
    book_tasks = [t for t in tasks if t.get("book_id") == book_id]

    if not book_tasks:
        await call.answer("В этом учебнике пока нет решений.", show_alert=True)
        return

    paragraphs = sorted(list(set([t.get("paragraph", "Параграф") for t in book_tasks])))
    kb = [[InlineKeyboardButton(text=f"📑 {p}", callback_data=f"u_p_{book_id}_{i}")] for i, p in enumerate(paragraphs)]

    await call.message.edit_text("📑 **Выбери параграф:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()

# ШАГ 5: Выбор Категории
@dp.callback_query(F.data.startswith("u_p_"))
async def user_select_paragraph(call: types.CallbackQuery):
    _, _, book_id, p_idx = call.data.split("_")
    p_idx = int(p_idx)

    tasks = await db.get_all_tasks()
    book_tasks = [t for t in tasks if t.get("book_id") == book_id]
    paragraphs = sorted(list(set([t.get("paragraph", "Параграф") for t in book_tasks])))
    selected_p = paragraphs[p_idx]

    p_tasks = [t for t in book_tasks if t.get("paragraph") == selected_p]
    categories = sorted(list(set([t.get("category", "Задания") for t in p_tasks])))

    kb = [[InlineKeyboardButton(text=f"📌 {cat}", callback_data=f"u_c_{book_id}_{p_idx}_{i}")] for i, cat in enumerate(categories)]
    kb.append([InlineKeyboardButton(text="🔙 К параграфам", callback_data=f"u_b_{book_id}")])

    await call.message.edit_text(f"Параграф: *{selected_p}*\n\n📌 **Выбери категорию:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()

# ШАГ 6: Выбор Номера задания
@dp.callback_query(F.data.startswith("u_c_"))
async def user_select_category(call: types.CallbackQuery):
    _, _, book_id, p_idx, cat_idx = call.data.split("_")
    p_idx, cat_idx = int(p_idx), int(cat_idx)

    tasks = await db.get_all_tasks()
    book_tasks = [t for t in tasks if t.get("book_id") == book_id]
    paragraphs = sorted(list(set([t.get("paragraph", "Параграф") for t in book_tasks])))
    selected_p = paragraphs[p_idx]

    p_tasks = [t for t in book_tasks if t.get("paragraph") == selected_p]
    categories = sorted(list(set([t.get("category", "Задания") for t in p_tasks])))
    selected_cat = categories[cat_idx]

    final_tasks = [t for t in p_tasks if t.get("category") == selected_cat]

    kb = []
    row = []
    for t in final_tasks:
        row.append(InlineKeyboardButton(text=t.get("task_number", "№"), callback_data=f"u_t_{t['_id']}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)

    kb.append([InlineKeyboardButton(text="🔙 К категориям", callback_data=f"u_p_{book_id}_{p_idx}")])

    await call.message.edit_text(
        f"📑 *{selected_p}* ➔ 📌 *{selected_cat}*\n\n🔢 **Выбери номер:**",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )
    await call.answer()

# Показ решения
@dp.callback_query(F.data.startswith("u_t_"))
async def user_send_task(call: types.CallbackQuery):
    task_id = call.data.replace("u_t_", "")
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
# 2. АДМИНКА И ПОШАГОВОЕ ОБНОВЛЕНИЕ
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

# ОБНОВЛЕНИЕ ПО СТРУКТУРЕ: Класс -> Предмет -> Учебник -> Задание
@dp.callback_query(F.data == "edit_start")
async def edit_step_1_grade(call: types.CallbackQuery, state: FSMContext):
    grades = await db.get_all_grades()
    if not grades:
        await call.message.answer("Учебники не найдены.")
        await call.answer()
        return

    kb = [[InlineKeyboardButton(text=f"🎓 {g}", callback_data=f"ed_g_{i}")] for i, g in enumerate(grades)]
    kb.append([InlineKeyboardButton(text="🔙 В меню", callback_data="admin_menu")])

    await state.update_data(edit_grades=grades)
    await state.set_state(AdminStates.edit_grade)
    await call.message.edit_text("🎓 **Выбери класс:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(AdminStates.edit_grade, F.data.startswith("ed_g_"))
async def edit_step_2_subj(call: types.CallbackQuery, state: FSMContext):
    g_idx = int(call.data.replace("ed_g_", ""))
    data = await state.get_data()
    selected_grade = data["edit_grades"][g_idx]
    await state.update_data(selected_grade=selected_grade)

    books = await db.get_all_books()
    grade_books = [b for b in books if b.get("grade") == selected_grade]
    subj_ids = list(set([b.get("subject_id") for b in grade_books]))

    subjs = await db.get_all_subjects()
    grade_subjs = [s for s in subjs if str(s["_id"]) in subj_ids]

    kb = [[InlineKeyboardButton(text=s["title"], callback_data=f"ed_s_{s['_id']}")] for s in grade_subjs]
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="edit_start")])

    await state.set_state(AdminStates.edit_subj)
    await call.message.edit_text(f"Класс: *{selected_grade}*\n\n📐 **Выбери предмет:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(AdminStates.edit_subj, F.data.startswith("ed_s_"))
async def edit_step_3_book(call: types.CallbackQuery, state: FSMContext):
    subj_id = call.data.replace("ed_s_", "")
    data = await state.get_data()
    selected_grade = data["selected_grade"]

    books = await db.get_all_books()
    target_books = [b for b in books if b.get("grade") == selected_grade and b.get("subject_id") == subj_id]

    kb = [[InlineKeyboardButton(text=f"📘 {b['title']}", callback_data=f"ed_b_{b['_id']}")] for b in target_books]

    await state.set_state(AdminStates.edit_book)
    await call.message.edit_text("📘 **Выбери учебник:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(AdminStates.edit_book, F.data.startswith("ed_b_"))
async def edit_step_4_task(call: types.CallbackQuery, state: FSMContext):
    book_id = call.data.replace("ed_b_", "")
    tasks = await db.get_all_tasks()
    book_tasks = [t for t in tasks if t.get("book_id") == book_id]

    if not book_tasks:
        await call.message.answer("В этом учебнике нет решений.")
        await call.answer()
        return

    kb = []
    for t in book_tasks[:30]:
        btn_text = f"✏️ {t.get('paragraph', '')} -> {t.get('task_number', '')}"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"ed_t_{t['_id']}")])

    await state.set_state(AdminStates.edit_task)
    await call.message.edit_text("Выбери решение для обновления фото:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(AdminStates.edit_task, F.data.startswith("ed_t_"))
async def edit_step_5_photo_prompt(call: types.CallbackQuery, state: FSMContext):
    task_id = call.data.replace("ed_t_", "")
    await state.update_data(edit_task_id=task_id)
    await state.set_state(AdminStates.edit_photo)
    await call.message.answer("📸 Отправь **НОВОЕ фото** решения:")
    await call.answer()

@dp.message(AdminStates.edit_photo, F.photo)
async def edit_step_6_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_id = data["edit_task_id"]
    new_photo_id = message.photo[-1].file_id

    await db.update_task_solution(task_id, new_photo_id, message.caption or "")
    await message.answer("✅ Фотография решения обновлена!", reply_markup=get_admin_menu())
    await state.clear()

# ДОБАВЛЕНИЕ ЭЛЕМЕНТОВ
@dp.callback_query(F.data == "add_subj")
async def start_add_subj(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.subject_title)
    await call.message.answer("📐 Введи название предмета:")
    await call.answer()

@dp.message(AdminStates.subject_title)
async def process_subj_title(message: types.Message, state: FSMContext):
    await db.add_subject(message.text)
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
    await state.update_data(title=message.text)
    await state.set_state(AdminStates.book_grade)
    await message.answer("🎓 Класс (например: *7 класс*):")

@dp.message(AdminStates.book_grade)
async def process_book_grade(message: types.Message, state: FSMContext):
    await state.update_data(grade=message.text)
    await state.set_state(AdminStates.book_year)
    await message.answer("📅 Год издания:")

@dp.message(AdminStates.book_year)
async def process_book_year(message: types.Message, state: FSMContext):
    await state.update_data(year=message.text)
    await state.set_state(AdminStates.book_cover)
    await message.answer("📸 Отправь фото обложки (или `-` для пропуска):")

@dp.message(AdminStates.book_cover)
async def process_book_cover(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cover_id = message.photo[-1].file_id if message.photo else None
    await db.add_book(data["subject_id"], data["title"], data["grade"], data["year"], cover_id)
    await message.answer("✅ Учебник сохранен!", reply_markup=get_admin_menu())
    await state.clear()

@dp.callback_query(F.data == "add_task")
async def start_add_task(call: types.CallbackQuery, state: FSMContext):
    books = await db.get_all_books()
    if not books:
        await call.message.answer("⚠️ Сначала создай учебник!")
        await call.answer()
        return
    kb = [[InlineKeyboardButton(text=f"[{b['grade']}] {b['title']}", callback_data=f"tb_{b['_id']}")] for b in books]
    await state.set_state(AdminStates.task_book_id)
    await call.message.answer("Выбери учебник:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await call.answer()

@dp.callback_query(AdminStates.task_book_id, F.data.startswith("tb_"))
async def process_task_book(call: types.CallbackQuery, state: FSMContext):
    book_id = call.data.replace("tb_", "")
    await state.update_data(book_id=book_id)
    
    tasks = await db.get_all_tasks()
    chapters = sorted(list(set([t["chapter"] for t in tasks if t.get("book_id") == book_id and t.get("chapter")])))

    kb = [[InlineKeyboardButton(text=f"📖 {ch}", callback_data=f"ch_{i}")] for i, ch in enumerate(chapters)]
    kb.append([InlineKeyboardButton(text="➕ Создать новую главу", callback_data="ch_new")])

    await state.update_data(chapters_list=chapters)
    await state.set_state(AdminStates.task_chapter_select)
    await call.message.answer("📖 Выбери **Главу** или создай новую:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await call.answer()

@dp.callback_query(AdminStates.task_chapter_select, F.data == "ch_new")
async def ask_new_chapter(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.task_chapter_custom)
    await call.message.answer("Введи название новой главы:")
    await call.answer()

@dp.message(AdminStates.task_chapter_custom)
async def process_custom_chapter(message: types.Message, state: FSMContext):
    await state.update_data(chapter=message.text)
    await ask_paragraph_step(message, state)

@dp.callback_query(AdminStates.task_chapter_select, F.data.startswith("ch_"))
async def process_select_chapter(call: types.CallbackQuery, state: FSMContext):
    idx = int(call.data.replace("ch_", ""))
    data = await state.get_data()
    ch = data["chapters_list"][idx]
    await state.update_data(chapter=ch)
    await ask_paragraph_step(call.message, state)
    await call.answer()

async def ask_paragraph_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    book_id = data["book_id"]
    chapter = data["chapter"]

    tasks = await db.get_all_tasks()
    paragraphs = sorted(list(set([t["paragraph"] for t in tasks if t.get("book_id") == book_id and t.get("chapter") == chapter and t.get("paragraph")])))

    kb = [[InlineKeyboardButton(text=f"📑 {p}", callback_data=f"p_{i}")] for i, p in enumerate(paragraphs)]
    kb.append([InlineKeyboardButton(text="➕ Создать новый параграф", callback_data="p_new")])

    await state.update_data(paragraphs_list=paragraphs)
    await state.set_state(AdminStates.task_paragraph_select)
    await message.answer(f"Глава: *{chapter}*\n\n📑 Выбери **Параграф** или создай новый:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@dp.callback_query(AdminStates.task_paragraph_select, F.data == "p_new")
async def ask_new_paragraph(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.task_paragraph_custom)
    await call.message.answer("Введи название нового параграфа:")
    await call.answer()

@dp.message(AdminStates.task_paragraph_custom)
async def process_custom_paragraph(message: types.Message, state: FSMContext):
    await state.update_data(paragraph=message.text)
    await ask_category_step(message, state)

@dp.callback_query(AdminStates.task_paragraph_select, F.data.startswith("p_"))
async def process_select_paragraph(call: types.CallbackQuery, state: FSMContext):
    idx = int(call.data.replace("p_", ""))
    data = await state.get_data()
    p = data["paragraphs_list"][idx]
    await state.update_data(paragraph=p)
    await ask_category_step(call.message, state)
    await call.answer()

async def ask_category_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    book_id = data["book_id"]
    chapter = data["chapter"]
    paragraph = data["paragraph"]

    tasks = await db.get_all_tasks()
    categories = sorted(list(set([t["category"] for t in tasks if t.get("book_id") == book_id and t.get("chapter") == chapter and t.get("paragraph") == paragraph and t.get("category")])))

    kb = [[InlineKeyboardButton(text=f"📌 {cat}", callback_data=f"cat_{i}")] for i, cat in enumerate(categories)]
    kb.append([InlineKeyboardButton(text="➕ Создать новую категорию", callback_data="cat_new")])

    await state.update_data(categories_list=categories)
    await state.set_state(AdminStates.task_category_select)
    await message.answer(f"Параграф: *{paragraph}*\n\n📌 Выбери **Категорию** или создай новую:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@dp.callback_query(AdminStates.task_category_select, F.data == "cat_new")
async def ask_new_category(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.task_category_custom)
    await call.message.answer("Введи название новой категории:")
    await call.answer()

@dp.message(AdminStates.task_category_custom)
async def process_custom_category(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text)
    await ask_task_number_step(message, state)

@dp.callback_query(AdminStates.task_category_select, F.data.startswith("cat_"))
async def process_select_category(call: types.CallbackQuery, state: FSMContext):
    idx = int(call.data.replace("cat_", ""))
    data = await state.get_data()
    cat = data["categories_list"][idx]
    await state.update_data(category=cat)
    await ask_task_number_step(call.message, state)
    await call.answer()

async def ask_task_number_step(message: types.Message, state: FSMContext):
    await state.set_state(AdminStates.task_number)
    await message.answer("🔢 Введи **номер упражнения / вопроса**:")

@dp.message(AdminStates.task_number)
async def process_task_number(message: types.Message, state: FSMContext):
    await state.update_data(task_number=message.text)
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

# СПИСОК И УДАЛЕНИЕ
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
    kb = [[InlineKeyboardButton(text=f"❌ [{b['grade']}] {b['title']}", callback_data=f"confirm_del_book_{b['_id']}")] for b in books]
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

# API СЕРВЕР
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
