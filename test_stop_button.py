#!/usr/bin/env python3
"""
Тест функциональности кнопки остановки рассылки
"""

import time
import threading
import requests
from bot.fb_poster import FacebookGroupPoster

def test_stop_functionality():
    """Тестирование функциональности остановки"""
    
    print("🔍 Тестирование функциональности кнопки остановки")
    print("=" * 55)
    
    # Создаем экземпляр бота
    bot = FacebookGroupPoster()
    
    print(f"📋 Начальное состояние:")
    print(f"   is_posting: {bot.is_posting}")
    print(f"   stop_posting_flag: {bot.stop_posting_flag}")
    print(f"   stop_posting: {bot.stop_posting}")
    
    # Симулируем начало рассылки
    print(f"\n🚀 Симулируем начало рассылки...")
    bot.is_posting = True
    bot.stop_posting_flag = False
    bot.stop_posting = False
    
    print(f"📋 Состояние после начала рассылки:")
    print(f"   is_posting: {bot.is_posting}")
    print(f"   stop_posting_flag: {bot.stop_posting_flag}")
    print(f"   stop_posting: {bot.stop_posting}")
    
    # Тестируем метод остановки
    print(f"\n⏹️  Вызываем stop_posting_method()...")
    result = bot.stop_posting_method()
    
    print(f"📋 Состояние после вызова stop_posting_method():")
    print(f"   is_posting: {bot.is_posting}")
    print(f"   stop_posting_flag: {bot.stop_posting_flag}")
    print(f"   stop_posting: {bot.stop_posting}")
    print(f"   Результат метода: {result}")
    print(f"   Статус: {bot.stats.get('status', 'Unknown')}")
    
    # Проверяем корректность
    success = True
    if not bot.stop_posting_flag:
        print("❌ ОШИБКА: stop_posting_flag должен быть True")
        success = False
    
    if not bot.stop_posting:
        print("❌ ОШИБКА: stop_posting должен быть True для совместимости")
        success = False
        
    if bot.is_posting:
        print("❌ ОШИБКА: is_posting должен быть False после остановки")
        success = False
        
    if bot.stats.get('status') != 'Stopping':
        print("❌ ОШИБКА: статус должен быть 'Stopping'")
        success = False
    
    if success:
        print("✅ Все проверки пройдены успешно!")
    else:
        print("❌ Некоторые проверки не пройдены!")
    
    return success

def test_api_endpoint():
    """Тестирование API endpoint"""
    
    print(f"\n🌐 Тестирование API endpoint /api/stop_posting")
    print("=" * 55)
    
    try:
        # Тестируем когда нет активной рассылки
        print("📡 Тестируем API когда нет активной рассылки...")
        response = requests.post('http://localhost:8080/api/stop_posting', timeout=5)
        
        if response.status_code == 400:
            data = response.json()
            if 'error' in data and 'No posting in progress' in data['error']:
                print("✅ API корректно отвечает когда нет активной рассылки")
            else:
                print(f"❌ Неожиданный ответ: {data}")
                return False
        else:
            print(f"❌ Неожиданный статус код: {response.status_code}")
            return False
            
        print("✅ API endpoint работает корректно!")
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Не удается подключиться к серверу на localhost:8080")
        print("   Убедитесь, что веб-сервер запущен")
        return False
    except Exception as e:
        print(f"❌ Ошибка при тестировании API: {e}")
        return False

def main():
    """Основная функция тестирования"""
    
    print("🧪 ТЕСТИРОВАНИЕ ФУНКЦИОНАЛЬНОСТИ КНОПКИ ОСТАНОВКИ")
    print("=" * 60)
    
    # Тест 1: Функциональность метода
    test1_success = test_stop_functionality()
    
    # Тест 2: API endpoint
    test2_success = test_api_endpoint()
    
    # Итоговый результат
    print(f"\n📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    print("=" * 30)
    print(f"✅ Тест метода остановки: {'ПРОЙДЕН' if test1_success else 'НЕ ПРОЙДЕН'}")
    print(f"✅ Тест API endpoint: {'ПРОЙДЕН' if test2_success else 'НЕ ПРОЙДЕН'}")
    
    if test1_success and test2_success:
        print(f"\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("   Кнопка остановки должна работать корректно")
    else:
        print(f"\n❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ!")
        print("   Требуется дополнительная отладка")

if __name__ == "__main__":
    main() 