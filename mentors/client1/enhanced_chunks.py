from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import logging

def get_relevant_chunks(question: str, documents: list[str], top_k: int = 15, final_k: int = 5) -> list[str]:
    """
    Возвращает наиболее релевантные и разнообразные куски текста из материалов.

    - top_k: сколько максимум извлечь по релевантности
    - final_k: сколько оставить после удаления дубликатов/схожих
    """
    if not documents:
        return []

    try:
        # TF-IDF для всех chunks + вопроса
        vectorizer = TfidfVectorizer(stop_words="english")
        tfidf_matrix = vectorizer.fit_transform([question] + documents)

        # Считаем cosine similarity между вопросом и всеми кусками
        similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()

        # Берем top_k самых похожих
        top_indices = np.argsort(similarities)[::-1][:top_k]
        top_chunks = [documents[i] for i in top_indices]

        # Дополнительно: фильтрация по разнообразию
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

