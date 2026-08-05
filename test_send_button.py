#!/usr/bin/env python3
"""
Специальный тест для кнопки "Отправить"
Проверяет найдет ли бот кнопку с текстом "Отправить" в диалоге создания поста
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.fb_poster import FacebookGroupPoster
import time

def main():
    print("🔍 Тест поиска кнопки 'Отправить'")
    print("=" * 50)
    
    # Короткое тестовое сообщение
    test_message = "Тест кнопки 'Отправить' " + time.strftime("%H:%M:%S")
    
    print(f"📝 Тестовое сообщение: {test_message}")
    print()
    
    # Инициализация бота с видимым браузером
    poster = FacebookGroupPoster(headless=False)
    
    try:
        print("🔧 Настройка WebDriver...")
        if not poster.setup_driver():
            print("❌ Ошибка настройки WebDriver!")
            return
        
        print("🔐 Вход в Facebook...")
        if not poster.login():
            print("❌ Ошибка входа!")
            return
        
        print("✅ Вход выполнен успешно!")
        print()
        
        # Загрузка групп
        groups = poster.load_groups('temp_groups.txt')
        
        if not groups:
            print("❌ Группы не найдены!")
            return
        
        test_group = groups[0]
        print(f"🎯 Тестовая группа: {test_group}")
        print()
        
        print("🚀 Начинаем тест кнопки 'Отправить'...")
        print("=" * 40)
        
        # Переход к группе
        print("📱 Переход к группе...")
        poster.driver.get(test_group)
        time.sleep(3)
        
        # Попытка найти элемент создания поста
        print("🔍 Поиск элемента создания поста...")
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
        
        post_creation_selectors = [
            "//span[contains(text(), 'Напишите что-нибудь')]//ancestor::div[@role='button'][1]",
            "//div[@role='button' and contains(@aria-label, 'Напишите что-нибудь')]",
            "//div[@contenteditable='true' and @role='textbox']"
        ]
        
        post_element = None
        for i, selector in enumerate(post_creation_selectors):
            try:
                print(f"   Пробуем селектор {i+1}: {selector}")
                post_element = WebDriverWait(poster.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                print(f"   ✅ Найден элемент создания поста!")
                break
            except TimeoutException:
                print(f"   ❌ Селектор {i+1} не сработал")
                continue
        
        if not post_element:
            print("❌ Не удалось найти элемент создания поста!")
            print("🔍 Браузер остается открытым для проверки...")
            input("Нажмите Enter когда закончите проверку...")
            return
        
        # Клик по элементу создания поста
        print("👆 Клик по элементу создания поста...")
        post_element.click()
        time.sleep(2)
        
        # Поиск текстового поля
        print("📝 Поиск текстового поля для ввода...")
        text_area_selectors = [
            "//div[@role='dialog']//div[@contenteditable='true' and @role='textbox']",
            "//div[@contenteditable='true' and contains(@class, 'notranslate')]",
            "//div[@contenteditable='true']"
        ]
        
        text_area = None
        for i, selector in enumerate(text_area_selectors):
            try:
                print(f"   Пробуем селектор текстового поля {i+1}")
                text_area = WebDriverWait(poster.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, selector))
                )
                print(f"   ✅ Найдено текстовое поле!")
                break
            except TimeoutException:
                continue
        
        if not text_area:
            print("❌ Не удалось найти текстовое поле!")
            return
        
        # Ввод тестового сообщения
        print("⌨️  Ввод тестового сообщения...")
        text_area.click()
        time.sleep(1)
        text_area.send_keys(test_message)
        time.sleep(2)
        
        print("✅ Сообщение введено!")
        print()
        
        # ГЛАВНАЯ ПРОВЕРКА: поиск кнопки "Отправить"
        print("🔍 ГЛАВНАЯ ПРОВЕРКА: Поиск кнопки 'Отправить'")
        print("=" * 50)
        
        # Все возможные селекторы для кнопки "Отправить"
        send_button_selectors = [
            "//div[@role='dialog']//div[@role='button'][.//span[contains(text(), 'Отправить')]]",
            "//div[@role='button' and contains(@aria-label, 'Отправить')]", 
            "//span[contains(text(), 'Отправить')]//ancestor::div[@role='button'][1]",
            "//div[@role='dialog']//div[@role='button'][.//span[text()='Отправить']]",
            "//button[contains(text(), 'Отправить')]",
            "//div[contains(@class, 'dialog')]//div[@role='button' and contains(text(), 'Отправить')]"
        ]
        
        send_button = None
        for i, selector in enumerate(send_button_selectors):
            try:
                print(f"🔍 Пробуем селектор кнопки {i+1}: {selector}")
                send_button = WebDriverWait(poster.driver, 3).until(
                    EC.presence_of_element_located((By.XPATH, selector))
                )
                
                if send_button.is_enabled() and send_button.is_displayed():
                    print(f"✅ НАЙДЕНА кнопка 'Отправить' с селектором {i+1}!")
                    
                    # Выделяем кнопку красной рамкой
                    poster.driver.execute_script("arguments[0].style.border='5px solid red';", send_button)
                    poster.driver.execute_script("arguments[0].style.backgroundColor='yellow';", send_button)
                    
                    print("🔴 Кнопка выделена красной рамкой и желтым фоном!")
                    break
                else:
                    print(f"⚠️  Кнопка найдена но не активна с селектором {i+1}")
                    send_button = None
                    
            except TimeoutException:
                print(f"❌ Селектор {i+1} не сработал")
                continue
            except Exception as e:
                print(f"❌ Ошибка с селектором {i+1}: {str(e)}")
                continue
        
        if send_button:
            print()
            print("🎉 УСПЕХ! Кнопка 'Отправить' найдена!")
            print("=" * 40)
            
            # Получаем информацию о кнопке
            button_text = poster.driver.execute_script("return arguments[0].textContent || arguments[0].innerText;", send_button)
            button_aria = send_button.get_attribute('aria-label') or 'Нет aria-label'
            
            print(f"📝 Текст кнопки: '{button_text}'")
            print(f"🏷️  Aria-label: '{button_aria}'")
            print(f"✅ Активна: {send_button.is_enabled()}")
            print(f"👁️  Видима: {send_button.is_displayed()}")
            
            # Предлагаем пользователю клик
            print()
            choice = input("❓ Хотите кликнуть по кнопке 'Отправить'? (y/n): ").lower()
            
            if choice == 'y':
                print("👆 Кликаем по кнопке...")
                try:
                    send_button.click()
                    print("✅ Клик выполнен!")
                    
                    # Ждем результата
                    time.sleep(3)
                    
                    # Проверяем, закрылся ли диалог
                    try:
                        WebDriverWait(poster.driver, 5).until_not(
                            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
                        )
                        print("🎉 ДИАЛОГ ЗАКРЫЛСЯ! Пост отправлен успешно!")
                    except TimeoutException:
                        print("⚠️  Диалог все еще открыт, результат неопределенный")
                        
                except Exception as e:
                    print(f"❌ Ошибка при клике: {str(e)}")
            else:
                print("❌ Клик отменен пользователем")
        else:
            print()
            print("❌ КНОПКА 'ОТПРАВИТЬ' НЕ НАЙДЕНА!")
            print("=" * 40)
            
            # JavaScript поиск как резерв
            print("🔍 Попытка поиска через JavaScript...")
            js_result = poster.driver.execute_script("""
                var buttons = document.querySelectorAll('div[role="button"], button');
                var found = [];
                
                for (var i = 0; i < buttons.length; i++) {
                    var btn = buttons[i];
                    var text = btn.textContent || btn.innerText || '';
                    var ariaLabel = btn.getAttribute('aria-label') || '';
                    
                    if (text.includes('Отправить') || ariaLabel.includes('Отправить')) {
                        found.push({
                            text: text,
                            ariaLabel: ariaLabel,
                            visible: btn.offsetParent !== null,
                            enabled: !btn.disabled
                        });
                        
                        // Выделяем найденные кнопки
                        btn.style.border = '3px solid blue';
                        btn.style.backgroundColor = 'lightblue';
                    }
                }
                
                return found;
            """)
            
            if js_result:
                print(f"✅ JavaScript нашел {len(js_result)} кнопок с 'Отправить':")
                for i, btn_info in enumerate(js_result):
                    print(f"   {i+1}. Текст: '{btn_info['text']}', Aria: '{btn_info['ariaLabel']}', Видима: {btn_info['visible']}, Активна: {btn_info['enabled']}")
                print("🔵 Найденные кнопки выделены синей рамкой!")
            else:
                print("❌ JavaScript тоже не нашел кнопок с 'Отправить'")
        
        print()
        print("🔍 Браузер остается открытым для ручной проверки...")
        print("📱 Посмотрите на диалог и найдите кнопку отправки")
        print("Press Ctrl+C to exit when ready")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n👋 Завершение теста...")
    
    except Exception as e:
        print(f"❌ Ошибка теста: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("🧹 Очистка...")
        poster.cleanup()

if __name__ == "__main__":
    main() 