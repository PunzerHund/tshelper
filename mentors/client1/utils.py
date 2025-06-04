import os

def load_materials(folder):
    # Загрузка всех материалов в виде словаря: {имя_файла: текст}
    materials = {}
    for fname in os.listdir(folder):
        if fname.endswith('.txt'):
            with open(os.path.join(folder, fname), encoding='utf-8') as f:
                materials[fname] = f.read()
    return materials

def get_relevant_chunks(question, materials, max_length=3000):
    """
    Возвращает самые релевантные куски из всех материалов (простая фильтрация по наличию ключевых слов).
    Ограничивает итоговую длину (max_length символов), чтобы prompt не был слишком большим.
    """
    question_words = set(question.lower().split())
    relevance = []
    for name, text in materials.items():
        score = sum(word in text.lower() for word in question_words)
        if score > 0:
            relevance.append((score, text))
    # Сортируем по релевантности (score)
    relevance.sort(reverse=True)
    result = []
    total_length = 0
    for score, chunk in relevance:
        if total_length + len(chunk) > max_length:
            left = max_length - total_length
            if left > 100:
                result.append(chunk[:left])
            break
        result.append(chunk)
        total_length += len(chunk)
    # Если ничего не найдено — возвращаем первые N символов всех материалов (чтобы не было пусто)
    if not result:
        for text in materials.values():
            if total_length + len(text) > max_length:
                left = max_length - total_length
                if left > 100:
                    result.append(text[:left])
                break
            result.append(text)
            total_length += len(text)
    return result

def make_deepseek_prompt(question, chunks):
    # Задаём чёткую роль ассистента
    base_instruction = (
        "Ты доброжелательный, точный и подробный ассистент-ментор по курсу. "
        "Используй ТОЛЬКО приведённые материалы для ответа на вопрос пользователя. "
        "Если ответа в материалах нет, напиши: «Я могу отвечать только на вопросы по материалам курса».\n\n"
        "Материалы курса:\n"
    )
    context = "\n---\n".join(chunks)
    prompt = f"{base_instruction}{context}\n\nВопрос: {question}\nОтвет:"
    return prompt
