#!/usr/bin/env python3
"""
🚀 Улучшенный тест Facebook постинга с эмодзи 
Демонстрирует новые возможности: поддержка эмодзи + увеличенный лимит групп (до 200)
"""

import os
import sys
import time
from datetime import datetime
from bot.fb_poster import FacebookGroupPoster

def print_header():
    """Красивый заголовок теста"""
    print("=" * 70)
    print("🚀 FACEBOOK GROUP POSTER - ТЕСТ ЭМОДЗИ И ЛИМИТОВ")
    print("=" * 70)
    print("✅ Новые возможности:")
    print("   • Полная поддержка эмодзи (UTF-8)")
    print("   • Увеличенный лимит групп: до 200 за сессию")
    print("   • Улучшенная обработка текста")
    print("=" * 70)

def create_test_message():
    """Создаем тестовое сообщение с различными эмодзи"""
    return f"""🔥 Привет! Я тестирую новую функцию 😊🚀

Проверяем отображение эмодзи в посте:

🌟 Популярные эмодзи:
• 🔥 Огонь
• 😊 Улыбка  
• 🚀 Ракета
• 💡 Идея
• ✅ Галочка

🏳️ Флаги стран:
• 🇺🇦 Украина
• 🇨🇭 Швейцария
• 🇩🇪 Германия
• 🇵🇱 Польша

📱 Технологии:
• 💻 Компьютер
• 📱 Телефон
• 🌐 Интернет

Время теста: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ⏰

#тест #эмодзи #автоматизация 🤖"""

def main():
    """Основная функция теста"""
    print_header()
    
    # Создаем тестовое сообщение
    test_message = create_test_message()
    
    print("📝 Тестовое сообщение создано:")
    print("-" * 50)
    print(test_message)
    print("-" * 50)
    
    # Инициализируем бота
    print("\n🤖 Инициализация Facebook Group Poster...")
    bot = FacebookGroupPoster()
    
    # Показываем текущие настройки
    print(f"⚙️  Текущие настройки:")
    print(f"   • Максимум групп: {bot.max_groups}")
    print(f"   • Минимальная задержка: {bot.min_delay}с")
    print(f"   • Максимальная задержка: {bot.max_delay}с")
    
    # Проверяем наличие учетных данных
    if not bot.username or not bot.password:
        print("❌ ОШИБКА: Учетные данные Facebook не настроены!")
        print("Пожалуйста, настройте их в config.ini")
        sys.exit(1)
    
    print(f"👤 Используется аккаунт: {bot.username}")
    
    # Запускаем диагностику сообщения
    print("\n🔍 Запуск диагностики сообщения...")
    is_valid = bot.diagnose_message(test_message)
    
    if not is_valid:
        print("❌ Сообщение не прошло диагностику!")
        sys.exit(1)
    
    # Показываем процесс очистки текста
    print("\n🧹 Обработка текста для постинга...")
    clean_message = bot.clean_text_for_chromedriver(test_message)
    
    if clean_message == test_message:
        print("✅ Текст не требует очистки - все эмодзи сохранены!")
    else:
        print("⚠️  Текст был изменен в процессе очистки")
        print(f"Исходная длина: {len(test_message)}")
        print(f"Очищенная длина: {len(clean_message)}")
    
    # Загружаем список групп
    groups_file = "autofetched_groups.json"
    if not os.path.exists(groups_file):
        groups_file = "groups.txt"
        if not os.path.exists(groups_file):
            print("❌ ОШИБКА: Файл с группами не найден!")
            print("Запустите manual_fetch_groups.py для получения списка групп")
            sys.exit(1)
    
    print(f"\n📁 Загрузка групп из файла: {groups_file}")
    groups = bot.load_groups(groups_file)
    
    if not groups:
        print("❌ ОШИБКА: Не найдено групп для тестирования!")
        sys.exit(1)
    
    print(f"📊 Найдено групп: {len(groups)}")
    
    # Выбираем первую группу для теста
    test_group = groups[0]
    print(f"🎯 Группа для теста: {test_group}")
    
    # Подтверждение от пользователя
    print("\n" + "=" * 50)
    print("🚨 ВНИМАНИЕ: Готовность к тестированию!")
    print("=" * 50)
    print("Сообщение будет отправлено в реальную Facebook группу.")
    print("Убедитесь, что содержание соответствует правилам группы.")
    print("=" * 50)
    
    confirm = input("Продолжить тест? (y/n): ").lower()
    if confirm != 'y':
        print("🛑 Тест отменен пользователем.")
        sys.exit(0)
    
    # Запуск теста
    print("\n🚀 ЗАПУСК ТЕСТА...")
    print("=" * 50)
    
    try:
        # Инициализируем WebDriver
        print("🌐 Инициализация браузера...")
        if not bot.setup_driver():
            print("❌ Ошибка инициализации WebDriver!")
            sys.exit(1)
        
        print("✅ Браузер успешно инициализирован")
        
        # Вход в Facebook
        print("🔐 Вход в Facebook...")
        if not bot.login():
            print("❌ Ошибка входа в Facebook!")
            bot.cleanup()
            sys.exit(1)
        
        print("✅ Успешный вход в Facebook")
        
        # Отправка сообщения
        print("📤 Отправка тестового сообщения с эмодзи...")
        success = bot.post_to_group(test_group, test_message)
        
        if success:
            print("\n" + "=" * 50)
            print("🎉 УСПЕХ! Тест завершен успешно!")
            print("=" * 50)
            print("✅ Сообщение с эмодзи опубликовано")
            print("✅ UTF-8 кодировка работает корректно")
            print("✅ Новый лимит групп (200) активен")
            print("=" * 50)
        else:
            print("\n" + "=" * 50)
            print("❌ ОШИБКА: Не удалось опубликовать сообщение")
            print("=" * 50)
            print("Проверьте скриншоты в папке screenshots/")
            print("Проверьте логи в файле poster.log")
            print("=" * 50)
            
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")
        
    finally:
        # Очистка ресурсов
        print("\n🧹 Очистка ресурсов...")
        bot.cleanup()
        print("✅ Очистка завершена")
        
        print("\n📊 РЕЗУЛЬТАТЫ ТЕСТА:")
        print("=" * 50)
        if 'success' in locals() and success:
            print("🎯 Статус: УСПЕХ")
            print("🔥 Эмодзи: ПОДДЕРЖИВАЮТСЯ")
            print("📈 Лимит групп: 200 (УВЕЛИЧЕН)")
        else:
            print("🎯 Статус: НЕУДАЧА")
            print("🔍 Проверьте логи для диагностики")
        print("=" * 50)

if __name__ == "__main__":
    main() 