import logging
import os
import pickle
import asyncio
import requests
from datetime import datetime
from typing import Dict, Any

from telegram import Update, User
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    PicklePersistence,
    filters,
)

from config import TG_TOKEN, DEEPSEEK_API_KEY
from utils import load_materials
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# ---------------------------------------------------------------------------
# Конфигурация путей (жёстко привязаны к каталогу бота)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
MATERIALS_DIR = os.path.join(BASE_DIR, "materials")
PICKLE = os.path.join(BASE_DIR, "sessions.pkl")
ACCOUNTS_PATH = "/opt/mentors/client1/accounts.pkl"
PERSONA_PATH = os.path.join(BASE_DIR, "persona.txt")

# ---------------------------------------------------------------------------
# Получение текущей персоны
# ---------------------------------------------------------------------------
def get_current_persona() -> str:
    try:
        with open(PERSONA_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        logging.exception("Не удалось прочитать persona.txt")
        return "Ты — тьютор по курсу. Отвечай доброжелательно и строго по материалам."

# ---------------------------------------------------------------------------
# Логи
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# ---------------------------------------------------------------------------
# Динамическое чтение материалов
# ---------------------------------------------------------------------------
_materials_cache: list[str] | None = None
_materials_mtime: float | None = None

def load_materials_if_changed() -> list[str]:
    global _materials_cache, _materials_mtime

    try:
        files = [f for f in os.listdir(MATERIALS_DIR) if f.endswith(".txt")]
    except FileNotFoundError:
        logging.warning("Каталог материалов не найден: %s", MATERIALS_DIR)
        _materials_cache, _materials_mtime = [], 0
        return _materials_cache

    current_mtime = max((os.path.getmtime(os.path.join(MATERIALS_DIR, f)) for f in files), default=0)

    if _materials_cache is None or current_mtime != _materials_mtime:
        _materials_cache = load_materials(MATERIALS_DIR)
        _materials_mtime = current_mtime
        logging.info("Материалы перечитаны (%d файлов)", len(_materials_cache))

    return _materials_cache

# ---------------------------------------------------------------------------
# Анализ релевантных кусков
# ---------------------------------------------------------------------------
def get_relevant_chunks(question: str, documents: list[str] | dict, top_k: int = 15, final_k: int = 5) -> list[str]:
    # Поддержка dict: извлекаем только тексты
    if isinstance(documents, dict):
        documents = list(documents.values())
    if not documents:
        return []

    try:
        vectorizer = TfidfVectorizer(stop_words="english")
        tfidf_matrix = vectorizer.fit_transform([question] + documents)

        similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
        top_indices = np.argsort(similarities)[::-1][:top_k]
        top_chunks = [documents[i] for i in top_indices]

        final_chunks = []
        used_vectors = []

        for i in range(len(top_chunks)):
            vec = tfidf_matrix[top_indices[i] + 1]
            if all(cosine_similarity(vec, v)[0][0] < 0.85 for v in used_vectors):
                final_chunks.append(top_chunks[i])
                used_vectors.append(vec)
            if len(final_chunks) >= final_k:
                break

        return final_chunks

    except Exception as e:
        logging.exception("Ошибка при поиске релевантных кусков: %s", str(e))
        return []

# ---------------------------------------------------------------------------
# Сохранение метаданных пользователя
# ---------------------------------------------------------------------------
def _store_user_meta(u: User, user_data: Dict[str, Any]) -> None:
    user_data["user_id"] = u.id
    if u.username:
        user_data["username"] = u.username.lstrip("@")
    if u.first_name:
        user_data["first_name"] = u.first_name
    if u.last_name:
        user_data["last_name"] = u.last_name

# ---------------------------------------------------------------------------
# Проверка доступа
# ---------------------------------------------------------------------------
def is_allowed(user: User) -> bool:
    if not os.path.exists(ACCOUNTS_PATH):
        return True

    with open(ACCOUNTS_PATH, "rb") as f:
        data = pickle.load(f)

    if data.get("allow_all"):
        return True

    username = (user.username or "").lstrip("@")

    for u in data.get("accounts", []):
        if u.get("username") == username and u.get("status", "active") == "active":
            return True

    for grp in data.get("groups", {}).values():
        for u in grp:
            if u.get("username") == username and u.get("status", "active") == "active":
                return True

    return False

# ---------------------------------------------------------------------------
# DeepSeek helper
# ---------------------------------------------------------------------------
def ask_deepseek(question: str, chunks: list[str], history_msgs: list[dict], api_key: str) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[{i}] Источник:\n{chunk}")

    context_text = "\n\n".join(parts)

    messages = [
        {"role": "system", "content": get_current_persona()},
    ] + history_msgs + [
        {"role": "user", "content": question},
        {"role": "system", "content": "Материалы курса (из разных источников):\n\n" + context_text},
    ]

    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.1,
        "stream": False,
    }

    try:
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        logging.exception("DeepSeek API error")
        return "⚠️ Произошла ошибка. Попробуйте позже."

# ---------------------------------------------------------------------------
# Telegram-handlers
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user):
        await update.message.reply_text("⛔️ Нет доступа. Обратитесь к администратору.")
        return
    _store_user_meta(update.effective_user, context.user_data)
    await update.message.reply_text(
        """🚀 Добро пожаловать на курс «Деньги на Telegram»!
Я сделаю прохождение курса для тебя легким и прибыльным💸

А теперь давай знакомиться! 😉
💡Напиши какой продукт или услугу ты уже продаёшь или планируешь создать?
И сразу получи готовый план действий.""",
        parse_mode=ParseMode.MARKDOWN,
    )

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user):
        await update.message.reply_text("⛔️ Нет доступа. Обратитесь к администратору.")
        return
    context.user_data.clear()
    _store_user_meta(update.effective_user, context.user_data)
    await update.message.reply_text("История диалога очищена.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user):
        await update.message.reply_text("⛔️ Нет доступа. Обратитесь к администратору.")
        return

    _store_user_meta(update.effective_user, context.user_data)

    text = update.message.text.strip()
    # Сохраняем время прихода вопроса
    now_user = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    history = context.user_data.setdefault("history", [])
    history.append({"role": "user", "content": text, "timestamp": now_user})

    materials = load_materials_if_changed()
    logging.info("Материалов загружено: %d", len(materials))
    chunks = get_relevant_chunks(text, materials)
    logging.info("Найдено %d кусков", len(chunks))
    for idx, ch in enumerate(chunks[:3], 1):
        logging.info("Кусок %d: %s", idx, ch)

    # Собираем последние 20 сообщений из истории
    last_msgs = history[-20:]
    history_msgs = [{"role": item["role"], "content": item["content"]} for item in last_msgs]
    answer = await asyncio.to_thread(ask_deepseek, text, chunks, history_msgs, DEEPSEEK_API_KEY)
    answer = re.sub(r"^###\s*(.*)$", r"**\1**", answer, flags=re.MULTILINE)
    answer = re.sub(r"^##\s*(.*)$", r"**\1**", answer, flags=re.MULTILINE)

    # Сохраняем время отправки ответа бота (обновляем метку после генерации)
    now_bot = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history.append({"role": "assistant", "content": answer, "timestamp": now_bot})
    context.user_data["history"] = history

    await update.message.reply_text(answer, parse_mode=ParseMode.MARKDOWN)

# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------
def main():
    persistence = PicklePersistence(filepath=PICKLE)
    app = (
        Application.builder()
        .token(TG_TOKEN)
        .persistence(persistence)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Бот запущен. MATERIALS_DIR=%s", MATERIALS_DIR)
    app.run_polling()

if __name__ == "__main__":
    main()
