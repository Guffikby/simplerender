import os
import re
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise ValueError("ОШИБКА: Переменная окружения MONGO_URI не задана!")

cluster = AsyncIOMotorClient(MONGO_URI)
db = cluster["simple_gdz_db"]

subjects_collection = db["subjects"]
books_collection = db["books"]
tasks_collection = db["tasks"]

def clean_text(text: str) -> str:
    """Очищает строку от эмодзи и лишних спецсимволов для корректной сортировки"""
    if not text:
        return ""
    # Вырезаем символы из диапазонов эмодзи и значков
    clean = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff\u2000-\u206f]', '', text)
    return clean.strip()

def extract_number(text: str) -> int:
    """Извлекает первое число из строки для сортировки (например: '7 класс' -> 7, '№12' -> 12)"""
    match = re.search(r'\d+', text or '')
    return int(match.group()) if match else 999

# --- ПРЕДМЕТЫ ---
async def add_subject(title: str):
    return await subjects_collection.insert_one({"title": clean_text(title)})

async def get_all_subjects():
    subjects = await subjects_collection.find().to_list(length=100)
    return sorted(subjects, key=lambda x: clean_text(x.get("title", "")).lower())

async def delete_subject(subject_id: str):
    await subjects_collection.delete_one({"_id": ObjectId(subject_id)})
    books = await books_collection.find({"subject_id": subject_id}).to_list(length=500)
    for b in books:
        await delete_book(str(b["_id"]))

# --- УЧЕБНИКИ ---
async def add_book(subject_id: str, title: str, grade: str, year: str, cover_file_id: str = None):
    return await books_collection.insert_one({
        "subject_id": subject_id,
        "title": clean_text(title),
        "grade": clean_text(grade),
        "year": clean_text(year),
        "cover_file_id": cover_file_id
    })

async def get_all_books():
    books = await books_collection.find().to_list(length=200)
    # Сортировка по номеру класса, затем по названию
    return sorted(books, key=lambda b: (
        extract_number(b.get("grade", "")),
        clean_text(b.get("title", "")).lower()
    ))

async def update_book_cover(book_id: str, cover_file_id: str):
    return await books_collection.update_one(
        {"_id": ObjectId(book_id)},
        {"$set": {"cover_file_id": cover_file_id}}
    )

async def delete_book(book_id: str):
    await books_collection.delete_one({"_id": ObjectId(book_id)})
    await tasks_collection.delete_many({"book_id": book_id})

# --- ЗАДАНИЯ (УПРАЖНЕНИЯ) ---
async def add_task(book_id: str, chapter: str, paragraph: str, category: str, task_number: str, image_id: str, answer_text: str = ""):
    return await tasks_collection.insert_one({
        "book_id": book_id,
        "chapter": clean_text(chapter),
        "paragraph": clean_text(paragraph),
        "category": clean_text(category),
        "task_number": clean_text(task_number),
        "image_id": image_id,
        "answer_text": answer_text
    })

async def get_all_tasks():
    tasks = await tasks_collection.find().to_list(length=2000)
    # Сортировка по главе, номеру параграфа и номеру задания
    return sorted(tasks, key=lambda t: (
        clean_text(t.get("chapter", "")).lower(),
        extract_number(t.get("paragraph", "")),
        clean_text(t.get("category", "")).lower(),
        extract_number(t.get("task_number", ""))
    ))

async def update_task_solution(task_id: str, image_id: str, answer_text: str = ""):
    return await tasks_collection.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"image_id": image_id, "answer_text": answer_text}}
    )

async def delete_task(task_id: str):
    await tasks_collection.delete_one({"_id": ObjectId(task_id)})

# --- СБОРКА КАТАЛОГА ДЛЯ REST API ---
async def get_full_catalog():
    subjects = await get_all_subjects()
    books = await get_all_books()
    tasks = await get_all_tasks()

    result = []
    for s in subjects:
        s_id = str(s["_id"])
        s_books = [b for b in books if b.get("subject_id") == s_id]
        
        formatted_books = []
        for b in s_books:
            b_id = str(b["_id"])
            b_tasks = [t for t in tasks if t.get("book_id") == b_id]
            
            formatted_tasks = []
            for t in b_tasks:
                formatted_tasks.append({
                    "id": str(t["_id"]),
                    "chapter": t.get("chapter", "Без главы"),
                    "paragraph": t.get("paragraph", "Без параграфа"),
                    "category": t.get("category", "Вопросы и задания"),
                    "task_number": t.get("task_number", ""),
                    "photo_url": f"/api/photo/{t['image_id']}" if t.get("image_id") else None,
                    "answer_text": t.get("answer_text", "")
                })

            formatted_books.append({
                "id": b_id,
                "title": b.get("title", ""),
                "grade": b.get("grade", ""),
                "year": b.get("year", ""),
                "cover_url": f"/api/photo/{b['cover_file_id']}" if b.get("cover_file_id") else None,
                "tasks": formatted_tasks
            })

        result.append({
            "id": s_id,
            "title": s.get("title", ""),
            "books": formatted_books
        })

    return result
