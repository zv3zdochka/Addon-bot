import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from g4f.client import Client
import os

# Устанавливаем уровень логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация клиента g4f
client = Client()

# История сообщений
user_history = {}

with open('base.txt', 'r', encoding="UTF-8") as f:
    initial_prompt = f.readlines()


# Функция для начала нового диалога
def start_new_dialog(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    # Очищаем историю сообщений
    user_history[user_id] = [{"role": "system", "content": initial_prompt}]

    # Подтверждение начала нового диалога
    update.message.reply_text("Новый диалог начат. Пиши, и я буду отвечать с учетом новых тем!")


# Функция для отправки истории диалога в файл
def download_conversation(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id

    # Проверяем, есть ли история
    if user_id in user_history and len(user_history[user_id]) > 1:
        # Создаем имя файла
        filename = f"conversation_{user_id}.txt"

        # Записываем историю в файл
        with open(filename, "w", encoding="utf-8") as file:
            for message in user_history[user_id]:

                if message['role'] != "system":
                    role = message['role'].capitalize()
                    content = message['content']
                    file.write(f"{role}: {content}\n\n")

        # Отправляем файл
        with open(filename, 'rb') as file:
            update.message.reply_document(file, filename=filename)

        # Удаляем файл после отправки
        os.remove(filename)
    else:
        update.message.reply_text("История диалога пуста.")


# Функция для обработки сообщений от пользователя
def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    user_message = update.message.text

    # Сохранение истории сообщений
    if user_id not in user_history:
        user_history[user_id] = [{"role": "system", "content": initial_prompt}]

    # Добавляем сообщение пользователя в историю
    user_history[user_id].append({"role": "user", "content": user_message})

    # Отправка запроса к g4f с сохранением истории
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=user_history[user_id],
        web_search=False
    )

    # Получаем ответ от GPT
    bot_reply = response.choices[0].message.content

    # Отправка ответа пользователю
    update.message.reply_text(bot_reply)

    # Обновляем историю сообщений с ответом GPT
    user_history[user_id].append({"role": "assistant", "content": bot_reply})


# Основная функция для запуска бота
def main():
    # Токен бота (получите его от BotFather)
    TOKEN = '7280723602:AAEuPhvt1SrdQrgRQBxDTIUY8y5EIChaW7U'

    # Создаем Updater и Dispatcher
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Добавляем команды
    dispatcher.add_handler(CommandHandler('new_bot', start_new_dialog))
    dispatcher.add_handler(CommandHandler('download_conv', download_conversation))

    # Обработчик сообщений
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    # Запуск бота
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
