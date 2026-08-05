"""
Facebook Group Poster - Dashboard Application
Flask-based web interface to control the Facebook group posting bot
"""

import os
from flask import Flask, render_template, jsonify, request

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_status')
def get_status():
    return jsonify({
        'status': 'idle',
        'posts_completed': 6,
        'posts_failed': 0,
        'groups_total': 6,
        'success_rate': 100,
        'current_message': 'Test message',
        'group_statuses': {
            'group1': {
                'name': 'Group 1',
                'url': 'https://facebook.com/groups/group1',
                'status': 'success',
                'time': '2023-05-18 15:30:45',
                'message': 'Hello world'
            },
            'group2': {
                'name': 'Group 2',
                'url': 'https://facebook.com/groups/group2',
                'status': 'success',
                'time': '2023-05-18 15:32:10',
                'message': 'Hello world'
            },
        }
    })

@app.route('/fetch_my_groups', methods=['POST'])
def fetch_my_groups():
    """Заглушка для эмуляции работы с Facebook"""
    return jsonify({
        'status': 'started',
        'message': 'Начался фоновый процесс извлечения групп Facebook. В данной минимальной версии это тестовая заглушка.',
        'using_session': True,
        'headless_warning': False
    })

@app.route('/get_logs')
def get_logs():
    """Вернуть тестовые логи"""
    return jsonify({
        'logs': [
            {'timestamp': '2023-05-18 15:30:00', 'level': 'INFO', 'message': 'Тестовый лог 1'},
            {'timestamp': '2023-05-18 15:31:00', 'level': 'INFO', 'message': 'Тестовый лог 2'},
            {'timestamp': '2023-05-18 15:32:00', 'level': 'WARNING', 'message': 'Тестовое предупреждение'}
        ]
    })

@app.route('/get_history')
def get_history():
    """Вернуть тестовую историю постов"""
    return jsonify({
        'status': 'success',
        'history': [
            {'date': '2023-05-18', 'group': 'Group 1', 'status': 'success'},
            {'date': '2023-05-18', 'group': 'Group 2', 'status': 'success'}
        ],
        'statistics': {
            'total': 2,
            'success': 2,
            'failed': 0
        }
    })

@app.route('/get_settings')
def get_settings():
    """Вернуть тестовые настройки"""
    return jsonify({
        'status': 'success',
        'settings': {
            'username': 'test@example.com',
            'has_password': True,
            'min_delay': 10,
            'max_delay': 60,
            'headless_mode': False,
            'max_groups': 20
        }
    })

@app.route('/get_templates')
def get_templates():
    """Вернуть тестовые шаблоны сообщений"""
    return jsonify({
        'status': 'success',
        'templates': [
            {'id': '1', 'name': 'Шаблон 1', 'content': 'Текст шаблона 1'},
            {'id': '2', 'name': 'Шаблон 2', 'content': 'Текст шаблона 2'}
        ]
    })

@app.route('/get_my_groups')
def get_my_groups():
    """Получить список групп Facebook"""
    return jsonify({
        'status': 'success',
        'groups': [
            {'name': 'Ukraine Fan Club', 'url': 'https://facebook.com/groups/ukraine-fan-club'},
            {'name': 'IT Professionals UA', 'url': 'https://facebook.com/groups/it-professionals-ua'},
            {'name': 'Kyiv News', 'url': 'https://facebook.com/groups/kyiv-news'},
            {'name': 'Odessa Support', 'url': 'https://facebook.com/groups/odessa-support'},
            {'name': 'Kharkiv Community', 'url': 'https://facebook.com/groups/kharkiv-community'},
            {'name': 'Lviv Events', 'url': 'https://facebook.com/groups/lviv-events'}
        ],
        'fetched': True
    })

# Run the app
if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=8080)
    except OSError as e:
        if 'Address already in use' in str(e):
            print("Error: Port 8080 is already in use.")
            print("Please stop any running instance of the app first, or use a different port.")
            print("For example: app.run(debug=True, host='0.0.0.0', port=8081)")
        else:
            print(f"Error starting the app: {e}") 