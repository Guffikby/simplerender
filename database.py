import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise ValueError("ОШИБКА: Переменная окружения MONGO_URI не задана!")

cluster = AsyncIOMotorClient(MONGO_URI)
db = cluster["simple_gdz_db"]

subjects_collection = db["subjects"]
books_collection = db["books"]
tasks_collection = db["tasks"]

# --- ПРЕДМЕТЫ ---
async def add_subject(title: str):
    return await subjects_collection.insert_one({"title": title})

async def get_all_subjects():
    return await subjects_collection.find().to_list(length=100)

async def delete_subject(subject_id: str):
    from bson import ObjectId
    oid = ObjectId(subject_id)
    await subjects_collection.delete_one({"_id": oid})
    await books_collection.delete_many({"subject_id": subject_id})

# --- УЧЕБНИКИ ---
async def add_book(subject_id: str, title: str, grade: str, year: str, cover_file_id: str = None):
    return await books_collection.insert_one({
        "subject_id": subject_id,
        "title": title,
        "grade": grade,
        "year": year,
        "cover_file_id": cover_file_id
    })

async def get_books_by_subject(subject_id: str):
    return await books_collection.find({"subject_id": subject_id}).to_list(length=100)

async def get_all_books():
    return await books_collection.find().to_list(length=200)

async def delete_book(book_id: str):
    from bson import ObjectId
    oid = ObjectId(book_id)
    await books_collection.delete_one({"_id": oid})
    await tasks_collection.delete_many({"book_id": book_id})

# --- ЗАДАНИЯ ---
async def add_task(book_id: str, chapter: str, task_type: str, task_number: str, image_id: str, answer_text: str = ""):
    return await tasks_collection.insert_one({
        "book_id": book_id,
        "chapter": chapter,
        "task_type": task_type,
        "task_number": task_number,
        "image_id": image_id,
        "answer_text": answer_text
    })

async def get_tasks_by_book(book_id: str):
    return await tasks_collection.find({"book_id": book_id}).to_list(length=500)

async def delete_task(task_id: str):
    from bson import ObjectId
    await tasks_collection.delete_one({"_id": ObjectId(task_id)})

# --- ОБЩАЯ СБОРКА ДЛЯ API ---
async def get_full_catalog():
    subjects = await get_all_subjects()
    books = await get_all_books()
    tasks = await tasks_collection.find().to_list(length=2000)

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
                    "task_type": t.get("task_type", "Задания"),
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
