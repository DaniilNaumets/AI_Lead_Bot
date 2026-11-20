import json
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

import os
from dotenv import load_dotenv

load_dotenv() # Загружаем ключи из .env

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ КЛИЕНТОВ
# ==========================================

# Подключение к AIAI.BY (Белорусский сервер)
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.aiai.by/v1" 
)

# Подключение к Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
gs_client = gspread.authorize(creds)
sheet = gs_client.open(SHEET_NAME).sheet1

# Заголовки таблицы (добавятся автоматически при первом запуске)
HEADERS = ["date", "name", "contact", "request_type", "urgency", "budget", "summary", "raw_text"]
try:
    if not sheet.row_values(1):
        sheet.append_row(HEADERS)
except Exception as e:
    print(f"Не удалось проверить заголовки таблицы: {e}")

# ==========================================
# 3. ФУНКЦИЯ ОБРАБОТКИ ЗАЯВКИ ЧЕРЕЗ LLM
# ==========================================

def process_lead_with_ai(text: str) -> dict:
    """Отправляет текст в нейросеть и получает структурированные данные в формате JSON."""
    
    model_name = "gpt-4o" # Модель на AIAI.BY
    
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": """Ты — ассистент по обработке входящих заявок.
Извлеки из текста пользователя данные и верни ТОЛЬКО JSON без markdown-разметки:
{
  "name": "имя или null",
  "contact": "телефон/email/telegram или null",
  "request_type": "краткий тип запроса (сайт, бот, консультация и т.д.)",
  "urgency": "срочно / средний / низкий",
  "budget": "бюджет или null",
  "summary": "краткое описание запроса в 1 предложении"
}"""},
            {"role": "user", "content": text}
        ],
        temperature=0.1,
        response_format={"type": "json_object"} # Гарантирует, что ответ будет в JSON
    )
    return json.loads(response.choices[0].message.content)

# ==========================================
# 4. ОБРАБОТЧИК СООБЩЕНИЙ TELEGRAM
# ==========================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user = update.message.from_user
    
    # Получаем username или формируем ссылку по ID
    if user.username:
        contact_info = f"@{user.username}"
    else:
        contact_info = f'<a href="tg://user?id={user.id}">Написать (ID: {user.id})</a>'
    
    # 1. Отправляем текст в нейросеть
    try:
        data = process_lead_with_ai(user_text)
    except Exception as e:
        await update.message.reply_text("Ошибка обработки ИИ. Попробуйте позже.")
        print(f"Ошибка LLM: {e}")
        return
    
    # 2. Сохраняем в Google Sheets
    try:
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            data.get("name") or "Не указано", 
            data.get("contact") or contact_info, 
            data.get("request_type", ""),
            data.get("urgency", ""),
            data.get("budget", ""),
            data.get("summary", ""),
            user_text[:200]
        ]
        sheet.append_row(row)
    except Exception as e:
        print(f"Ошибка записи в Sheets: {e}")
        await update.message.reply_text("Заявка получена, но произошла ошибка сохранения.")
        return
    
    # 3. Отвечаем пользователю
    await update.message.reply_text(
        f"Спасибо! Ваша заявка принята.\n"
        f"Тип: {data.get('request_type', '—')}\n"
        f"Срочность: {data.get('urgency', '—')}"
    )
    
    # 4. Отправляем уведомление вам (админу)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🔔 Новая заявка!\n\n{json.dumps(data, ensure_ascii=False, indent=2)}\n\nКлиент: {contact_info}",
            parse_mode="HTML" # Включаем HTML, чтобы ссылка работала в Телеграме
        )
    except Exception as e:
        print(f"Не удалось отправить уведомление админу: {e}")

# ==========================================
# 5. ЗАПУСК БОТА
# ==========================================

if __name__ == "__main__":
    print("Запуск бота...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Бот будет реагировать на любой текст, кроме команд (например, /start)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Бот успешно запущен! Напишите ему в Telegram.")
    app.run_polling()