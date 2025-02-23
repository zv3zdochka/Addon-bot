from flask import Flask, request, jsonify
import logging
import os

# Создаём Flask-приложение, папка static — для index.html
app = Flask(__name__, static_folder='static', static_url_path='')

# Настраиваем базовое логирование в файл logs.txt
logging.basicConfig(
    filename='logs.txt',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s'
)

@app.route('/')
def index():
    # При заходе на корень отдаем index.html (лежит в static/)
    return app.send_static_file('index.html')

@app.route('/save_log', methods=['POST'])
def save_log():
    """
    Маршрут, на который фронтенд отправляет POST-запрос с лог-сообщением.
    """
    data = request.get_json()
    msg = data.get('message', 'No message provided')
    # Пишем сообщение в файл logs.txt
    logging.info(msg)
    # Возвращаем JSON-ответ, что всё ок
    return jsonify({'status': 'ok', 'message': 'logged successfully'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
