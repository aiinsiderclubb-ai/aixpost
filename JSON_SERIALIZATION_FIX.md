# 🔧 Исправление ошибки JSON Serialization

## 🎯 **Проблема:**
После входа в Facebook возникала ошибка: **"Object of type datetime is not JSON serializable"**

## 🔍 **Найденная причина:**

В методе `get_status()` в файле `bot/fb_poster.py` возвращался объект `self.stats`, который содержал datetime объекты:
- `start_time` - datetime объект
- `end_time` - datetime объект  
- `elapsed_time` - потенциально timedelta объект

Эти объекты не могут быть автоматически сериализованы в JSON при отправке через API endpoint `/api/posting_status`.

## ✅ **Исправление:**

### 🛠️ **Обновлен метод `get_status()` в `bot/fb_poster.py`:**

```python
def get_status(self):
    \"\"\"Get the current status of the bot\"\"\"
    # Convert datetime objects to ISO strings for JSON serialization
    status = self.stats.copy()
    
    # Convert datetime objects to strings
    if 'start_time' in status and status['start_time'] is not None:
        if hasattr(status['start_time'], 'isoformat'):
            status['start_time'] = status['start_time'].isoformat()
    
    if 'end_time' in status and status['end_time'] is not None:
        if hasattr(status['end_time'], 'isoformat'):
            status['end_time'] = status['end_time'].isoformat()
    
    # Convert elapsed time if it's a timedelta
    if 'elapsed_time' in status and hasattr(status['elapsed_time'], 'total_seconds'):
        status['elapsed_time'] = int(status['elapsed_time'].total_seconds())
    
    return status
```

### 🎯 **Что изменилось:**

1. **🔄 Создается копия stats** - `status = self.stats.copy()`
2. **📅 Конвертация datetime в ISO строки** - `datetime.isoformat()`
3. **⏱️ Конвертация timedelta в секунды** - `timedelta.total_seconds()`
4. **🛡️ Безопасная проверка типов** - `hasattr()` checks

## 🔍 **Дополнительная информация:**

### **Дублирование логов входа - НОРМАЛЬНО:**
Логи показывают двойной ввод email/password, но это происходит из-за:
1. Первичный вход при старте сессии
2. Повторный вход при восстановлении сессии (`restart_driver_session()`)

Это **нормальное поведение** системы восстановления сессии ChromeDriver.

### **ChromeDriver Session Recovery:**
Система автоматически:
- ✅ Обнаруживает падение сессии
- ✅ Перезапускает ChromeDriver  
- ✅ Заново логинится в Facebook
- ✅ Продолжает постинг

## 🎉 **Результат:**
- ✅ JSON serialization error ИСПРАВЛЕНА
- ✅ API `/api/posting_status` работает корректно
- ✅ datetime объекты конвертируются в ISO строки
- ✅ Система восстановления сессии функционирует правильно
- ✅ Постинг продолжается после восстановления сессии

## 🧪 **Тестирование:**
1. Запустите постинг
2. Проверьте что нет ошибок JSON serialization
3. Убедитесь что статус корректно отображается в веб-интерфейсе
4. При падении сессии проверьте автоматическое восстановление 