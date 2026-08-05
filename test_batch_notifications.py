#!/usr/bin/env python3
"""
Тестовый скрипт для проверки новой системы батчинга Telegram уведомлений
Facebook Group Poster - Batch Notifications Test
"""

import os
import sys
from datetime import datetime

# Добавляем путь к модулю бота
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from fb_poster import FacebookGroupPoster

def test_batch_notifications():
    """Тестирование новой системы батч-уведомлений"""
    
    print("🔔 Тестирование системы батч-уведомлений Facebook Group Poster")
    print("=" * 70)
    
    # Инициализируем бота
    try:
        bot = FacebookGroupPoster()
        print(f"✅ Бот инициализирован")
        print(f"📱 Telegram уведомления: {'включены' if bot.telegram_notifications_enabled else 'отключены'}")
        print(f"📊 Размер батча: {bot.batch_size} групп")
        
        if not bot.telegram_notifications_enabled:
            print("\n⚠️  Telegram уведомления отключены в config.ini")
            return
            
        if (not bot.telegram_token or not bot.telegram_chat_id or
            bot.telegram_token == 'YOUR_BOT_TOKEN_HERE' or 
            bot.telegram_chat_id == 'YOUR_CHAT_ID_HERE'):
            print("\n⚠️  Не настроены telegram_token или telegram_chat_id в config.ini")
            return
            
    except Exception as e:
        print(f"❌ Ошибка инициализации бота: {e}")
        return
    
    print("\n🧪 Тестируем батч-уведомления...")
    
    # Тест 1: Батч все успешные
    print("\n1️⃣ Тестируем батч 'все успешные'...")
    try:
        bot.send_batch_summary_notification(
            batch_num=1,
            batch_success=10,
            batch_failed=0,
            failed_groups=[],
            total_processed=10,
            total_groups=50
        )
        print("   ✅ Батч-уведомление 'все успешные' отправлено")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    # Тест 2: Батч с ошибками
    print("\n2️⃣ Тестируем батч с ошибками...")
    try:
        failed_groups = [
            ("ID: 123456789", "Could not find post creation element"),
            ("ID: 987654321", "Text entry failed"),
            ("AUTO VERKAUF CH", "Element not clickable")
        ]
        
        bot.send_batch_summary_notification(
            batch_num=2,
            batch_success=7,
            batch_failed=3,
            failed_groups=failed_groups,
            total_processed=20,
            total_groups=50
        )
        print("   ✅ Батч-уведомление 'с ошибками' отправлено")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    # Тест 3: Батч много ошибок
    print("\n3️⃣ Тестируем батч 'много ошибок'...")
    try:
        failed_groups = [
            ("ID: 111111111", "Session expired"),
            ("ID: 222222222", "Group access denied"),
            ("ID: 333333333", "Element not found"),
            ("ID: 444444444", "Timeout waiting for element"),
            ("ID: 555555555", "JavaScript execution failed"),
            ("ID: 666666666", "Network error"),
            ("ID: 777777777", "CAPTCHA appeared")
        ]
        
        bot.send_batch_summary_notification(
            batch_num=3,
            batch_success=2,
            batch_failed=7,
            failed_groups=failed_groups,
            total_processed=29,
            total_groups=50
        )
        print("   ✅ Батч-уведомление 'много ошибок' отправлено")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    # Тест 4: Финальный батч (неполный)
    print("\n4️⃣ Тестируем финальный батч (неполный)...")
    try:
        failed_groups = [
            ("Poznań Car", "Browser session died")
        ]
        
        bot.send_batch_summary_notification(
            batch_num=5,
            batch_success=6,
            batch_failed=1,
            failed_groups=failed_groups,
            total_processed=50,
            total_groups=50
        )
        print("   ✅ Финальный батч-уведомление отправлено")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
    
    print("\n" + "=" * 70)
    print("🎉 Тестирование батч-уведомлений завершено!")
    print("\n💡 Проверьте ваш Telegram чат для подтверждения получения уведомлений")
    print("\n📊 Теперь при постинге вы будете получать:")
    print(f"   • Сводку каждые {bot.batch_size} групп")
    print("   • Список неудачных групп с причинами")
    print("   • Общий прогресс и статистику")
    print("   • Без спама отдельных уведомлений")

if __name__ == "__main__":
    test_batch_notifications() 