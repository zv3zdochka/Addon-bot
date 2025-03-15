import logging
import os
import subprocess
import wave
import json
import aiml

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from g4f.client import Client
from vosk import Model, KaldiRecognizer

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

client = Client()
user_history = {}

kernel = aiml.Kernel()
kernel.learn("advertisement.aiml")

with open('base.txt', 'r', encoding="UTF-8") as f:
    initial_prompt = f.readlines()

vosk_model_path = "model"
if not os.path.exists(vosk_model_path):
    logger.error(f"Модель по пути '{vosk_model_path}' не найдена.")
    exit(1)
vosk_model = Model(vosk_model_path)


def process_user_message(user_id: int, message_text: str, update: Update, context: CallbackContext) -> None:
    """
    Обрабатывает текстовое сообщение от пользователя. Сначала пытается ответить с помощью AIML.
    Если AIML не возвращает ответ, используется модель gpt-4o-mini. Сообщения сохраняются в истории диалога.

    Args:
        user_id (int): Идентификатор пользователя.
        message_text (str): Текст сообщения пользователя.
        update (Update): Объект обновления Telegram.
        context (CallbackContext): Контекст обновления.
    """
    if user_id not in user_history:
        user_history[user_id] = [{"role": "system", "content": initial_prompt}]
    user_history[user_id].append({"role": "user", "content": message_text})

    aiml_response = kernel.respond(message_text)
    if aiml_response:
        update.message.reply_text(aiml_response)
        user_history[user_id].append({"role": "assistant", "content": aiml_response})
    else:
        attempts = 0
        while True:
            if attempts == 10:
                update.message.reply_text("GPT is unavailable now, try again later")
                break
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=user_history[user_id],
                web_search=False
            ).choices[0].message.content
            if "Claude" in response:
                attempts += 1
                print("catch claude")
                continue
            attempts = 0
            update.message.reply_text(response)
            user_history[user_id].append({"role": "assistant", "content": response})
            break


def start_new_dialog(update: Update, context: CallbackContext) -> None:
    """
    Начинает новый диалог, переинициализируя историю пользователя.

    Args:
        update (Update): Объект обновления Telegram.
        context (CallbackContext): Контекст обновления.
    """
    user_id = update.message.from_user.id
    user_history[user_id] = [{"role": "system", "content": initial_prompt}]
    update.message.reply_text("Новый диалог начат. Пиши, и я буду отвечать с учетом новых тем!")


def download_conversation(update: Update, context: CallbackContext) -> None:
    """
    Отправляет историю диалога пользователю в виде текстового файла.

    Args:
        update (Update): Объект обновления Telegram.
        context (CallbackContext): Контекст обновления.
    """
    user_id = update.message.from_user.id
    if user_id in user_history and len(user_history[user_id]) > 1:
        filename = f"conversation_{user_id}.txt"
        with open(filename, "w", encoding="utf-8") as file:
            for message in user_history[user_id]:
                if message['role'] != "system":
                    role = message['role'].capitalize()
                    content = message['content']
                    file.write(f"{role}: {content}\n\n")
        with open(filename, 'rb') as file:
            update.message.reply_document(file, filename=filename)
        os.remove(filename)
    else:
        update.message.reply_text("История диалога пуста.")


def handle_text(update: Update, context: CallbackContext) -> None:
    """
    Обрабатывает входящие текстовые сообщения.

    Args:
        update (Update): Объект обновления Telegram.
        context (CallbackContext): Контекст обновления.
    """
    user_id = update.message.from_user.id
    user_message = update.message.text
    process_user_message(user_id, user_message, update, context)


def handle_voice(update: Update, context: CallbackContext) -> None:
    """
    Обрабатывает голосовые сообщения. Скачивает голосовое сообщение, конвертирует OGG в WAV,
    распознает речь с помощью Vosk и передаёт распознанный текст на обработку.

    Args:
        update (Update): Объект обновления Telegram.
        context (CallbackContext): Контекст обновления.
    """
    user_id = update.message.from_user.id
    voice = update.message.voice

    ogg_path = f"{user_id}_voice.ogg"
    wav_path = f"{user_id}_voice.wav"
    try:
        file = voice.get_file()
        file.download(ogg_path)
    except Exception as e:
        logger.error(f"Ошибка скачивания голосового файла: {e}")
        update.message.reply_text("Ошибка при скачивании голосового сообщения.")
        return

    try:
        subprocess.run(["ffmpeg", "-i", ogg_path, wav_path], check=True)
    except Exception as e:
        logger.error(f"Ошибка конвертации файла: {e}")
        update.message.reply_text("Ошибка при конвертации голосового сообщения.")
        if os.path.exists(ogg_path):
            os.remove(ogg_path)
        return

    try:
        wf = wave.open(wav_path, "rb")
    except Exception as e:
        logger.error(f"Ошибка открытия WAV-файла: {e}")
        update.message.reply_text("Ошибка при обработке аудиофайла.")
        os.remove(ogg_path)
        os.remove(wav_path)
        return

    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() not in [8000, 16000, 32000, 44100, 48000]:
        update.message.reply_text(
            "Аудиофайл должен быть в формате WAV с одной дорожкой (моно), 16-битным сэмплом и допустимой частотой дискретизации."
        )
        wf.close()
        os.remove(ogg_path)
        os.remove(wav_path)
        return

    rec = KaldiRecognizer(vosk_model, wf.getframerate())
    while True:
        data = wf.readframes(4000)
        if not data:
            break
        rec.AcceptWaveform(data)
    result = rec.FinalResult()
    wf.close()
    os.remove(ogg_path)
    os.remove(wav_path)

    try:
        result_json = json.loads(result)
        recognized_text = result_json.get("text", "")
    except Exception as e:
        logger.error(f"Ошибка при разборе результата: {e}")
        update.message.reply_text("Ошибка при распознавании речи.")
        return

    if not recognized_text:
        update.message.reply_text("Не удалось распознать голосовое сообщение.")
        return

    process_user_message(user_id, recognized_text, update, context)


def main():
    """
    Основная функция для запуска Telegram-бота. Инициализирует обработчики команд и сообщений.
    """
    TOKEN = '7280723602:AAEuPhvt1SrdQrgRQBxDTIUY8y5EIChaW7U'
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('new_bot', start_new_dialog))
    dispatcher.add_handler(CommandHandler('download_conv', download_conversation))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    dispatcher.add_handler(MessageHandler(Filters.voice, handle_voice))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
