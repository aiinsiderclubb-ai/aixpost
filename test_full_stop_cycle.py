#!/usr/bin/env python3
"""
Полный тест цикла работы кнопки остановки
Симулирует реальное использование в веб-интерфейсе
"""

import time
import threading
import requests
import json
from bot.fb_poster import FacebookGroupPoster

def simulate_posting_session():
    """Симулирует сессию рассылки с возможностью остановки"""
    
    print("🚀 Симулируем реальную сессию рассылки...")
    
    # Создаем бота
    bot = FacebookGroupPoster()
    
    # Симулируем начало рассылки
    bot.is_posting = True
    bot.stop_posting_flag = False
    bot.stop_posting = False
    bot.stats['status'] = 'Running'
    bot.posts_completed = 0
    bot.posts_failed = 0
    
    print(f"📊 Начальное состояние:")
    print(f"   is_posting: {bot.is_posting}")
    print(f"   status: {bot.stats['status']}")
    print(f"   stop_posting_flag: {bot.stop_posting_flag}")
    
    # Симулируем цикл рассылки
    def posting_loop():
        """Симулирует цикл рассылки по группам"""
        groups = ['group1', 'group2', 'group3', 'group4', 'group5']
        
        for i, group in enumerate(groups):
            # Проверяем флаг остановки
            if bot.stop_posting_flag:
                print(f"⏹️  Остановка обнаружена на группе {i+1}")
                bot.stats['status'] = 'Stopped'
                break
                
            print(f"📤 Отправляем в группу {i+1}/5: {group}")
            bot.posts_completed += 1
            
            # Симулируем время отправки
            time.sleep(1)
            
        # Завершаем рассылку
        bot.is_posting = False
        if bot.stats['status'] == 'Running':
            bot.stats['status'] = 'Completed'
            
        print(f"🏁 Рассылка завершена. Статус: {bot.stats['status']}")
        print(f"📊 Отправлено: {bot.posts_completed} постов")
    
    # Запускаем рассылку в отдельном потоке
    posting_thread = threading.Thread(target=posting_loop)
    posting_thread.daemon = True
    posting_thread.start()
    
    # Ждем немного, затем останавливаем
    time.sleep(2.5)  # Остановим после ~2 групп
    
    print(f"\n⏹️  Пользователь нажал кнопку 'Stop Posting'")
    result = bot.stop_posting_method()
    
    print(f"📋 Результат остановки: {result}")
    print(f"📊 Состояние после остановки:")
    print(f"   is_posting: {bot.is_posting}")
    print(f"   status: {bot.stats['status']}")
    print(f"   stop_posting_flag: {bot.stop_posting_flag}")
    print(f"   posts_completed: {bot.posts_completed}")
    
    # Ждем завершения потока
    posting_thread.join(timeout=3)
    
    print(f"📊 Финальное состояние:")
    print(f"   is_posting: {bot.is_posting}")
    print(f"   status: {bot.stats['status']}")
    print(f"   posts_completed: {bot.posts_completed}")
    
    return bot

def test_api_integration():
    """Тестирует интеграцию с API"""
    
    print(f"\n🌐 Тестируем интеграцию с веб-API...")
    
    try:
        # Проверяем статус
        response = requests.get('http://localhost:8080/api/posting_status', timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API статус работает: is_posting = {data.get('is_posting', 'unknown')}")
        else:
            print(f"❌ Ошибка API статуса: {response.status_code}")
            return False
            
        # Тестируем остановку (должна вернуть ошибку, так как нет активной рассылки)
        response = requests.post('http://localhost:8080/api/stop_posting', timeout=5)
        if response.status_code == 400:
            data = response.json()
            if 'No posting in progress' in data.get('error', ''):
                print(f"✅ API остановки корректно отвечает при отсутствии рассылки")
            else:
                print(f"❌ Неожиданный ответ API: {data}")
                return False
        else:
            print(f"❌ Неожиданный статус код: {response.status_code}")
            return False
            
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Веб-сервер недоступен на localhost:8080")
        return False
    except Exception as e:
        print(f"❌ Ошибка тестирования API: {e}")
        return False

def test_multiple_stop_calls():
    """Тестирует множественные вызовы остановки"""
    
    print(f"\n🔄 Тестируем множественные вызовы остановки...")
    
    bot = FacebookGroupPoster()
    bot.is_posting = True
    bot.stop_posting_flag = False
    
    print(f"📊 Начальное состояние: is_posting={bot.is_posting}")
    
    # Вызываем остановку несколько раз
    for i in range(3):
        print(f"⏹️  Вызов остановки #{i+1}")
        result = bot.stop_posting_method()
        print(f"   Результат: {result}")
        print(f"   is_posting: {bot.is_posting}")
        print(f"   stop_posting_flag: {bot.stop_posting_flag}")
        print(f"   status: {bot.stats['status']}")
        
        if not result:
            print(f"❌ Ошибка при вызове #{i+1}")
            return False
            
    print(f"✅ Множественные вызовы работают корректно")
    return True

def main():
    """Основная функция тестирования"""
    
    print("🧪 ПОЛНЫЙ ТЕСТ ЦИКЛА РАБОТЫ КНОПКИ ОСТАНОВКИ")
    print("=" * 60)
    
    # Тест 1: Симуляция реальной сессии
    print("\n" + "="*50)
    print("ТЕСТ 1: Симуляция реальной сессии рассылки")
    print("="*50)
    
    bot = simulate_posting_session()
    test1_success = (
        not bot.is_posting and 
        bot.stop_posting_flag and 
        bot.stats['status'] in ['Stopping', 'Stopped'] and
        bot.posts_completed > 0 and bot.posts_completed < 5
    )
    
    # Тест 2: API интеграция
    print("\n" + "="*50)
    print("ТЕСТ 2: Интеграция с веб-API")
    print("="*50)
    
    test2_success = test_api_integration()
    
    # Тест 3: Множественные вызовы
    print("\n" + "="*50)
    print("ТЕСТ 3: Множественные вызовы остановки")
    print("="*50)
    
    test3_success = test_multiple_stop_calls()
    
    # Итоговый отчет
    print(f"\n📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    print("=" * 40)
    print(f"✅ Тест симуляции сессии: {'ПРОЙДЕН' if test1_success else 'НЕ ПРОЙДЕН'}")
    print(f"✅ Тест API интеграции: {'ПРОЙДЕН' if test2_success else 'НЕ ПРОЙДЕН'}")
    print(f"✅ Тест множественных вызовов: {'ПРОЙДЕН' if test3_success else 'НЕ ПРОЙДЕН'}")
    
    all_tests_passed = test1_success and test2_success and test3_success
    
    if all_tests_passed:
        print(f"\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("   Кнопка остановки полностью функциональна")
        print("   Система готова к продакшену")
    else:
        print(f"\n❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ!")
        print("   Требуется дополнительная отладка")
        
    print(f"\n🔧 Рекомендации:")
    print("   1. Протестируйте кнопку в веб-интерфейсе")
    print("   2. Запустите реальную рассылку и остановите её")
    print("   3. Проверьте логи на наличие ошибок")
    
    return all_tests_passed

if __name__ == "__main__":
    main() 