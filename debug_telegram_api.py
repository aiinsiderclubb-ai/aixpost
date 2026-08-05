#!/usr/bin/env python3
"""
Отладочный скрипт для тестирования Telegram Bot API
"""

import requests
import configparser
import os

def test_telegram_api():
    """Тестирование прямого взаимодействия с Telegram API"""
    
    print("🔍 Тестирование прямого взаимодействия с Telegram Bot API")
    print("=" * 55)
    
    # Загружаем конфигурацию
    config = configparser.ConfigParser()
    if not os.path.exists('config.ini'):
        print("❌ Файл config.ini не найден!")
        return
    
    config.read('config.ini')
    
    # Получаем данные
    bot_token = config.get('Telegram', 'telegram_bot_token', fallback='')
    chat_id = config.get('Telegram', 'telegram_chat_id', fallback='')
    
    print(f"📋 Конфигурация:")
    print(f"   Bot Token: {'✅ установлен' if bot_token and bot_token != 'YOUR_BOT_TOKEN_HERE' else '❌ НЕ УСТАНОВЛЕН'}")
    print(f"   Chat ID: {'✅ установлен' if chat_id and chat_id != 'YOUR_CHAT_ID_HERE' else '❌ НЕ УСТАНОВЛЕН'}")
    
    if not bot_token or bot_token == 'YOUR_BOT_TOKEN_HERE':
        print("\n❌ Bot Token не настроен! Обновите config.ini")
        return
        
    if not chat_id or chat_id == 'YOUR_CHAT_ID_HERE':
        print("\n❌ Chat ID не настроен! Обновите config.ini")
        return
    
    # Очищаем chat_id
    chat_id_clean = str(chat_id).strip()
    print(f"   Chat ID (очищенный): '{chat_id_clean}' (тип: {type(chat_id_clean)})")
    
    # Тест 1: getMe
    print(f"\n🧪 Тест 1: Проверка бота (getMe)")
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        response = requests.get(url, timeout=10)
        print(f"   Статус: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                bot_info = data.get('result', {})
                print(f"   ✅ Бот найден: @{bot_info.get('username')} ({bot_info.get('first_name')})")
            else:
                print(f"   ❌ Ошибка: {data}")
        else:
            print(f"   ❌ HTTP ошибка: {response.text}")
    except Exception as e:
        print(f"   ❌ Исключение: {e}")
    
    # Тест 2: sendMessage
    print(f"\n🧪 Тест 2: Отправка сообщения (sendMessage)")
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        # Тестируем с data (form-data)
        print("   📤 Попытка 1: requests.post с data (form-data)")
        payload = {
            'chat_id': chat_id_clean,
            'text': '🧪 Тестовое сообщение от отладочного скрипта',
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, data=payload, timeout=10)
        print(f"   Статус: {response.status_code}")
        print(f"   Ответ: {response.text}")
        
        if response.status_code == 200:
            print("   ✅ Сообщение отправлено успешно!")
        else:
            print("   ❌ Ошибка отправки")
            
            # Попробуем с json
            print("   📤 Попытка 2: requests.post с json")
            response2 = requests.post(url, json=payload, timeout=10)
            print(f"   Статус: {response2.status_code}")
            print(f"   Ответ: {response2.text}")
            
    except Exception as e:
        print(f"   ❌ Исключение: {e}")
    
    print(f"\n" + "=" * 55)
    print("🎯 Если тест 1 прошел, но тест 2 не прошел:")
    print("   • Проверьте, что chat_id правильный")
    print("   • Убедитесь, что вы первым написали боту")
    print("   • Для групп: добавьте бота в группу")

if __name__ == "__main__":
    test_telegram_api() 