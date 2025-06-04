# /opt/admin/utils/stats.py

import os
import pickle
import datetime as dt
import pandas as pd

# Путь к папке с сессиями
PERSIST_ROOT = "/opt/mentors"

def load_df(login: str) -> pd.DataFrame:
    """
    Загружает все сообщения из sessions.pkl в DataFrame с колонками:
      - uid  (ID пользователя или чата)
      - text (текст сообщения)
      - dt   (datetime объект)
    При этом кидает в консоль отладочную информацию.
    """
    pkl_path = os.path.join(PERSIST_ROOT, login, "sessions.pkl")
    print(f">> DEBUG: loading sessions from {pkl_path!r} (exists: {os.path.exists(pkl_path)})")
    if not os.path.exists(pkl_path):
        # если файла нет — возвращаем пустой DF
        return pd.DataFrame(columns=["uid", "text", "dt"])

    with open(pkl_path, "rb") as f:
        data = pickle.load(f)

    # Отладка структуры
    print(">> DEBUG: keys in persistence:", list(data.keys()))

    # Собираем все сообщения
    messages = []

    # 1) Пытаемся из user_data
    for uid, udata in data.get("user_data", {}).items():
        for msg in udata.get("messages", []):
            messages.append((uid, msg.get("text", ""), msg.get("ts")))

    # 2) Если не нашли ни одного, проверяем chat_data
    if not messages:
        for chat_id, cdata in data.get("chat_data", {}).items():
            for msg in cdata.get("messages", []):
                messages.append((chat_id, msg.get("text", ""), msg.get("ts")))

    # Превращаем в DataFrame
    rows = []
    for uid, text, ts in messages:
        try:
            dt_obj = dt.datetime.fromisoformat(ts)
        except Exception as e:
            # некорректный формат даты — пропускаем
            continue
        rows.append({"uid": uid, "text": text, "dt": dt_obj})

    df = pd.DataFrame(rows)
    print(f">> DEBUG: loaded {len(df)} messages into DataFrame")
    if not df.empty:
        print(df.head())

    return df

def top_questions(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    # ... ваш существующий код ...
    from sklearn.feature_extraction.text import TfidfVectorizer
    from nltk.corpus import stopwords

    tfidf = TfidfVectorizer(stop_words=stopwords.words("russian"))
    X = tfidf.fit_transform(df["text"].astype(str))
    scores = X.sum(axis=0).A1
    terms  = tfidf.get_feature_names_out()
    top    = sorted(zip(terms, scores), key=lambda t: t[1], reverse=True)[:n]
    return pd.DataFrame(top, columns=["term", "score"])

def hour_heatmap(df: pd.DataFrame) -> pd.DataFrame:
    if "dt" not in df.columns or df.empty:
        # возвращаем нулевую матрицу 7×24
        return pd.DataFrame([[0]*24 for _ in range(7)])
    df["hour"] = df["dt"].dt.hour
    df["dow"]  = df["dt"].dt.dayofweek
    return df.pivot_table(
        index="dow", columns="hour", values="uid",
        aggfunc="count", fill_value=0
    )
