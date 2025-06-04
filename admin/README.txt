MentorWeb – минимальная админ‑панель для управления ботами

1. Развернуть
---------------
sudo mkdir -p /opt/admin
cd /opt/admin
unzip mentorweb.zip
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py   # порт 5041

2. Структура
-------------
routes/      – блюпринты
templates/   – Jinja2‑шаблоны
static/      – CSS/JS
utils.py     – копирование шаблона бота и systemd unit

3. Создание бота
----------------
• Добавить шаблон в /opt/mentorbot
• В админке ввести login
• Проверить systemctl status mentorbot_<login>.service
