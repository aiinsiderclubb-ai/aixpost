#!/usr/bin/env python3
"""
Тестовый скрипт для проверки Telegram уведомлений
Facebook Group Poster - Telegram Integration Test

Этот скрипт позволяет протестировать Telegram уведомления без запуска полного процесса постинга.
"""

import os
import sys
from datetime import datetime

# Добавляем путь к модулю бота
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from fb_poster import FacebookGroupPoster

def test_telegram_notifications():
    """Тестирование всех типов Telegram уведомлений"""
    
    print("🔔 Тестирование Telegram уведомлений для Facebook Group Poster")
    print("=" * 60)
    
    # Инициализируем бота
    try:
        bot = FacebookGroupPoster()
        print(f"✅ Бот инициализирован")
        print(f"📱 Telegram уведомления: {'включены' if bot.telegram_notifications_enabled else 'отключены'}")
        print(f"🔧 Режим 'только ошибки': {'да' if bot.telegram_errors_only else 'нет'}")
        
        # Отладочная информация
        print(f"\n🔍 Отладочная информация:")
        print(f"   Bot Token: {'установлен' if bot.telegram_token and bot.telegram_token != 'YOUR_BOT_TOKEN_HERE' else 'НЕ УСТАНОВЛЕН'}")
        print(f"   Chat ID: {'установлен' if bot.telegram_chat_id and bot.telegram_chat_id != 'YOUR_CHAT_ID_HERE' else 'НЕ УСТАНОВЛЕН'}")
        if bot.telegram_chat_id and bot.telegram_chat_id != 'YOUR_CHAT_ID_HERE':
            print(f"   Chat ID значение: {bot.telegram_chat_id} (тип: {type(bot.telegram_chat_id)})")
        
        if not bot.telegram_notifications_enabled:
            print("\n⚠️  Telegram уведомления отключены в config.ini")
            print("   Для тестирования установите notifications_enabled = true")
            return
            
        if (not bot.telegram_token or not bot.telegram_chat_id or
            bot.telegram_token == 'YOUR_BOT_TOKEN_HERE' or 
            bot.telegram_chat_id == 'YOUR_CHAT_ID_HERE'):
            print("\n⚠️  Не настроены telegram_bot_token или telegram_chat_id в config.ini")
            print("   Пожалуйста, настройте эти параметры для тестирования")
            return
            
    except Exception as e:
        print(f"❌ Ошибка инициализации бота: {e}")
        return
    
    print("\n🧪 Начинаем тестирование уведомлений...")
    
    # Тест 1: Уведомление об ошибке
    print("\n1️⃣ Тестируем уведомление об ошибке...")
    try:
        test_group_url = "https://www.facebook.com/groups/123456789/"
        test_error = "ElementNotFound (textarea)"
        bot.send_error_notification(test_group_url, test_error)
        print("   ✅ Уведомление об ошибке отправлено")
    except Exception as e:
        print(f"   ❌ Ошибка отправки уведомления об ошибке: {e}")
    
    # Тест 2: Уведомление об успехе (если не включен режим "только ошибки")
    if not bot.telegram_errors_only:
        print("\n2️⃣ Тестируем уведомление об успехе...")
        try:
            test_group_url = "https://www.facebook.com/groups/987654321/"
            bot.groups_total = 50  # Симулируем общее количество групп
            bot.success_count = 25  # Симулируем текущий прогресс
            bot.send_success_notification(test_group_url)
            print("   ✅ Уведомление об успехе отправлено")
        except Exception as e:
            print(f"   ❌ Ошибка отправки уведомления об успехе: {e}")
    else:
        print("\n2️⃣ Пропускаем тест уведомления об успехе (включен режим 'только ошибки')")
    
    # Тест 3: Итоговое уведомление
    print("\n3️⃣ Тестируем итоговое уведомление...")
    try:
        # Симулируем завершенную сессию
        bot.session_start_time = datetime.now()
        bot.success_count = 45
        bot.error_count = 5
        bot.send_session_complete_notification()
        print("   ✅ Итоговое уведомление отправлено")
    except Exception as e:
        print(f"   ❌ Ошибка отправки итогового уведомления: {e}")
    
    # Тест 4: Прямое уведомление
    print("\n4️⃣ Тестируем прямое уведомление...")
    try:
        test_message = (
            "🧪 <b>Тестовое уведомление</b>\n"
            "📅 Время: " + datetime.now().strftime("%H:%M:%S") + "\n"
            "✅ Telegram интеграция работает!"
        )
        bot.send_telegram_notification(test_message, error_level=False)
        print("   ✅ Прямое уведомление отправлено")
    except Exception as e:
        print(f"   ❌ Ошибка отправки прямого уведомления: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 Тестирование завершено!")
    print("\n💡 Проверьте ваш Telegram чат для подтверждения получения уведомлений")
    print("📋 Если уведомления не приходят, проверьте:")
    print("   • Правильность telegram_bot_token")
    print("   • Правильность telegram_chat_id") 
    print("   • Что бот добавлен в чат (для групповых чатов)")
    print("   • Интернет соединение")

def show_config_help():
    """Показать справку по настройке конфигурации"""
    print("\n📖 Справка по настройке Telegram уведомлений:")
    print("=" * 50)
    print("\n1. Создайте бота в Telegram:")
    print("   • Напишите @BotFather в Telegram")
    print("   • Отправьте команду /newbot")
    print("   • Следуйте инструкциям и получите токен")
    
    print("\n2. Получите Chat ID:")
    print("   • Для личных сообщений: напишите @userinfobot")
    print("   • Для групп: добавьте бота в группу и используйте @userinfobot")
    
    print("\n3. Настройте config.ini:")
    print("   [Telegram]")
    print("   telegram_bot_token = ВАШ_ТОКЕН_БОТА")
    print("   telegram_chat_id = ВАШ_CHAT_ID")
    print("   notifications_enabled = true")
    print("   errors_only = false")
    
    print("\n4. Запустите тест:")
    print("   python test_telegram_notifications.py")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h', 'help']:
        show_config_help()
    else:
        test_telegram_notifications() 