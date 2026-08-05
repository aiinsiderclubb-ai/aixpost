"""
Facebook Group Poster Bot - Main Module
Handles automated posting to Facebook groups using Selenium
"""

import os
import time
import random
import logging
import configparser
import subprocess
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException, ElementClickInterceptedException, InvalidSessionIdException, WebDriverException
import re
from selenium.webdriver.common.keys import Keys
import requests
import unicodedata


class FacebookGroupPoster:
    """Main bot class for automating Facebook group posts"""
    
    def __init__(self, config_file='config.ini', headless=False, use_profile=False, profile_dir=None, user_id: int | None = None):
        """Initialize Facebook Group Poster with enhanced session management"""
        
        # КРИТИЧЕСКИ ВАЖНО: Создаем logger В ПЕРВУЮ ОЧЕРЕДЬ
        log_format = '%(asctime)s,%(msecs)03d - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger('FacebookGroupPoster')
        self.logger.info("Initializing Facebook Group Poster")
        
        # Базовые атрибуты
        self.config_file = config_file
        self.headless = headless
        self.driver = None
        self.config = configparser.ConfigParser()
        self.username = ""
        self.password = ""
        self.telegram_token = ""
        self.telegram_chat_id = ""
        self.is_posting = False
        self.should_stop = False
        self.success_count = 0
        self.error_count = 0
        self.session_start_time = None
        self.groups = []
        self.use_profile = use_profile
        # Prefer the explicitly selected account profile; otherwise isolate by user.
        self.profile_dir = profile_dir
        if not self.profile_dir and user_id is not None:
            base_profiles = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'user_data', 'profiles')
            self.profile_dir = os.path.abspath(os.path.join(base_profiles, f"profile_user_{user_id}"))
        # User attribution for per-user analytics
        self.user_id = user_id
        
        # Enhanced session management
        self.login_attempts = 0
        self.max_login_attempts = 3
        self.login_in_progress = False  # ЗАЩИТА ОТ ПОВТОРНОГО ВЫЗОВА
        self.last_login_attempt = None
        self.session_restarts = 0
        self.max_session_restarts = 3
        self.last_activity_time = datetime.now()
        
        # Initialize state tracking
        self._is_logged_in = False
        self.stop_posting_flag = False
        self.stop_posting = False  # Compatibility alias
        self.error = None
        self.waiting_for_2fa = False
        self.manual_verification_needed = False
        self.posts_completed = 0
        self.posts_failed = 0
        self.groups_total = 0
        
        # Initialize attributes for template system
        self.template_manager = None
        self.template_mode = 'random'
        self.use_templates = False
        self.current_message = ""
        self.group_statuses = {}
        self.max_groups = 50  # Default limit
        self.batch_size = 10  # Default batch size for notifications
        self.pause_posting_flag = False
        self.runtime_event_callback = None
        self.group_status_callback = None
        self.status_change_callback = None
        self.session_state_callback = None
        self.recent_events = []
        
        # Account safety controls
        self.account_id = None
        self.hourly_limit = 0
        self.daily_limit = 0
        self.rate_limiter = None
        self.health_monitor = None
        self.skip_success_urls = set()
        
        # Initialize stats tracking
        self.stats = {
            'status': 'Idle',
            'posts_completed': 0,
            'posts_failed': 0,
            'groups_total': 0,
            'start_time': None,
            'elapsed_time': '00:00:00',
            'current_group': None,
            'error': None,
            'session_restarts': 0
        }
        
        # Initialize Telegram configuration defaults BEFORE loading config
        self.telegram_notifications_enabled = False
        self.telegram_errors_only = False
        self.telegram_token = ""
        self.telegram_chat_id = ""
        
        # Load config ПІСЛЯ создания logger
        self.load_config()
        
        # Initialize analytics
        try:
            from .analytics_db import analytics_db
            self.analytics_db = analytics_db
            self.analytics_enabled = True
            self.logger.info("✅ Analytics database initialized")
        except ImportError as e:
            self.logger.warning(f"Analytics not available: {e}")
            self.analytics_db = None
            self.analytics_enabled = False
        
        self.take_screenshot("init_completed")
    
    def load_config(self):
        """Load configuration from config file"""
        try:
            if os.path.exists(self.config_file):
                self.config.read(self.config_file)
                
                # Credentials
                self.username = self.config.get('Credentials', 'username', fallback='')
                self.password = self.config.get('Credentials', 'password', fallback='')
                
                # Settings
                self.max_groups = self.config.getint('Settings', 'max_groups_per_session', fallback=200)
                self.min_delay = self.config.getint('Settings', 'min_delay_seconds', fallback=10)
                self.max_delay = self.config.getint('Settings', 'max_delay_seconds', fallback=60)
                self.batch_size = self.config.getint('Settings', 'batch_size', fallback=10)
                
                # Profile settings override
                if not self.use_profile and self.config.has_option('Settings', 'use_profile'):
                    self.use_profile = self.config.getboolean('Settings', 'use_profile', fallback=False)
                if not self.profile_dir and self.config.has_option('Settings', 'profile_dir'):
                    self.profile_dir = self.config.get('Settings', 'profile_dir', fallback=None)
                
                # Telegram configuration
                self.telegram_token = self.config.get('Telegram', 'telegram_bot_token', fallback='')
                self.telegram_chat_id = self.config.get('Telegram', 'telegram_chat_id', fallback='')
                self.telegram_notifications_enabled = self.config.getboolean('Telegram', 'notifications_enabled', fallback=False)
                self.telegram_errors_only = self.config.getboolean('Telegram', 'errors_only', fallback=False)
                
                self.logger.info("Configuration loaded successfully")
            else:
                self.logger.error(f"Config file {self.config_file} not found - using defaults")
                # Set defaults
                self.username = ''
                self.password = ''
                self.max_groups = 200
                self.min_delay = 10
                self.max_delay = 60
                self.batch_size = 10
                self.telegram_token = ''
                self.telegram_chat_id = ''
                self.telegram_notifications_enabled = False
                self.telegram_errors_only = False

            try:
                from app.core.config import AppConfig
                AppConfig.overlay_bot_secrets_from_env(self)
            except Exception:
                if os.environ.get('FB_USERNAME'):
                    self.username = os.environ['FB_USERNAME']
                if os.environ.get('FB_PASSWORD'):
                    self.password = os.environ['FB_PASSWORD']
                if os.environ.get('TELEGRAM_BOT_TOKEN'):
                    self.telegram_token = os.environ['TELEGRAM_BOT_TOKEN']
                if os.environ.get('TELEGRAM_CHAT_ID'):
                    self.telegram_chat_id = os.environ['TELEGRAM_CHAT_ID']
                
        except Exception as e:
            self.logger.error(f"Error loading config: {str(e)}")
            # Set safe defaults
            self.username = ''
            self.password = ''
            self.max_groups = 200
            self.min_delay = 10
            self.max_delay = 60
            self.batch_size = 10
    
    def check_driver_session(self):
        """
        Проверка активности сессии ChromeDriver
        
        Returns:
            bool: True если сессия активна, False если нужен перезапуск
        """
        if not self.driver:
            self.log_action("Driver is None - session is dead", 'warning')
            return False
        
        try:
            # Пытаемся получить текущий URL - это простая операция для проверки сессии
            current_url = self.driver.current_url
            # Если дошли до этой строки, сессия активна
            return True
        except InvalidSessionIdException:
            self.log_action("Invalid session ID detected - driver session is dead", 'warning')
            return False
        except WebDriverException as e:
            error_str = str(e).lower()
            if "invalid session id" in error_str or "session deleted" in error_str or "no such window" in error_str:
                self.log_action(f"WebDriver session error detected: {str(e)}", 'warning')
                return False
            else:
                # Другие ошибки WebDriver не означают проблемы с сессией
                return True
        except Exception as e:
            self.log_action(f"Unexpected error checking driver session: {str(e)}", 'warning')
            # При неизвестной ошибке считаем сессию живой
            return True
    
    def restart_driver_session(self):
        """
        Перезапуск ChromeDriver сессии
        
        Returns:
            bool: True если перезапуск успешен, False если нет
        """
        self.log_action("⚠️ Перезапускаем ChromeDriver сессию...", 'warning')
        
        # Отправляем уведомление в Telegram
        restart_message = (
            f"⚠️ <b>Ошибка ChromeDriver:</b>\n"
            f"🔄 <b>Сессия была перезапущена</b>\n"
            f"📊 <b>Попытка:</b> {self.session_restarts + 1}/{self.max_session_restarts}"
        )
        self.send_telegram_notification(restart_message, error_level=True)
        
        # Закрываем старый драйвер если он есть
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass  # Игнорируем ошибки при закрытии мертвой сессии
            finally:
                self.driver = None
                self._is_logged_in = False
        
        # Увеличиваем счетчик перезапусков
        self.session_restarts += 1
        
        if self.session_restarts > self.max_session_restarts:
            self.log_action(f"❌ Превышено максимальное количество перезапусков сессии ({self.max_session_restarts})", 'error')
            
            final_error_message = (
                f"❌ <b>Критическая ошибка:</b>\n"
                f"🚫 <b>ChromeDriver сессия упала {self.max_session_restarts} раз подряд</b>\n"
                f"⏹️ <b>Постинг остановлен</b>"
            )
            self.send_telegram_notification(final_error_message, error_level=True)
            return False
        
        # Пытаемся перезапустить драйвер
        try:
            if self.use_profile:
                success = self.setup_driver_with_profile(self.profile_dir)
            else:
                success = self.setup_driver()
            
            if not success:
                self.log_action("❌ Не удалось перезапустить драйвер", 'error')
                return False
            
            # Пытаемся войти в систему заново
            if not self._is_logged_in:
                if not self.login():
                    self.log_action("❌ Не удалось войти в систему после перезапуска драйвера", 'error')
                    return False
            
            self.log_action("✅ ChromeDriver сессия успешно перезапущена", 'info')
            
            # Отправляем уведомление об успешном восстановлении
            recovery_message = (
                f"✅ <b>Сессия восстановлена!</b>\n"
                f"🔄 <b>ChromeDriver перезапущен успешно</b>\n"
                f"▶️ <b>Продолжаем постинг...</b>"
            )
            self.send_telegram_notification(recovery_message, error_level=False)
            
            return True
            
        except Exception as e:
            self.log_action(f"❌ Ошибка при перезапуске драйвера: {str(e)}", 'error')
            return False
    
    def safe_driver_operation(self, operation_func, *args, **kwargs):
        """
        Безопасное выполнение операций с драйвером с автоматическим восстановлением сессии
        
        Args:
            operation_func: Функция для выполнения
            *args, **kwargs: Аргументы для функции
            
        Returns:
            Результат выполнения функции или None в случае ошибки
        """
        max_attempts = 2
        
        for attempt in range(max_attempts):
            try:
                # Проверяем сессию перед операцией
                if not self.check_driver_session():
                    if not self.restart_driver_session():
                        return None
                
                # Выполняем операцию
                return operation_func(*args, **kwargs)
                
            except InvalidSessionIdException as e:
                self.log_action(f"🔄 Обнаружена ошибка сессии на попытке {attempt + 1}: {str(e)}", 'warning')
                
                if attempt < max_attempts - 1:
                    # Пытаемся восстановить сессию
                    if not self.restart_driver_session():
                        return None
                    continue
                else:
                    self.log_action(f"❌ Не удалось восстановить сессию после {max_attempts} попыток", 'error')
                    return None
            except WebDriverException as e:
                error_str = str(e).lower()
                if "invalid session id" in error_str or "session deleted" in error_str or "no such window" in error_str:
                    self.log_action(f"🔄 Обнаружена ошибка сессии на попытке {attempt + 1}: {str(e)}", 'warning')
                    
                    if attempt < max_attempts - 1:
                        # Пытаемся восстановить сессию
                        if not self.restart_driver_session():
                            return None
                        continue
                    else:
                        self.log_action(f"❌ Не удалось восстановить сессию после {max_attempts} попыток", 'error')
                        return None
                else:
                    # Другие ошибки WebDriver пробрасываем наверх
                    raise e
            except Exception as e:
                # Другие исключения пробрасываем наверх
                raise e
        
        return None
    
    @property
    def is_logged_in(self):
        """Enhanced login status check with Facebook element detection"""
        # If we have no driver, we're definitely not logged in
        if not self.driver:
            self._is_logged_in = False
            return False

        # Always attempt to detect login state (don't rely only on cached flag)
        try:
            current_url = (self.driver.current_url or "").lower()
            if any(marker in current_url for marker in ("/checkpoint", "/captcha", "/two_factor", "/approvals_code")):
                self._mark_verification_required(
                    "checkpoint" if "/checkpoint" in current_url else "captcha",
                    f"Facebook requires verification at {current_url}",
                )
                return False
            # Cookie-based detection: if c_user cookie exists, user is authenticated
            try:
                cookies = self.driver.get_cookies()
                if any(c.get('name') == 'c_user' and c.get('value') for c in cookies):
                    self._is_logged_in = True
                    return True
            except Exception:
                pass

            # Quick check for navigation bar (main indicator)
            navigation_elements = self.driver.find_elements(By.XPATH, "//div[@role='banner']")
            if navigation_elements and any(el.is_displayed() for el in navigation_elements):
                self._is_logged_in = True
                return True

            # Additional checks for login state
            login_indicators = [
                (By.CSS_SELECTOR, "div[role='navigation']"),
                (By.XPATH, "//div[@aria-label='Account' or contains(@aria-label, 'account')]"),
                (By.XPATH, "//input[@type='search' or contains(@placeholder, 'Search') or contains(@placeholder, 'Поиск') or contains(@placeholder, 'Szukaj') or contains(@placeholder, 'Suche') or contains(@placeholder, 'Пошук')]"),
                (By.XPATH, "//div[contains(@aria-label, 'Home') or contains(@aria-label, 'home')]")
            ]

            for selector_type, selector in login_indicators:
                try:
                    elements = self.driver.find_elements(selector_type, selector)
                    if elements and any(el.is_displayed() for el in elements):
                        self._is_logged_in = True
                        return True
                except Exception:
                    continue

            # Check URL patterns
            if ("facebook.com/home" in current_url or
                ("facebook.com/?" in current_url and "login" not in current_url) or
                "facebook.com/groups" in current_url):
                self._is_logged_in = True
                return True

        except Exception as e:
            self.log_action(f"⚠️ Error checking login status: {str(e)}", 'warning')

        self._is_logged_in = False
        return False

    def _mark_verification_required(self, status, reason):
        """Record a checkpoint/CAPTCHA/2FA state without treating it as a login."""
        self._is_logged_in = False
        self.manual_verification_needed = True
        self.waiting_for_2fa = status == "need_2fa"
        self.error = reason
        self._set_runtime_status("Waiting for 2FA" if status == "need_2fa" else "Waiting for manual verification", reason)
        self._emit_session_state(status, reason)
    
    def log_action(self, message, level='info'):
        """Log actions with appropriate level"""
        if level == 'info':
            self.logger.info(message)
        elif level == 'error':
            self.logger.error(message)
        elif level == 'warning':
            self.logger.warning(message)
        event = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message,
        }
        self.recent_events.append(event)
        self.recent_events = self.recent_events[-200:]
        if callable(self.runtime_event_callback):
            try:
                self.runtime_event_callback(message=message, level=level, event_type='log', metadata=event)
            except Exception:
                pass

    def _set_runtime_status(self, status, error=None):
        self.stats['status'] = status
        if error is not None:
            self.stats['error'] = error
        if callable(self.status_change_callback):
            try:
                self.status_change_callback(status=status, error=error, snapshot=self.get_status())
            except Exception:
                pass

    def _emit_session_state(self, status, reason=None):
        if callable(self.session_state_callback):
            try:
                self.session_state_callback(status=status, reason=reason, snapshot=self.get_status())
            except Exception:
                pass

    def _sync_group_state(self, group_id, payload):
        self.group_statuses[group_id] = payload
        if callable(self.group_status_callback):
            try:
                self.group_status_callback(group_id=group_id, payload=payload)
            except Exception:
                pass

    def _wait_if_paused(self):
        if callable(getattr(self, 'task_control_callback', None)):
            self.task_control_callback()
        while self.pause_posting_flag and not self.stop_posting_flag:
            if callable(getattr(self, 'task_control_callback', None)):
                self.task_control_callback()
            self._set_runtime_status('Paused')
            time.sleep(1)
        if not self.stop_posting_flag and self.is_posting:
            self._set_runtime_status('Running')

    def pause_posting_method(self):
        self.pause_posting_flag = True
        self.log_action("Pausing posting session", 'warning')
        self._set_runtime_status('Paused')
        return True

    def resume_posting_method(self):
        self.pause_posting_flag = False
        self.log_action("Resuming posting session")
        self._set_runtime_status('Running')
        return True
    
    def send_telegram_notification(self, message, error_level=False):
        """
        Отправка уведомления в Telegram через Bot API
        
        Args:
            message (str): Текст сообщения для отправки
            error_level (bool): True если это уведомление об ошибке
        """
        # Проверяем, включены ли уведомления
        if not self.telegram_notifications_enabled:
            return
        
        # Проверяем, настроены ли токен и chat_id
        if not self.telegram_token or not self.telegram_chat_id:
            self.logger.warning("Telegram notifications enabled but bot_token or chat_id not configured")
            return
            
        # Проверяем, что токен и chat_id не являются заглушками
        if (self.telegram_token == 'YOUR_BOT_TOKEN_HERE' or 
            self.telegram_chat_id == 'YOUR_CHAT_ID_HERE'):
            self.logger.warning("Telegram bot_token or chat_id are placeholder values - please update config.ini")
            return
        
        # Если включен режим "только ошибки", отправляем только ошибки
        if self.telegram_errors_only and not error_level:
            return
        
        try:
            # URL для Telegram Bot API
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            
            # Очищаем chat_id от возможных пробелов и обеспечиваем правильный тип
            chat_id_clean = str(self.telegram_chat_id).strip()
            
            # Подготовка данных для отправки (используем data вместо json)
            payload = {
                'chat_id': chat_id_clean,
                'text': message,
                'parse_mode': 'HTML',  # Поддержка HTML разметки
                'disable_web_page_preview': 'true'
            }
            
            # Отправка запроса с правильным Content-Type
            response = requests.post(url, data=payload, timeout=10)
            
            if response.status_code == 200:
                self.logger.info("Telegram notification sent successfully")
            else:
                self.logger.warning(f"Failed to send Telegram notification: {response.status_code} - {response.text}")
                
        except requests.RequestException as e:
            self.logger.error(f"Error sending Telegram notification: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error in Telegram notification: {str(e)}")
    
    def send_error_notification(self, group_name, error_message):
        """
        Отправка уведомления об ошибке при постинге
        
        Args:
            group_name (str): Название/URL группы
            error_message (str): Описание ошибки
        """
        # Извлекаем читаемое имя группы из URL
        group_display_name = self.extract_group_name(group_name)
        
        # НЕ отправляем индивидуальные уведомления об ошибках
        # Они будут включены в батч-сводку
        # message = (
        #     f"⚠️ <b>Ошибка при постинге:</b>\n"
        #     f"🔗 <b>Группа:</b> {group_display_name}\n"
        #     f"❌ <b>Причина:</b> {error_message}"
        # )
        # self.send_telegram_notification(message, error_level=True)
        
        self.error_count += 1
    
    def send_success_notification(self, group_name):
        """
        Отправка уведомления об успешном постинге (опционально)
        
        Args:
            group_name (str): Название/URL группы
        """
        # НЕ отправляем индивидуальные уведомления об успехах
        # Они будут включены в батч-сводку  
        # if self.telegram_errors_only:
        #     return
        #     
        # group_display_name = self.extract_group_name(group_name)
        # 
        # message = (
        #     f"✅ <b>Пост успешно отправлен!</b>\n"
        #     f"🔗 <b>Группа:</b> {group_display_name}\n"
        #     f"📊 <b>Прогресс:</b> {self.success_count + 1}/{self.groups_total}"
        # )
        # 
        # self.send_telegram_notification(message, error_level=False)
        pass
    
    def send_session_complete_notification(self, use_templates=False):
        """
        Отправка итогового уведомления по завершению сессии постинга с поддержкой шаблонов
        """
        if not self.session_start_time:
            return
            
        # Вычисляем время выполнения
        elapsed_time = datetime.now() - self.session_start_time
        total_minutes = int(elapsed_time.total_seconds() // 60)
        
        # Формируем статистику
        total_processed = self.success_count + self.error_count
        
        # Определяем эмодзи в зависимости от результата
        if self.error_count == 0:
            status_emoji = "🎉"
            status_text = "Все посты отправлены успешно!"
        elif self.success_count > self.error_count:
            status_emoji = "✅"
            status_text = "Постинг завершён (есть ошибки)"
        else:
            status_emoji = "⚠️"
            status_text = "Постинг завершён (много ошибок)"
        
        # Добавляем информацию о перезапусках сессии
        restart_info = ""
        if hasattr(self, 'session_restarts') and self.session_restarts > 0:
            restart_info = f"\n🔄 Перезапусков сессии: <b>{self.session_restarts}</b>"
        
        # Добавляем информацию о шаблонах
        template_info = ""
        if use_templates and hasattr(self, 'template_manager') and self.template_manager:
            template_count = len(self.template_manager.templates)
            template_mode = getattr(self, 'template_mode', 'random')
            template_info = f"\n🧠 <b>Шаблоны:</b> {template_count} шаблонов ({template_mode} режим)"
            
            # Добавляем статистику о последнем использованном шаблоне
            if hasattr(self.template_manager, 'current_template_index') and self.template_manager.current_template_index is not None:
                last_template = self.template_manager.templates[self.template_manager.current_template_index]
                template_info += f"\n📄 Последний: <code>{last_template[:40]}{'...' if len(last_template) > 40 else ''}</code>"
        
        message = (
            f"{status_emoji} <b>{status_text}</b>\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"✅ Успешно: <b>{self.success_count}</b>\n"
            f"❌ Ошибок: <b>{self.error_count}</b>\n"
            f"📝 Всего обработано: <b>{total_processed}</b>\n"
            f"⏱ Время выполнения: <b>{total_minutes} мин</b>{restart_info}{template_info}"
        )
        
        self.send_telegram_notification(message, error_level=False)
    
    def extract_group_name(self, group_url):
        """
        Извлекает читаемое имя группы из URL
        
        Args:
            group_url (str): URL группы Facebook
            
        Returns:
            str: Читаемое имя группы
        """
        if not group_url:
            return "Неизвестная группа"
        
        try:
            # Извлекаем ID группы из URL
            if '/groups/' in group_url:
                parts = group_url.split('/groups/')
                if len(parts) > 1:
                    group_id = parts[1].rstrip('/')
                    # Убираем возможные параметры URL
                    if '?' in group_id:
                        group_id = group_id.split('?')[0]
                    return f"ID: {group_id}"
            
            # Если не удалось извлечь ID, возвращаем укороченный URL
            if len(group_url) > 50:
                return group_url[:47] + "..."
            return group_url
            
        except Exception:
            return "Неизвестная группа"
        
    def setup_driver(self):
        """Set up and configure the Chrome WebDriver"""
        self.log_action("Setting up Chrome WebDriver")
        
        try:
            chrome_options = Options()
            
            if self.headless:
                chrome_options.add_argument("--headless")
                
            # Basic options
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--disable-infobars")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Additional anti-detection measures
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            # Add a user agent to appear more like a real browser
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36")
            
            # Add language and platform to appear more natural
            chrome_options.add_argument("--lang=en-US")
            chrome_options.add_argument("--start-maximized")
            
            # Initialize the Chrome driver
            self.driver = webdriver.Chrome(options=chrome_options)
            
            if not self.driver:
                self.log_action("Failed to initialize WebDriver - driver is None", 'error')
                self.stats['status'] = 'Error'
                return False
                
            # Execute CDP commands to prevent detection
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    
                    // Overwrite the 'plugins' property to use a custom getter
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    
                    // Overwrite the 'languages' property to use a custom getter
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en', 'es']
                    });
                    
                    window.chrome = {
                        runtime: {}
                    };
                """
            })
            
            # Always start with a proper Facebook URL to avoid 'data:' URL issues
            try:
                self.log_action("Navigating to Facebook login page")
                self.driver.get("https://www.facebook.com/login")
                
                # Wait for page to load
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Verify we're on Facebook and not a data: URL
                current_url = self.driver.current_url
                if not current_url.startswith("https://www.facebook.com") and not current_url.startswith("https://facebook.com"):
                    self.log_action(f"URL verification failed. Current URL: {current_url}", 'error')
                    self.take_screenshot("invalid_url")
                    return False
                    
                self.log_action(f"Successfully loaded Facebook login page: {current_url}")
            except Exception as e:
                self.log_action(f"Failed to navigate to Facebook login page: {str(e)}", 'error')
                self.take_screenshot("login_page_error")
                return False
            
            self.driver.maximize_window()
            if not self.headless:
                self._focus_browser_window()
            self.log_action("Chrome WebDriver initialized successfully")
            return True
            
        except Exception as e:
            self.log_action(f"Failed to initialize Chrome WebDriver: {str(e)}", 'error')
            self.stats['status'] = 'Error'
            
            # Safety cleanup in case driver was partially initialized
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
                
            return False

    def _focus_browser_window(self):
        """Bring the Chrome window to the foreground in visible mode."""
        if self.headless:
            return
        try:
            if os.name == 'posix':
                subprocess.run(
                    ["osascript", "-e", 'tell application "Google Chrome" to activate'],
                    check=False,
                    capture_output=True,
                    text=True
                )
            self.log_action("🪟 Chrome window brought to front")
        except Exception as e:
            self.log_action(f"⚠️ Could not focus Chrome window: {str(e)}", 'warning')
            
    def setup_driver_with_profile(self, profile_dir=None):
        """Set up Chrome WebDriver with a user profile for session reuse"""
        self.log_action("Setting up Chrome WebDriver with user profile")
        
        # If no profile directory is specified, create a default one
        if not profile_dir:
            # Prevent using global shared profile when profiles are required
            raise Exception("Profile directory not set. Use per-user profile: profile_user_<user_id>.")
            
        # Create the profile directory if it doesn't exist
        if not os.path.exists(profile_dir):
            try:
                os.makedirs(profile_dir)
                self.log_action(f"Created new Chrome profile directory: {profile_dir}")
            except Exception as e:
                self.log_action(f"Failed to create profile directory: {str(e)}", 'error')
                # Do not allow fallback to shared profile
                raise
                
        try:
            chrome_options = Options()
            
            # Set user data directory
            chrome_options.add_argument(f"--user-data-dir={profile_dir}")
            
            if self.headless:
                chrome_options.add_argument("--headless")
                
            # Basic options
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--disable-infobars")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            
            # Additional anti-detection measures
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            # Add a user agent to appear more like a real browser
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36")
            
            # Add language and platform to appear more natural
            chrome_options.add_argument("--lang=en-US")
            chrome_options.add_argument("--start-maximized")
            
            # Initialize the Chrome driver
            self.driver = webdriver.Chrome(options=chrome_options)
            
            if not self.driver:
                self.log_action("Failed to initialize WebDriver with profile - driver is None", 'error')
                self.stats['status'] = 'Error'
                return False
                
            # Execute CDP commands to prevent detection
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    
                    // Overwrite the 'plugins' property to use a custom getter
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    
                    // Overwrite the 'languages' property to use a custom getter
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en', 'es']
                    });
                    
                    window.chrome = {
                        runtime: {}
                    };
                """
            })
            
            # Navigate to Facebook login page
            try:
                self.log_action("Navigating to Facebook with saved profile")
                self.driver.get("https://www.facebook.com")
                
                # Wait for page to load
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Check if we're already logged in with the saved profile
                current_url = self.driver.current_url
                if "facebook.com/home" in current_url or "/profile.php" in current_url:
                    self.log_action("Already logged in with saved profile")
                    self._is_logged_in = True
                
                self.log_action(f"Successfully loaded Facebook with profile: {current_url}")
                if not self.headless:
                    self._focus_browser_window()
            except Exception as e:
                self.log_action(f"Failed to navigate with profile: {str(e)}", 'error')
                self.take_screenshot("profile_navigation_error")
                return False
                
            self.driver.maximize_window()
            self.log_action("Chrome WebDriver with profile initialized successfully")
            return True
            
        except Exception as e:
            self.log_action(f"Failed to initialize Chrome WebDriver with profile: {str(e)}", 'error')
            self.stats['status'] = 'Error'
            
            # Safety cleanup in case driver was partially initialized
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
                
            # Fall back to regular setup
            self.log_action("Falling back to regular WebDriver setup")
            return self.setup_driver()
    
    def login(self):
        """Enhanced bulletproof Facebook login with anti-duplication protection"""
        
        # КРИТИЧЕСКАЯ ЗАЩИТА ОТ ПОВТОРНОГО ВЫЗОВА
        if self.login_in_progress:
            self.log_action("⚠️ Login already in progress, skipping duplicate call", 'warning')
            return False
            
        # Проверяем не слишком ли часто пытаемся входить
        if self.last_login_attempt:
            time_since_last = (datetime.now() - self.last_login_attempt).total_seconds()
            if time_since_last < 30:  # Минимум 30 секунд между попытками
                self.log_action(f"⚠️ Too frequent login attempts, waiting {30 - int(time_since_last)}s", 'warning')
                return False
        
        # Проверяем лимит попыток входа
        if self.login_attempts >= self.max_login_attempts:
            self.log_action(f"❌ Maximum login attempts ({self.max_login_attempts}) exceeded", 'error')
            return False
        
        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Проверяем состояние браузера в начале логина
        if not self.check_driver_session():
            self.log_action("❌ Browser session is dead at login start, attempting to restart", 'warning')
            if not self.restart_driver_session():
                self.log_action("❌ Failed to restart browser session for login", 'error')
                return False
        
        # УСТАНАВЛИВАЕМ ФЛАГ ЗАЩИТЫ
        self.login_in_progress = True
        self.login_attempts += 1
        self.last_login_attempt = datetime.now()
        
        try:
            self.log_action(f"🔐 Starting bulletproof login (attempt {self.login_attempts}/{self.max_login_attempts})")
            
            # Проверяем не залогинены ли уже
            if self.is_logged_in:
                self.log_action("✅ Already logged in, skipping login process")
                self.login_in_progress = False
                return True
            
            # Run several login passes before giving up.
            success = False
            for flow_attempt in range(1, 4):
                self.log_action(f"🔁 Login flow pass {flow_attempt}/3")
                self._handle_cookie_dialogs()
                success = self._perform_bulletproof_login()
                if success:
                    break
                try:
                    self.driver.get("https://www.facebook.com/login")
                    time.sleep(2)
                except Exception:
                    pass
            
            if success:
                self.log_action("🎉 Bulletproof login completed successfully!")
                self.login_attempts = 0  # Сбрасываем счетчик при успехе
            else:
                self.log_action(f"❌ Login failed (attempt {self.login_attempts})")
            
            return success
            
        except Exception as e:
            self.log_action(f"❌ Critical error in login: {str(e)}", 'error')
            return False
        finally:
            # ОБЯЗАТЕЛЬНО СНИМАЕМ ФЛАГ ЗАЩИТЫ
            self.login_in_progress = False
    
    def _handle_cookie_dialogs(self):
        """Handle cookie consent dialogs"""
        try:
            self.log_action("🍪 Checking for cookie consent dialogs")
            cookie_selectors = [
                "//button[contains(string(), 'Allow') or contains(string(), 'Accept')]",
                "//button[contains(@data-testid, 'cookie-policy')]",
                "//button[contains(text(), 'Accept All')]",
                "//button[contains(text(), 'Allow')]",
                "//button[contains(text(), 'Accept essential and optional cookies')]",
                "//button[contains(text(), 'Allow all cookies')]",
                "//button[contains(text(), 'Only allow essential cookies')]",
                "//span[contains(text(), 'Accept all')]/ancestor::div[@role='button'][1]",
                "//span[contains(text(), 'Allow all cookies')]/ancestor::div[@role='button'][1]",
                "//span[contains(text(), 'Разрешить все cookie')]/ancestor::div[@role='button'][1]",
                "//span[contains(text(), 'Принять все')]/ancestor::div[@role='button'][1]",
                "//span[contains(text(), 'Akzeptieren')]/ancestor::div[@role='button'][1]",
                "//span[contains(text(), 'Alle akzeptieren')]/ancestor::div[@role='button'][1]"
            ]
            
            for selector in cookie_selectors:
                try:
                    cookie_button = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    try:
                        cookie_button.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", cookie_button)
                    self.log_action(f"✅ Accepted cookies using: {selector}")
                    time.sleep(1)
                    return
                except:
                    continue
                    
            self.log_action("ℹ️ No cookie prompt found", 'info')
        except Exception as e:
            self.log_action(f"⚠️ Error handling cookies: {str(e)}", 'warning')
    
    def _perform_bulletproof_login(self):
        """Bulletproof login that prevents field duplication"""
        try:
            # STEP 1: Find and prepare email field
            email_field = self._find_and_prepare_email_field()
            if not email_field:
                return False
            
            # STEP 2: Find and prepare password field  
            password_field = self._find_and_prepare_password_field()
            if not password_field:
                return False
            
            # STEP 3: Find and click login button
            return self._find_and_click_login_button()
            
        except Exception as e:
            self.log_action(f"❌ Error in bulletproof login: {str(e)}", 'error')
            return False
    
    def _find_and_prepare_email_field(self):
        """Find email field and safely enter email"""
        try:
            self.log_action("📧 Looking for email field")
            
            # Попробуем разные страницы Facebook для поиска формы логина
            login_urls = [
                "https://www.facebook.com/login",
                "https://www.facebook.com/login/",
                "https://www.facebook.com",
                "https://facebook.com/login",
                "https://m.facebook.com/login"
            ]
            
            email_field = None
            current_url_index = 0
            
            while not email_field and current_url_index < len(login_urls):
                url = login_urls[current_url_index]
                self.log_action(f"🌐 Trying login URL: {url}")
                
                try:
                    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Используем safe_driver_operation для навигации
                    def navigate_to_login_url():
                        self.driver.get(url)
                        time.sleep(3)  # Дать время на загрузку
                        return True
                    
                    navigation_result = self.safe_driver_operation(navigate_to_login_url)
                    
                    if navigation_result is None:
                        self.log_action(f"❌ Failed to navigate to {url} - session recovery failed")
                        current_url_index += 1
                        continue
                    
                    # Find email field with multiple selectors
                    email_selectors = [
                        (By.ID, "email"),
                        (By.NAME, "email"),
                        (By.XPATH, "//input[@placeholder='Email or phone number']"),
                        (By.XPATH, "//input[@type='email']"),
                        (By.XPATH, "//input[contains(@placeholder, 'Email')]"),
                        # Дополнительные селекторы для новых версий Facebook
                        (By.XPATH, "//input[@name='email']"),
                        (By.XPATH, "//input[@autocomplete='username']"),
                        (By.XPATH, "//input[@autocomplete='email']"),
                        (By.XPATH, "//input[contains(@placeholder, 'phone')]"),
                        (By.XPATH, "//input[contains(@placeholder, 'Phone')]"),
                        (By.XPATH, "//input[contains(@aria-label, 'Email')]"),
                        (By.XPATH, "//input[contains(@aria-label, 'Phone')]"),
                        (By.XPATH, "//input[@data-testid='royal_email']"),
                        (By.CSS_SELECTOR, "input[name='email']"),
                        (By.CSS_SELECTOR, "input[type='email']"),
                        (By.CSS_SELECTOR, "input[autocomplete='username']"),
                        # Мобильные версии
                        (By.NAME, "m_login_email"),
                        (By.ID, "m_login_email"),
                        # Альтернативные локаторы
                        (By.XPATH, "//input[contains(@class, 'inputtext') and @type='text']"),
                        (By.XPATH, "//form//input[@type='text'][1]")  # Первое текстовое поле в форме
                    ]
                    
                    # Также используем safe_driver_operation для поиска email поля
                    def find_email_field_safe():
                        for selector_type, selector in email_selectors:
                            try:
                                field = WebDriverWait(self.driver, 5).until(
                                    EC.element_to_be_clickable((selector_type, selector))
                                )
                                self.log_action(f"✅ Found email field on {url} using: {selector}")
                                return field
                            except:
                                continue
                        return None
                    
                    email_field = self.safe_driver_operation(find_email_field_safe)
                    
                    if email_field:
                        break
                        
                except Exception as e:
                    self.log_action(f"❌ Unexpected error with {url}: {str(e)}")
                    
                current_url_index += 1
            
            if not email_field:
                self.log_action("❌ Could not find email field on any Facebook login page", 'error')
                self.take_screenshot("no_email_field")
                return None
            
            # BULLETPROOF INPUT PROCESS
            try:
                # Step 1: Check current value
                current_value = email_field.get_attribute('value') or ''
                
                # Step 2: ADVANCED ELEMENT INTERACTION - FIXES CLICK INTERCEPTION!
                self.log_action("🎯 Preparing email field for interaction")
                
                # Remove any overlapping elements that might block interaction
                try:
                    self.driver.execute_script("""
                        // Find all elements that might overlap with the email field
                        var emailField = arguments[0];
                        var rect = emailField.getBoundingClientRect();
                        var overlapping = document.elementsFromPoint(rect.left + rect.width/2, rect.top + rect.height/2);
                        
                        // Remove or hide overlapping elements that are not the input field itself
                        overlapping.forEach(function(el) {
                            if (el !== emailField && el.tagName !== 'INPUT') {
                                if (el.style) {
                                    el.style.pointerEvents = 'none';
                                    el.style.zIndex = '-1';
                                }
                            }
                        });
                    """, email_field)
                    self.log_action("✅ Cleared overlapping elements")
                except:
                    self.log_action("⚠️ Could not clear overlapping elements, proceeding")
                
                # Enhanced scroll to view - make sure element is fully visible
                self.driver.execute_script("""
                    arguments[0].scrollIntoView({
                        behavior: 'smooth',
                        block: 'center',
                        inline: 'center'
                    });
                """, email_field)
                time.sleep(0.5)
                
                # Try multiple click methods in order of preference
                click_successful = False
                
                # Method 1: JavaScript click (most reliable for intercepted elements)
                try:
                    self.driver.execute_script("arguments[0].click();", email_field)
                    self.log_action("✅ JavaScript click successful")
                    click_successful = True
                except Exception as js_click_error:
                    self.log_action(f"⚠️ JavaScript click failed: {str(js_click_error)}")
                
                # Method 2: Focus using JavaScript (if click failed)
                if not click_successful:
                    try:
                        self.driver.execute_script("arguments[0].focus();", email_field)
                        self.log_action("✅ JavaScript focus successful")
                        click_successful = True
                    except Exception as js_focus_error:
                        self.log_action(f"⚠️ JavaScript focus failed: {str(js_focus_error)}")
                
                # Method 3: Actions chain click (last resort)
                if not click_successful:
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(self.driver)
                        actions.move_to_element(email_field).click().perform()
                        self.log_action("✅ ActionChains click successful")
                        click_successful = True
                    except Exception as action_click_error:
                        self.log_action(f"⚠️ ActionChains click failed: {str(action_click_error)}")
                
                # Method 4: Send keys to focus (ultimate fallback)
                if not click_successful:
                    try:
                        email_field.send_keys("")  # Empty string to focus
                        self.log_action("✅ Focus via send_keys successful")
                        click_successful = True
                    except Exception as keys_focus_error:
                        self.log_action(f"❌ All focus methods failed: {str(keys_focus_error)}")
                        return None
                
                time.sleep(0.3)  # Give time for focus to take effect
                
                # Enhanced clearing process with multiple methods
                self.log_action("🧹 Starting enhanced field clearing")
                
                # Method 1: JavaScript force clear (most reliable)
                self.driver.execute_script("arguments[0].value = '';", email_field)
                time.sleep(0.1)
                
                # Method 2: Focus and select all, then delete
                try:
                    email_field.send_keys(Keys.CONTROL + "a")
                    time.sleep(0.1)
                    email_field.send_keys(Keys.DELETE)
                    time.sleep(0.1)
                except:
                    self.log_action("⚠️ Keyboard clearing failed, continuing")
                
                # Method 3: Standard WebDriver clear as backup
                try:
                    email_field.clear()
                    time.sleep(0.1)
                except:
                    self.log_action("⚠️ Standard clear failed, continuing")
                
                # Method 4: Triple JavaScript clear for stubborn fields
                for i in range(3):
                    self.driver.execute_script("arguments[0].value = '';", email_field)
                    time.sleep(0.05)
                
                # Step 3: Verify field is completely empty
                cleared_value = email_field.get_attribute('value') or ''
                if cleared_value:
                    self.log_action(f"⚠️ Field not completely cleared: '{cleared_value}', forcing JavaScript clear")
                    # Force JavaScript clear multiple times
                    for i in range(3):
                        self.driver.execute_script("arguments[0].value = '';", email_field)
                        time.sleep(0.1)
                    
                    cleared_value = email_field.get_attribute('value') or ''
                    if cleared_value:
                        self.log_action(f"❌ Cannot clear field completely: '{cleared_value}'", 'error')
                        return None
                
                # Step 4: Enhanced input with multiple methods
                self.log_action("✅ Field cleared completely, entering email")
                
                # Method 1: JavaScript input (most reliable, bypasses all interceptors)
                try:
                    self.driver.execute_script("arguments[0].value = arguments[1];", email_field, self.username)
                    # Trigger input events to ensure Facebook recognizes the change
                    self.driver.execute_script("""
                        var element = arguments[0];
                        var inputEvent = new Event('input', { bubbles: true });
                        var changeEvent = new Event('change', { bubbles: true });
                        element.dispatchEvent(inputEvent);
                        element.dispatchEvent(changeEvent);
                    """, email_field)
                    self.log_action("✅ JavaScript input successful")
                except Exception as js_input_error:
                    self.log_action(f"⚠️ JavaScript input failed: {str(js_input_error)}")
                    
                    # Method 2: Fallback to WebDriver send_keys
                    try:
                        email_field.send_keys(self.username)
                        self.log_action("✅ WebDriver send_keys successful")
                    except Exception as keys_error:
                        self.log_action(f"❌ WebDriver send_keys failed: {str(keys_error)}")
                        return None
                
                time.sleep(0.5)
                
                # Step 5: Critical verification
                final_value = email_field.get_attribute('value') or ''
                if final_value != self.username:
                    self.log_action(f"❌ Email verification failed: got '{final_value}', expected '{self.username}'", 'error')
                    return None
                
                self.log_action("✅ Email entered and verified successfully")
                return email_field
                
            except Exception as e:
                self.log_action(f"❌ Error handling email field: {str(e)}", 'error')
                return None
                
        except Exception as e:
            self.log_action(f"❌ Error finding email field: {str(e)}", 'error')
            return None
    
    def _find_and_prepare_password_field(self):
        """Find password field and safely enter password"""
        try:
            self.log_action("🔒 Looking for password field")
            
            # Find password field
            password_selectors = [
                (By.ID, "pass"),
                (By.NAME, "pass"),
                (By.XPATH, "//input[@type='password']"),
                (By.XPATH, "//input[@placeholder='Password']")
            ]
            
            password_field = None
            for selector_type, selector in password_selectors:
                try:
                    password_field = self.driver.find_element(selector_type, selector)
                    self.log_action(f"✅ Found password field: {selector}")
                    break
                except:
                    continue
                    
            if not password_field:
                self.log_action("❌ Could not find password field", 'error')
                self.take_screenshot("no_password_field")
                return None
            
            # ANTI-DUPLICATION: Check current content
            try:
                current_value = password_field.get_attribute('value') or ''
                if len(current_value) == len(self.password):
                    self.log_action("✅ Password field already contains correct length value")
                    return password_field
                elif current_value:
                    self.log_action(f"⚠️ Password field contains {len(current_value)} chars, expected {len(self.password)}, will clear and re-enter")
                
                # ULTRA-SAFE CLEARING
                self._ultra_safe_clear_field(password_field, "password")
                
                # Enter password
                password_field.send_keys(self.password)
                time.sleep(0.3)
                
                # Verify input (check length only for security)
                final_value = password_field.get_attribute('value') or ''
                if len(final_value) == len(self.password):
                    self.log_action("✅ Password entered successfully")
                    return password_field
                else:
                    self.log_action(f"❌ Password verification failed: got {len(final_value)} chars, expected {len(self.password)}", 'error')
                    return None
                    
            except Exception as e:
                self.log_action(f"❌ Error handling password field: {str(e)}", 'error')
                return None
                
        except Exception as e:
            self.log_action(f"❌ Error finding password field: {str(e)}", 'error')
            return None
    
    def _ultra_safe_clear_field(self, field, field_name):
        """Ultra-safe field clearing that prevents stale element errors"""
        try:
            # Method 1: Standard clear
            field.clear()
            time.sleep(0.2)
            
            # Method 2: Select all and delete
            try:
                field.send_keys(Keys.CONTROL + "a")
                time.sleep(0.1)
                field.send_keys(Keys.DELETE)
                time.sleep(0.1)
            except:
                pass
            
            # Method 3: JavaScript force clear
            try:
                self.driver.execute_script("arguments[0].value = '';", field)
                time.sleep(0.1)
            except:
                pass
            
            # Verify clearing
            current_value = field.get_attribute('value') or ''
            if current_value:
                self.log_action(f"⚠️ {field_name} field still contains: '{current_value[:20]}...', but proceeding", 'warning')
            else:
                self.log_action(f"✅ {field_name} field cleared successfully")
                
        except Exception as e:
            self.log_action(f"⚠️ Error clearing {field_name} field: {str(e)}", 'warning')
    
    def _find_and_click_login_button(self):
        """Find and click login button safely"""
        try:
            self.log_action("🎯 Looking for login button")
            
            # Find login button
            login_selectors = [
                (By.NAME, "login"),
                (By.XPATH, "//button[@name='login']"),
                (By.XPATH, "//button[contains(text(), 'Log In')]"),
                (By.XPATH, "//button[contains(text(), 'Log in')]"),
                (By.XPATH, "//input[@value='Log In']"),
                (By.XPATH, "//input[@type='submit']")
            ]
            
            login_button = None
            for selector_type, selector in login_selectors:
                try:
                    login_button = self.driver.find_element(selector_type, selector)
                    self.log_action(f"✅ Found login button: {selector}")
                    break
                except:
                    continue
                    
            if not login_button:
                self.log_action("❌ Could not find login button", 'error')
                self.take_screenshot("no_login_button")
                return False
            
            # Click login button
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", login_button)
                time.sleep(0.5)
                login_button.click()
                self.log_action("✅ Clicked login button")
            except Exception as click_error:
                self.log_action(f"⚠️ Regular click failed, trying JavaScript: {str(click_error)}")
                self.driver.execute_script("arguments[0].click();", login_button)
                self.log_action("✅ JavaScript click successful")
            
            # Wait for login completion
            return self._wait_for_login_completion()
            
        except Exception as e:
            self.log_action(f"❌ Error with login button: {str(e)}", 'error')
            return False
    
    def _wait_for_login_completion(self):
        """Wait for login to complete and verify success"""
        try:
            self.log_action("⏳ Waiting for login completion...")
            
            # Step 1: Handle post-login dialogs FIRST
            self._handle_post_login_dialogs()
            
            # Step 2: Wait for navigation or login success indicators
            start_time = time.time()
            timeout = 15
            
            while time.time() - start_time < timeout:
                current_url = self.driver.current_url
                
                # Check for successful login indicators
                if "/checkpoint" in current_url or "/captcha" in current_url:
                    self._mark_verification_required("checkpoint", "Facebook checkpoint or CAPTCHA requires manual verification")
                    return False
                if ("facebook.com/home" in current_url or
                    "facebook.com/?sk=" in current_url):
                    self.log_action("✅ Login successful - detected URL change")
                    self._is_logged_in = True
                    return True
                
                # Check for navigation bar (indicates successful login)
                try:
                    self.driver.find_element(By.XPATH, "//div[@role='banner']")
                    self.log_action("✅ Login successful - detected navigation bar")
                    self._is_logged_in = True
                    return True
                except:
                    pass
                
                time.sleep(1)
            
            # Step 3: Final verification attempts
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//div[@role='banner']"))
                )
                self.log_action("✅ Login successful - final verification passed")
                self._is_logged_in = True
                return True
            except:
                # Last chance: check if we're on any facebook page (not login)
                if "facebook.com" in self.driver.current_url and "login" not in self.driver.current_url:
                    self.log_action("✅ Login appears successful - on Facebook page")
                    self._is_logged_in = True
                    return True
            
            self.log_action("❌ Login verification timeout", 'error')
            self.take_screenshot("login_timeout")
            
            # In visible mode, keep the browser open and allow manual completion.
            if not self.headless:
                self.log_action("🖐️ Automatic login did not finish. Waiting for manual login in visible browser...", 'warning')
                self.stats['status'] = 'Waiting for manual login'
                self._focus_browser_window()
                manual_wait_start = time.time()
                manual_timeout = 300
                while time.time() - manual_wait_start < manual_timeout:
                    try:
                        self.driver.current_url
                    except Exception as e:
                        self.log_action(f"❌ Browser window closed during manual login wait: {str(e)}", 'error')
                        self.is_posting = False
                        self.stats['status'] = 'Error'
                        self.stats['error'] = 'Browser window was closed during manual login'
                        return False
                    try:
                        self._handle_post_login_dialogs()
                    except Exception:
                        pass
                    if self.is_logged_in:
                        self.log_action("✅ Manual login completed successfully")
                        self.stats['status'] = 'Running'
                        return True
                    time.sleep(2)
                self.log_action("❌ Manual login timed out", 'error')
            
            return False
            
        except Exception as e:
            self.log_action(f"❌ Error waiting for login: {str(e)}", 'error')
            return False
    
    def _handle_post_login_dialogs(self):
        """Handle dialogs that appear after successful login"""
        try:
            self.log_action("🔍 Checking for post-login dialogs...")
            
            # Check for "Remember Password" dialog (КРИТИЧЕСКИЙ ДИАЛОГ!)
            try:
                save_password_selectors = [
                    "//button[contains(text(), 'ОК') or contains(text(), 'OK')]",
                    "//button[contains(text(), 'Не сейчас') or contains(text(), 'Not Now')]",
                    "//button[contains(text(), 'Save') or contains(text(), 'Сохранить')]",
                    "//button[contains(text(), 'Later') or contains(text(), 'Позже')]",
                    "//div[contains(text(), 'Запомнить пароль') or contains(text(), 'Remember password')]/..//button",
                    "//div[contains(text(), 'Save password') or contains(text(), 'Сохранить пароль')]/..//button"
                ]
                
                for selector in save_password_selectors:
                    try:
                        save_button = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        self.log_action(f"✅ Found 'Save Password' dialog, clicking: {selector}")
                        save_button.click()
                        time.sleep(2)
                        self.log_action("✅ Successfully handled save password dialog")
                        break
                    except:
                        continue
            except:
                self.log_action("ℹ️ No save password dialog found")
            
            # Check for 2FA prompt
            try:
                self.log_action("🔍 Checking for 2FA verification")
                two_fa_selectors = [
                    "//input[@aria-label='Two-factor authentication code']",
                    "//input[contains(@placeholder, 'code')]",
                    "//input[contains(@id, 'approvals_code')]",
                    "//input[contains(@name, 'approvals_code')]"
                ]
                
                for selector in two_fa_selectors:
                    try:
                        two_fa_element = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                        self.log_action(f"⚠️ 2FA verification required. Waiting for manual input using selector: {selector}", 'warning')
                        self.take_screenshot("2fa_required")
                        self._mark_verification_required("need_2fa", "Facebook two-factor authentication requires manual verification")
                        return
                    except:
                        continue
            except Exception as e:
                self.log_action(f"ℹ️ No 2FA required: {str(e)}")
                
            # Check for other verification prompts (SMS, email verification)
            try:
                self.log_action("🔍 Checking for additional verification prompts")
                verify_selectors = [
                    "//button[contains(text(), 'Continue') or contains(text(), 'Продолжить')]",
                    "//button[contains(text(), 'Yes, Continue') or contains(text(), 'Да, продолжить')]",
                    "//button[contains(text(), 'This is me') or contains(text(), 'Это я')]",
                    "//button[contains(text(), 'Skip') or contains(text(), 'Пропустить')]"
                ]
                
                for selector in verify_selectors:
                    try:
                        verify_button = WebDriverWait(self.driver, 2).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        self.log_action(f"✅ Found verification button: {selector}, clicking it")
                        verify_button.click()
                        time.sleep(2)
                        break
                    except:
                        continue
            except Exception as e:
                self.log_action(f"ℹ️ No additional verification needed: {str(e)}")
                
        except Exception as e:
            self.log_action(f"⚠️ Error handling post-login dialogs: {str(e)}", 'warning')
    
    def logout(self):
        """Log out of Facebook"""
        self.log_action("Logging out of Facebook")
        self.stats['status'] = 'Logging out'
        
        # Set logged in state to False
        self._is_logged_in = False
        
        # Close WebDriver
        self.cleanup()
        
        return True
    
    def load_groups(self, groups_file='groups.txt'):
        """Load Facebook group URLs from a text file"""
        self.log_action(f"Loading groups from {groups_file}")
        groups = []
        
        # Check if file exists
        if not os.path.exists(groups_file):
            self.log_action(f"Groups file not found: {groups_file}", 'error')
            return []
            
        # Check if file is empty
        if os.path.getsize(groups_file) == 0:
            self.log_action(f"Groups file is empty: {groups_file}", 'error')
            return []
        
        try:
            with open(groups_file, 'r') as file:
                line_number = 0
                valid_count = 0
                invalid_count = 0
                
                for line in file:
                    line_number += 1
                    url = line.strip()
                    
                    # Skip empty lines
                    if not url:
                        continue
                        
                    # Validate the URL
                    if 'facebook.com/groups' in url:
                        groups.append(url)
                        valid_count += 1
                    else:
                        invalid_count += 1
                        self.log_action(f"Invalid group URL at line {line_number}: {url}", 'warning')
            
            # Provide summary
            if valid_count > 0:
                self.log_action(f"Loaded {valid_count} valid group URLs" + 
                               (f" (skipped {invalid_count} invalid URLs)" if invalid_count > 0 else ""))
            else:
                self.log_action(f"No valid group URLs found in {groups_file}", 'error')
                
            return groups
        except Exception as e:
            self.log_action(f"Failed to load groups: {str(e)}", 'error')
            return []
    
    def clean_text_for_chromedriver(self, text):
        """Prepare text for posting while preserving emoji and UTF-8 characters"""
        if not text:
            return ""
        
        # Логируем информацию о кодировке и эмодзи в сообщении
        emoji_count = 0
        for char in text:
            if ord(char) >= 0x1F600:  # Подсчитываем эмодзи (большинство эмодзи начинается с U+1F600)
                emoji_count += 1
        
        if emoji_count > 0:
            self.log_action(f"Message contains {emoji_count} emoji characters - preserving them! 😊", 'info')
        
        # Убираем только действительно проблемные символы (например, NUL символы)
        # Но сохраняем все эмодзи и Unicode символы
        cleaned_text = text.replace('\x00', '').replace('\ufeff', '')  # Удаляем только NUL и BOM
        
        # Нормализуем Unicode для консистентности
        try:
            import unicodedata
            cleaned_text = unicodedata.normalize('NFC', cleaned_text)
            self.log_action("Unicode text normalized to NFC form for better compatibility", 'info')
        except ImportError:
            self.log_action("Unicode normalization not available - using text as-is", 'warning')
        
        # Убеждаемся что текст в UTF-8
        try:
            # Проверяем что текст можно закодировать/декодировать в UTF-8
            test_encode = cleaned_text.encode('utf-8')
            test_decode = test_encode.decode('utf-8')
            if test_decode == cleaned_text:
                self.log_action("Text UTF-8 encoding verified successfully", 'info')
            else:
                self.log_action("Text encoding consistency check failed", 'warning')
        except UnicodeError as e:
            self.log_action(f"UTF-8 encoding issue detected: {str(e)}", 'warning')
            # В случае ошибки, используем безопасное кодирование
            cleaned_text = cleaned_text.encode('utf-8', errors='replace').decode('utf-8')
        
        if cleaned_text != text:
            self.log_action(f"Text cleaned: removed {len(text) - len(cleaned_text)} problematic characters", 'info')
        else:
            self.log_action("Text requires no cleaning - ready for posting", 'info')
        
        return cleaned_text

    def diagnose_message(self, message):
        """Diagnostic function to analyze message for potential posting issues"""
        self.log_action("Running message diagnostics", 'info')
        
        # Check for empty message
        if not message or not message.strip():
            self.log_action("Message is empty or contains only whitespace", 'error')
            return False
        
        # Check length
        if len(message) > 5000:
            self.log_action(f"Message is very long ({len(message)} characters)", 'warning')
        
        # Подсчитываем эмодзи (поддерживаем их!)
        emoji_count = 0
        for char in message:
            if ord(char) >= 0x1F600:  # Большинство эмодзи
                emoji_count += 1
        
        if emoji_count > 0:
            self.log_action(f"✅ Message contains {emoji_count} emoji characters - these will be preserved!", 'info')
        
        # Check for links
        links = re.findall(r'https?://[^\s]+', message)
        if links:
            self.log_action(f"Message contains {len(links)} links", 'info')
        
        # Check for special characters that might cause issues
        special_chars = sum(1 for char in message if not char.isalnum() and not char.isspace() and ord(char) < 0x1F600)
        if special_chars > 20:
            self.log_action(f"Message contains many special characters ({special_chars})", 'warning')
        
        # Анализируем кодировку
        try:
            message.encode('utf-8')
            self.log_action("✅ Message UTF-8 encoding is valid", 'info')
        except UnicodeEncodeError as e:
            self.log_action(f"❌ UTF-8 encoding issue: {str(e)}", 'error')
            return False
        
        self.log_action("📝 Message diagnostics completed successfully", 'info')
        return True

    def post_to_group(self, group_url, message):
        """Post the provided message to a Facebook group"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Navigate to the group
                self.log_action(f"Attempting to post to group: {group_url} (attempt {attempt + 1}/{max_retries})")
                
                # Check driver session before any operation
                if not self.check_driver_session():
                    self.log_action("Driver session is dead, attempting to restart")
                    if not self.restart_driver_session():
                        self.log_action("Failed to restart driver session", 'error')
                        return False
                
                # First check if we're already logged in
                if not self._is_logged_in and self.driver:
                    self.log_action("Not logged in, attempting to login first")
                    
                    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Сброс счетчика попыток входа перед КАЖДОЙ попыткой входа
                    self.log_action("🔄 Resetting login attempts counter before login attempt")
                    self.login_attempts = 0
                    self.login_in_progress = False
                    self.last_login_attempt = None
                    
                    if not self.login():
                        self.log_action("Failed to login, cannot post", 'error')
                        return False
                
                # Navigate to group URL using safe operation
                def navigate_to_group():
                    self.log_action(f"Navigating to group: {group_url}")
                    self.driver.get(group_url)
                    return True
                
                result = self.safe_driver_operation(navigate_to_group)
                if result is None:
                    self.log_action("Failed to navigate to group due to session issues", 'error')
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    else:
                        return False
                
                # Wait for the page to load and look for the post creation element
                self.log_action("Waiting for page to load and looking for post creation element")
                post_element = None
                
                from bot.selector_engine import SelectorEngine
                engine = SelectorEngine(self.driver, self.logger)
                post_element = engine.find_and_click_xpath(
                    SelectorEngine.post_creation_selectors(),
                    wait_seconds=8,
                    safe_operation=self.safe_driver_operation,
                )
                if post_element:
                    time.sleep(2)
                
                # Legacy fallback selectors if engine did not match
                post_creation_selectors = SelectorEngine.post_creation_selectors() if not post_element else []
                
                # Try each selector with explicit wait and session protection
                for i, selector in enumerate(post_creation_selectors):
                    try:
                        self.log_action(f"Trying post creation selector {i+1}/{len(post_creation_selectors)}")
                        
                        # Safe operation for finding and clicking element
                        def find_and_click_post_element():
                            # Wait for element to be present and clickable
                            post_element = WebDriverWait(self.driver, 8).until(
                                EC.element_to_be_clickable((By.XPATH, selector))
                            )
                            
                            # Scroll to element if needed
                            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", post_element)
                            time.sleep(1)
                            
                            # Try to click
                            try:
                                post_element.click()
                            except ElementClickInterceptedException:
                                # If click is intercepted, try JavaScript click
                                self.driver.execute_script("arguments[0].click();", post_element)
                            
                            return post_element
                        
                        result = self.safe_driver_operation(find_and_click_post_element)
                        if result is not None:
                            self.log_action(f"Successfully clicked post creation element using selector: {selector}")
                            post_element = result
                            time.sleep(2)  # Wait for composer to open
                            break
                        
                    except (TimeoutException, NoSuchElementException, ElementNotInteractableException) as e:
                        self.log_action(f"Selector {i+1} failed: {type(e).__name__}")
                        continue
                    except (InvalidSessionIdException, WebDriverException) as e:
                        error_str = str(e).lower()
                        if "invalid session id" in error_str or "session deleted" in error_str or "no such window" in error_str:
                            self.log_action(f"Session error in selector {i+1}: {str(e)}", 'warning')
                            # The safe_driver_operation should have handled this, but if we get here, break and retry
                            break
                        else:
                            self.log_action(f"WebDriver error with selector {i+1}: {str(e)}")
                            continue
                    except Exception as e:
                        self.log_action(f"Unexpected error with selector {i+1}: {str(e)}")
                        continue
                
                if not post_element:
                    # Try JavaScript approach as fallback
                    self.log_action("Standard selectors failed, trying JavaScript approach")
                    try:
                        # Look for elements containing the Russian text "Напишите что-нибудь"
                        js_script = """
                        function findPostCreationElement() {
                            // Look for elements with Russian placeholder text
                            let elements = Array.from(document.querySelectorAll('div, span, button'));
                            
                            for (let element of elements) {
                                let text = element.textContent || element.getAttribute('aria-label') || '';
                                if (text.includes('Напишите что-нибудь') || 
                                    text.includes('Write something') || 
                                    text.includes('What\\'s on your mind')) {
                                    
                                    // Check if element is clickable
                                    if (element.role === 'button' || 
                                        element.getAttribute('role') === 'button' ||
                                        element.contentEditable === 'true') {
                                        return element;
                                    }
                                    
                                    // Look for parent that might be clickable
                                    let parent = element.parentElement;
                                    while (parent) {
                                        if (parent.getAttribute('role') === 'button' || 
                                            parent.contentEditable === 'true') {
                                            return parent;
                                        }
                                        parent = parent.parentElement;
                                    }
                                }
                            }
                            return null;
                        }
                        
                        let element = findPostCreationElement();
                        if (element) {
                            element.scrollIntoView({behavior: 'smooth', block: 'center'});
                            element.click();
                            return true;
                        }
                        return false;
                        """
                        
                        result = self.driver.execute_script(js_script)
                        if result:
                            self.log_action("Successfully clicked post creation element using JavaScript")
                            time.sleep(2)  # Wait for composer to open
                            post_element = True  # Set flag to continue
                        else:
                            self.log_action("JavaScript approach also failed to find post creation element")
                    
                    except Exception as e:
                        self.log_action(f"JavaScript approach failed: {str(e)}")
                
                if not post_element:
                    error_msg = "Could not find post creation element"
                    self.log_action(f"{error_msg} with any method", 'error')
                    self.take_screenshot(f"no_post_element_attempt_{attempt+1}")
                    
                    if attempt < max_retries - 1:
                        self.log_action(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        # Отправляем уведомление об ошибке только при финальной неудаче
                        self.send_error_notification(group_url, error_msg)
                        return False
                
                # Wait for post dialog/composer to appear and find text area
                self.log_action("Waiting for post composer to appear")
                post_text_area = None
                
                # More robust selectors for the post text area - prioritize by reliability
                text_area_selectors = [
                    # Specific selectors for the main composer that appears after clicking "Напишите что-нибудь..."
                    "//div[@contenteditable='true' and @role='textbox' and contains(@aria-label, 'Напишите что-нибудь')]",
                    "//div[@contenteditable='true' and @role='textbox' and contains(@aria-label, 'Write something')]",
                    
                    # Look for the main composer area in dialog
                    "//div[@role='dialog']//div[@contenteditable='true' and @role='textbox']",
                    "//div[@role='dialog']//div[@contenteditable='true' and contains(@class, 'notranslate')]",
                    
                    # Search for composer with specific placeholders in Russian
                    "//div[@contenteditable='true' and contains(@aria-label, 'Напишите что-нибудь')]",
                    "//div[@contenteditable='true' and contains(@data-lexical-text, 'true')]",
                    
                    # Look for composer in the main page area (not dialog)
                    "//div[contains(@class, 'notranslate') and @contenteditable='true' and @role='textbox']",
                    "//div[contains(@class, 'notranslate') and @contenteditable='true']",
                    
                    # Generic approaches for any contenteditable areas
                    "//div[@role='dialog']//div[@contenteditable='true']",
                    "//div[contains(@class, 'composer')]//div[@contenteditable='true']",
                    
                    # Specific aria labels in multiple languages
                    "//div[contains(@aria-label, 'Write something') or contains(@aria-label, 'What') or contains(@aria-label, 'Напишите') or contains(@aria-label, 'Написать')]",
                    
                    # Data attributes approach
                    "//div[contains(@data-contents, 'true') and @contenteditable='true']",
                    
                    # Generic textbox role anywhere
                    "//div[@role='textbox' and @contenteditable='true']",
                    "//div[@role='textbox']",
                    
                    # Fallback: any contenteditable div
                    "//div[@contenteditable='true']"
                ]
                
                for i, selector in enumerate(text_area_selectors):
                    try:
                        self.log_action(f"Trying text area selector {i+1}/{len(text_area_selectors)}")
                        
                        # Safe operation for finding text area
                        def find_text_area():
                            post_text_area = WebDriverWait(self.driver, 8).until(
                                EC.presence_of_element_located((By.XPATH, selector))
                            )
                            
                            # Verify element is actually interactable
                            if post_text_area.is_enabled() and post_text_area.is_displayed():
                                return post_text_area
                            else:
                                return None
                        
                        result = self.safe_driver_operation(find_text_area)
                        if result is not None:
                            self.log_action(f"Found post text area using selector: {selector}")
                            post_text_area = result
                            break
                        else:
                            post_text_area = None
                            continue
                            
                    except (TimeoutException, NoSuchElementException) as e:
                        self.log_action(f"Text area selector {i+1} failed: {type(e).__name__}")
                        continue
                    except (InvalidSessionIdException, WebDriverException) as e:
                        error_str = str(e).lower()
                        if "invalid session id" in error_str or "session deleted" in error_str or "no such window" in error_str:
                            self.log_action(f"Session error in text area selector {i+1}: {str(e)}", 'warning')
                            break
                        else:
                            self.log_action(f"WebDriver error with text area selector {i+1}: {str(e)}")
                            continue
                    except Exception as e:
                        self.log_action(f"Unexpected error with text area selector {i+1}: {str(e)}")
                        continue
                
                if not post_text_area:
                    error_msg = "Could not find post text area"
                    self.log_action(error_msg, 'error')
                    self.take_screenshot(f"no_text_area_attempt_{attempt+1}")
                    
                    if attempt < max_retries - 1:
                        self.log_action(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        # Отправляем уведомление об ошибке только при финальной неудаче
                        self.send_error_notification(group_url, error_msg)
                        return False
                
                # Focus on the text area and enter the message
                self.log_action("Entering message text")
                try:
                    # Safe operation for initial click and clear
                    def click_and_clear_text_area():
                        # Click to focus first
                        post_text_area.click()
                        time.sleep(1)
                        
                        # Clear any existing text
                        try:
                            post_text_area.clear()
                        except:
                            # If clear() doesn't work, try selecting all and deleting
                            post_text_area.send_keys(Keys.CONTROL + "a")
                            post_text_area.send_keys(Keys.DELETE)
                        return True
                    
                    result = self.safe_driver_operation(click_and_clear_text_area)
                    if result is None:
                        error_msg = "Failed to click and clear text area due to session issues"
                        self.log_action(error_msg, 'error')
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        else:
                            self.send_error_notification(group_url, error_msg)
                            return False
                    
                    # Use multiple methods to ensure text is entered
                    entered_successfully = False
                    
                    # Method 1: Enhanced JavaScript content setting with UTF-8 and emoji support
                    try:
                        self.log_action("Using enhanced JavaScript method for UTF-8/emoji text entry")
                        
                        def enhanced_js_text_entry():
                            self.driver.execute_script("""
                                // Убеждаемся что элемент в фокусе
                                arguments[0].focus();
                                
                                // Очищаем содержимое
                                arguments[0].textContent = '';
                                arguments[0].innerHTML = '';
                                
                                // Устанавливаем текст с поддержкой эмодзи
                                const text = arguments[1];
                                arguments[0].textContent = text;
                                
                                // Принудительно устанавливаем значение для Facebook
                                if (arguments[0].setAttribute) {
                                    arguments[0].setAttribute('data-text', text);
                                }
                                
                                // Симулируем пользовательский ввод
                                const events = [
                                    new Event('focus', { bubbles: true }),
                                    new Event('input', { bubbles: true, cancelable: true }),
                                    new Event('change', { bubbles: true, cancelable: true }),
                                    new KeyboardEvent('keyup', { bubbles: true, key: 'Enter' })
                                ];
                                
                                events.forEach(event => {
                                    arguments[0].dispatchEvent(event);
                                });
                                
                                // Дополнительно для Facebook - симулируем ввод текста
                                if (window.InputEvent) {
                                    const inputEvent = new InputEvent('input', {
                                        bubbles: true,
                                        cancelable: true,
                                        inputType: 'insertText',
                                        data: text
                                    });
                                    arguments[0].dispatchEvent(inputEvent);
                                }
                                
                                console.log('Enhanced text entry completed with emoji support');
                            """, post_text_area, message)
                            
                            time.sleep(1.5)
                            
                            # Verify text was entered
                            entered_text = self.driver.execute_script("return arguments[0].textContent || arguments[0].innerText", post_text_area)
                            if entered_text and entered_text.strip():
                                return True
                            return False
                        
                        result = self.safe_driver_operation(enhanced_js_text_entry)
                        if result:
                            entered_successfully = True
                            self.log_action("✅ Successfully entered text with emoji support using enhanced JavaScript method")
                        
                    except Exception as e:
                        self.log_action(f"Enhanced JavaScript method failed: {str(e)}")
                    
                    # Method 2: Alternative JavaScript approach
                    if not entered_successfully:
                        try:
                            self.driver.execute_script("""
                                arguments[0].focus();
                                arguments[0].innerHTML = arguments[1].replace(/\\n/g, '<br>');
                                arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                                arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                            """, post_text_area, message)
                            
                            time.sleep(1)
                            
                            entered_text = self.driver.execute_script("return arguments[0].textContent || arguments[0].innerText", post_text_area)
                            if entered_text and entered_text.strip():
                                entered_successfully = True
                                self.log_action("Successfully entered text using JavaScript method 2")
                        except Exception as e:
                            self.log_action(f"JavaScript method 2 failed: {str(e)}")
                    
                    # Method 3: send_keys as fallback
                    if not entered_successfully:
                        try:
                            # Focus first, then clear, then type
                            post_text_area.click()
                            time.sleep(0.5)
                            post_text_area.clear()
                            time.sleep(0.5)
                            post_text_area.send_keys(message)
                            time.sleep(1)
                            entered_successfully = True
                            self.log_action("Successfully entered text using send_keys method")
                        except Exception as e:
                            self.log_action(f"send_keys method failed: {str(e)}")
                    
                    # Method 4: Try typing character by character if all else fails
                    if not entered_successfully:
                        try:
                            self.log_action("Trying character-by-character input as last resort")
                            post_text_area.click()
                            time.sleep(0.5)
                            post_text_area.clear()
                            time.sleep(0.5)
                            
                            # Type each character with small delays
                            for char in message:
                                post_text_area.send_keys(char)
                                time.sleep(0.05)  # Small delay between characters
                            
                            time.sleep(1)
                            entered_successfully = True
                            self.log_action("Successfully entered text using character-by-character method")
                        except Exception as e:
                            self.log_action(f"Character-by-character method failed: {str(e)}")
                    
                    if not entered_successfully:
                        raise Exception("All text entry methods failed")
                    
                    self.log_action("Successfully entered message text")
                    
                except Exception as e:
                    error_msg = f"Error entering message text: {str(e)}"
                    self.log_action(error_msg, 'error')
                    self.take_screenshot(f"text_entry_error_attempt_{attempt+1}")
                    
                    if attempt < max_retries - 1:
                        self.log_action(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        # Отправляем уведомление об ошибке только при финальной неудаче
                        self.send_error_notification(group_url, f"Text entry failed: {str(e)}")
                        return False
                
                # Find and click post button
                self.log_action("Looking for post button")
                post_button = None
                
                # Wait a bit more for the button to become active after text input
                time.sleep(2)
                
                # More robust selectors for the post button - multiple languages support
                post_button_selectors = [
                    # Dialog-specific post buttons with text matching - Russian first (including "Отправить")
                    "//div[@role='dialog']//div[@role='button'][.//span[contains(text(), 'Отправить')]]",
                    "//div[@role='dialog']//div[@role='button'][.//span[contains(text(), 'Опубликовать')]]",
                    "//div[@role='dialog']//div[@role='button'][.//span[contains(text(), 'Поделиться')]]",
                    "//div[@role='dialog']//div[@role='button'][.//span[text()='Post']]",
                    "//div[@role='dialog']//div[@role='button'][.//span[text()='Share']]",
                    
                    # Look for aria-label attributes - Russian first (including "Отправить")
                    "//div[@role='button' and contains(@aria-label, 'Отправить')]",
                    "//div[@role='button' and contains(@aria-label, 'Опубликовать')]",
                    "//div[@role='button' and contains(@aria-label, 'Поделиться')]",
                    "//div[@role='button' and @aria-label='Post']",
                    "//div[@role='button' and @aria-label='Share']",
                    
                    # Text-based search in multiple languages (including "Отправить")
                    "//span[contains(text(), 'Отправить')]//ancestor::div[@role='button'][1]",
                    "//span[contains(text(), 'Опубликовать')]//ancestor::div[@role='button'][1]",
                    "//span[contains(text(), 'Поделиться')]//ancestor::div[@role='button'][1]",
                    "//span[text()='Post']//ancestor::div[@role='button'][1]",
                    "//span[text()='Share']//ancestor::div[@role='button'][1]",
                    
                    # Search within composer or dialog areas
                    "//div[contains(@class, 'composer') or @role='dialog']//div[@role='button' and contains(@class, 'layerConfirm')]",
                    
                    # Generic submit buttons
                    "//div[@role='button' and @type='submit']",
                    "//button[@type='submit' or contains(@class, 'layerConfirm')]",
                    
                    # Facebook-specific class patterns
                    "//div[@role='button' and contains(@class, 'composerPostButton')]",
                    "//div[@role='button' and contains(@data-testid, 'react-composer-post-button')]",
                    
                    # Last resort: look for any button in dialogs
                    "//div[@role='dialog']//div[@role='button'][last()]"
                ]
                
                for i, selector in enumerate(post_button_selectors):
                    try:
                        self.log_action(f"Trying post button selector {i+1}/{len(post_button_selectors)}")
                        
                        # Wait for button to be present and clickable
                        post_button = WebDriverWait(self.driver, 8).until(
                            EC.presence_of_element_located((By.XPATH, selector))
                        )
                        
                        # Additional wait for button to become clickable
                        WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                        
                        # Verify button is enabled and visible
                        if post_button.is_enabled() and post_button.is_displayed():
                            self.log_action(f"Found post button using selector: {selector}")
                            break
                        else:
                            self.log_action(f"Post button found but not enabled/visible with selector {i+1}")
                            post_button = None
                            continue
                            
                    except (TimeoutException, NoSuchElementException) as e:
                        self.log_action(f"Post button selector {i+1} failed: {type(e).__name__}")
                        continue
                    except Exception as e:
                        self.log_action(f"Unexpected error with post button selector {i+1}: {str(e)}")
                        continue
                    
                if not post_button:
                    self.log_action("Could not find active post button", 'error')
                    self.take_screenshot(f"no_post_button_attempt_{attempt+1}")
                    
                    # Try JavaScript fallback to find and click the button
                    self.log_action("Trying JavaScript fallback to find post button")
                    try:
                        # Use JavaScript to find and click the post button
                        js_click_success = self.driver.execute_script("""
                            // Try to find post button by various methods
                            var buttons = document.querySelectorAll('div[role="button"]');
                            var postButton = null;
                            
                            for (var i = 0; i < buttons.length; i++) {
                                var btn = buttons[i];
                                var text = btn.textContent || btn.innerText || '';
                                var ariaLabel = btn.getAttribute('aria-label') || '';
                                
                                if (text.includes('Отправить') || text.includes('Опубликовать') || text.includes('Post') || 
                                    text.includes('Поделиться') || text.includes('Share') ||
                                    ariaLabel.includes('Отправить') || ariaLabel.includes('Опубликовать') || ariaLabel.includes('Post') ||
                                    ariaLabel.includes('Поделиться') || ariaLabel.includes('Share')) {
                                    
                                    // Make sure it's visible and enabled
                                    if (btn.offsetParent !== null && !btn.disabled) {
                                        postButton = btn;
                                        break;
                                    }
                                }
                            }
                            
                            if (postButton) {
                                postButton.scrollIntoView({behavior: 'smooth', block: 'center'});
                                setTimeout(function() {
                                    postButton.click();
                                }, 500);
                                return true;
                            }
                            return false;
                        """)
                        
                        if js_click_success:
                            self.log_action("Successfully clicked post button using JavaScript fallback")
                            time.sleep(3)  # Wait for post to process
                        else:
                            self.log_action("JavaScript fallback could not find post button")
                            
                            if attempt < max_retries - 1:
                                self.log_action(f"Retrying in {retry_delay} seconds...")
                                time.sleep(retry_delay)
                                continue
                            else:
                                # Отправляем уведомление об ошибке при неудаче с постом
                                self.send_error_notification(group_url, "Could not find active post button")
                                return False
                                
                    except Exception as e:
                        self.log_action(f"JavaScript fallback failed: {str(e)}")
                        if attempt < max_retries - 1:
                            self.log_action(f"Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            # Отправляем уведомление об ошибке при JavaScript fallback неудаче
                            self.send_error_notification(group_url, f"Post button not found (JS fallback failed): {str(e)}")
                            return False
                else:
                    # Click the post button using multiple methods
                    try:
                        self.log_action("Clicking post button")
                        
                        # Scroll button into view
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", post_button)
                        time.sleep(1)
                        
                        # Highlight button for debugging
                        self.driver.execute_script("arguments[0].style.border='3px solid red';", post_button)
                        time.sleep(0.5)
                        
                        # Method 1: Regular click
                        click_success = False
                        try:
                            post_button.click()
                            click_success = True
                            self.log_action("Successfully clicked post button with regular click")
                        except ElementClickInterceptedException:
                            self.log_action("Regular click intercepted, trying JavaScript click")
                        except Exception as e:
                            self.log_action(f"Regular click failed: {str(e)}")
                        
                        # Method 2: JavaScript click
                        if not click_success:
                            try:
                                self.driver.execute_script("arguments[0].click();", post_button)
                                click_success = True
                                self.log_action("Successfully clicked post button with JavaScript click")
                            except Exception as e:
                                self.log_action(f"JavaScript click failed: {str(e)}")
                        
                        # Method 3: Force click with event dispatch
                        if not click_success:
                            try:
                                self.driver.execute_script("""
                                    var event = new MouseEvent('click', {
                                        view: window,
                                        bubbles: true,
                                        cancelable: true
                                    });
                                    arguments[0].dispatchEvent(event);
                                """, post_button)
                                click_success = True
                                self.log_action("Successfully clicked post button with force event dispatch")
                            except Exception as e:
                                self.log_action(f"Force event dispatch failed: {str(e)}")
                        
                        # Method 4: ActionChains click
                        if not click_success:
                            try:
                                from selenium.webdriver.common.action_chains import ActionChains
                                ActionChains(self.driver).move_to_element(post_button).click().perform()
                                click_success = True
                                self.log_action("Successfully clicked post button with ActionChains")
                            except Exception as e:
                                self.log_action(f"ActionChains click failed: {str(e)}")
                        
                        if not click_success:
                            raise Exception("All click methods failed")
                        
                        # Wait for posting to complete
                        self.log_action("Waiting for post to be submitted")
                        time.sleep(4)  # Increased wait time
                        
                    except Exception as e:
                        self.log_action(f"Error clicking post button: {str(e)}", 'error')
                        self.take_screenshot(f"post_button_click_error_attempt_{attempt+1}")
                        
                        if attempt < max_retries - 1:
                            self.log_action(f"Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            # Отправляем уведомление об ошибке при неудаче клика по кнопке поста
                            self.send_error_notification(group_url, f"Post button click failed: {str(e)}")
                            return False
                
                # Verify post was successful by checking if dialog is closed or success indicators
                posting_success = False
                
                # Method 1: Check if dialog disappeared
                try:
                    WebDriverWait(self.driver, 8).until_not(
                        EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
                    )
                    posting_success = True
                    self.log_action("✓ Post dialog closed - post successful")
                except TimeoutException:
                    self.log_action("Post dialog still present, checking for success indicators")
                    
                    # Method 2: Look for success messages or post appearing on page
                    try:
                        success_indicators = [
                            "//div[contains(text(), 'Your post is now published') or contains(text(), 'Posted') or contains(text(), 'опубликован') or contains(text(), 'Опубликовано')]",
                            "//div[contains(text(), 'Your post has been shared') or contains(text(), 'поделились')]",
                            f"//div[contains(text(), '{message[:50]}')]"  # Look for our message on the page
                        ]
                        
                        for indicator in success_indicators:
                            try:
                                WebDriverWait(self.driver, 3).until(
                                    EC.presence_of_element_located((By.XPATH, indicator))
                                )
                                posting_success = True
                                self.log_action("✓ Found success indicator - post successful")
                                break
                            except TimeoutException:
                                continue
                                
                        # Method 3: Check if we're back to the group feed
                        if not posting_success:
                            try:
                                # Look for feed elements that indicate we're back to the group page
                                WebDriverWait(self.driver, 3).until(
                                    EC.presence_of_element_located((By.XPATH, "//div[@data-pagelet='GroupFeed']"))
                                )
                                posting_success = True
                                self.log_action("✓ Returned to group feed - post likely successful")
                            except TimeoutException:
                                pass
                                
                    except Exception as e:
                        self.log_action(f"Error checking for success indicators: {str(e)}")
                
                # Take a screenshot of the result
                group_id = group_url.split('/')[-1].split('?')[0] if '/' in group_url else 'unknown'
                self.take_screenshot(f"post_result_{group_id}_attempt_{attempt+1}")
                
                if posting_success:
                    self.log_action(f"✓ Posting to group {group_url} completed successfully")
                    
                    post_url = None
                    post_id = None
                    try:
                        from .post_link_extractor import extract_post_link_from_driver
                        post_url, post_id = extract_post_link_from_driver(self.driver, message, group_url)
                        if post_url:
                            self.log_action(f"Captured post permalink: {post_url}")
                    except Exception as link_error:
                        self.log_action(f"Permalink extraction skipped: {link_error}", 'warning')
                    
                    # Save to analytics if enabled
                    if self.analytics_enabled and self.analytics_db:
                        try:
                            group_id = group_url.split('/')[-1].split('?')[0]
                            group_name = self.extract_group_name(group_url)
                            template_id = getattr(self, 'current_template_id', None)
                            uid = getattr(self, 'user_id', None)
                            self.analytics_db.save_post(
                                group_id,
                                group_name,
                                group_url,
                                message,
                                template_id,
                                uid,
                                post_url=post_url,
                                post_id=post_id,
                            )
                            self.analytics_db.update_group_stats(
                                group_id, True, group_name=group_name, group_url=group_url, user_id=uid or 0
                            )
                            self.log_action("Post saved to analytics database")
                        except Exception as e:
                            self.log_action(f"Failed to save analytics: {e}", 'warning')
                    
                    return True
                elif attempt == max_retries - 1:
                    # On the last attempt, be more lenient
                    self.log_action(f"? Posting to group {group_url} completed (status uncertain)")
                    
                    post_url = None
                    post_id = None
                    try:
                        from .post_link_extractor import extract_post_link_from_driver
                        post_url, post_id = extract_post_link_from_driver(self.driver, message, group_url)
                    except Exception:
                        pass
                    if self.analytics_enabled and self.analytics_db:
                        try:
                            group_id = group_url.split('/')[-1].split('?')[0]
                            group_name = self.extract_group_name(group_url)
                            template_id = getattr(self, 'current_template_id', None)
                            uid = getattr(self, 'user_id', None)
                            self.analytics_db.save_post(
                                group_id,
                                group_name,
                                group_url,
                                message,
                                template_id,
                                uid,
                                post_url=post_url,
                                post_id=post_id,
                            )
                            self.analytics_db.update_group_stats(
                                group_id, True, group_name=group_name, group_url=group_url, user_id=uid or 0
                            )
                            self.log_action("Uncertain post saved to analytics database")
                        except Exception as e:
                            self.log_action(f"Failed to save analytics: {e}", 'warning')
                    
                    return True  # Consider uncertain as success to avoid infinite retries
                else:
                    self.log_action("✗ Post submission uncertain, will retry")
                    time.sleep(retry_delay)
                    continue
                
            except Exception as e:
                self.log_action(f"Error in post_to_group (attempt {attempt+1}): {str(e)}", 'error')
                self.take_screenshot(f"post_to_group_error_attempt_{attempt+1}")
                
                if attempt < max_retries - 1:
                    self.log_action(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    continue
                else:
                    # Отправляем уведомление об ошибке при критической неудаче
                    self.send_error_notification(group_url, f"Critical error: {str(e)}")
                    
                    # Save error to analytics if enabled
                    if self.analytics_enabled and self.analytics_db:
                        try:
                            group_id = group_url.split('/')[-1].split('?')[0]
                            group_name = self.extract_group_name(group_url)
                            self.analytics_db.update_group_stats(
                                group_id, False, group_name=group_name, group_url=group_url,
                                user_id=getattr(self, 'user_id', None) or 0,
                            )
                            self.analytics_db.log_error(group_id, group_name, "Critical error", str(e))
                            self.log_action("📊 Error saved to analytics database")
                        except Exception as analytics_error:
                            self.log_action(f"⚠️ Failed to save error analytics: {analytics_error}", 'warning')
                    
                    return False
        
        # If we get here, all attempts failed
        self.log_action(f"Failed to post to group {group_url} after {max_retries} attempts", 'error')
        # Отправляем уведомление об окончательной неудаче после всех попыток
        self.send_error_notification(group_url, f"Failed after {max_retries} attempts")
        
        # Save final failure to analytics if enabled
        if self.analytics_enabled and self.analytics_db:
            try:
                group_id = group_url.split('/')[-1].split('?')[0]
                group_name = self.extract_group_name(group_url)
                self.analytics_db.update_group_stats(
                    group_id, False, group_name=group_name, group_url=group_url,
                    user_id=getattr(self, 'user_id', None) or 0,
                )
                self.analytics_db.log_error(group_id, group_name, "Max attempts exceeded", f"Failed after {max_retries} attempts")
                self.log_action("📊 Final failure saved to analytics database")
            except Exception as analytics_error:
                self.log_action(f"⚠️ Failed to save final failure analytics: {analytics_error}", 'warning')
        
        return False

    def start_posting(self, message, groups_file='groups.txt', max_groups=None):
        """Start the posting process to multiple groups"""
        if not max_groups:
            max_groups = self.max_groups
            
        self.stats['start_time'] = datetime.now()
        self.stats['posts_completed'] = 0
        self.stats['posts_failed'] = 0
        self.stats['status'] = 'Running'
        
        # Set is_posting flag to True
        self.is_posting = True
        self.stop_posting_flag = False
        self.posts_completed = 0
        self.posts_failed = 0
        
        # Reset Telegram counters and set session start time
        self.success_count = 0
        self.error_count = 0
        self.session_start_time = datetime.now()
        
        self.log_action(f"Starting posting session (max {max_groups} groups)")
        
        # Setup WebDriver with enhanced session recovery
        if self.use_profile:
            if not self.setup_driver_with_profile(self.profile_dir):
                self.log_action("❌ Failed to setup driver with profile", 'error')
                self.cleanup()
                self.is_posting = False
                self.error = "Failed to setup driver with profile"
                self.stats['status'] = 'Error'
                return False
        else:
            if not self.setup_driver():
                self.log_action("❌ Failed to setup driver", 'error')
                self.cleanup()
                self.is_posting = False
                self.error = "Failed to setup driver"
                self.stats['status'] = 'Error'
                return False
        
        # УЛУЧШЕННАЯ ПРОВЕРКА СОСТОЯНИЯ БРАУЗЕРА с агрессивным восстановлением
        session_check_attempts = 0
        max_session_checks = 3
        
        while session_check_attempts < max_session_checks:
            try:
                # Проверяем что окно браузера еще открыто
                current_url = self.driver.current_url
                self.log_action(f"✅ Browser window is active: {current_url}")
                break  # Сессия работает, выходим из цикла
            except Exception as e:
                error_str = str(e).lower()
                session_check_attempts += 1
                
                if "no such window" in error_str or "target window already closed" in error_str or "invalid session id" in error_str:
                    self.log_action(f"❌ Browser window was closed (attempt {session_check_attempts}/{max_session_checks}), restarting driver session", 'error')
                    
                    if session_check_attempts < max_session_checks:
                        # Сбрасываем счетчики для свежей попытки
                        self.login_attempts = 0
                        self.login_in_progress = False
                        self.session_restarts = 0  # Сброс для критических ситуаций
                        
                        if not self.restart_driver_session():
                            self.log_action(f"❌ Failed to restart driver session on attempt {session_check_attempts}", 'error')
                            continue
                        
                        # Дополнительная проверка после перезапуска
                        time.sleep(2)
                        if not self.check_driver_session():
                            self.log_action(f"❌ Session still dead after restart attempt {session_check_attempts}", 'error')
                            continue
                    else:
                        # Исчерпали попытки восстановления
                        self.log_action("❌ All session recovery attempts failed", 'error')
                        self.cleanup()
                        self.is_posting = False
                        self.error = "Browser window closed and could not restart after multiple attempts"
                        self.stats['status'] = 'Error'
                        return False
                else:
                    self.log_action(f"⚠️ Unknown browser error (attempt {session_check_attempts}): {str(e)}", 'warning')
                    if session_check_attempts >= max_session_checks:
                        self.log_action("❌ Unrecoverable browser error", 'error')
                        self.cleanup()
                        self.is_posting = False
                        self.error = f"Unrecoverable browser error: {str(e)}"
                        self.stats['status'] = 'Error'
                        return False
        
        # Login to Facebook
        if not self.login():
            self.cleanup()
            self.is_posting = False
            return False
            
        # Load groups
        groups = self.load_groups(groups_file)
        if not groups:
            self.log_action("No valid groups found", 'error')
            self.stats['status'] = 'Error'
            self.cleanup()
            self.is_posting = False
            return False
            
        # Limit the number of groups to process
        groups_to_process = groups[:max_groups]
        self.groups_total = len(groups_to_process)
        self.log_action(f"Will post to {len(groups_to_process)} groups in this session")
        
        # Post to each group
        for i, group_url in enumerate(groups_to_process):
            if callable(getattr(self, 'task_control_callback', None)):
                self.task_control_callback()
            if self.stop_posting_flag or self.stats['status'] != 'Running':
                self.log_action("Posting process stopped by user", 'warning')
                break
                
            self.log_action(f"Processing group {i+1}/{len(groups_to_process)}: {group_url}")
            success = self.post_to_group(group_url, message)
            
            if success:
                self.posts_completed += 1
                self.success_count += 1
                # Отправляем уведомление об успехе (если не включен режим "только ошибки")
                self.send_success_notification(group_url)
            else:
                self.posts_failed += 1
                # error_count увеличивается в send_error_notification
            
            if i < len(groups_to_process) - 1 and not self.stop_posting_flag and self.stats['status'] == 'Running':
                # Random delay between posts
                delay = random.randint(self.min_delay, self.max_delay)
                self.log_action(f"Waiting {delay} seconds before next post")
                if callable(getattr(self, 'task_control_sleep', None)):
                    self.task_control_sleep(delay)
                else:
                    time.sleep(delay)
                
        # Finalize
        elapsed_time = datetime.now() - self.stats['start_time']
        self.log_action(f"Posting session completed: {self.stats['posts_completed']} successful, "
                        f"{self.stats['posts_failed']} failed in {elapsed_time}")
        
        # Отправляем итоговое Telegram уведомление
        self.send_session_complete_notification()
        
        if self.stats['status'] == 'Running':
            self.stats['status'] = 'Idle'
        
        # Set is_posting flag to False
        self.is_posting = False
            
        self.cleanup()
        return True
    
    def stop_posting_method(self):
        """Stop the current posting session"""
        self.log_action("Stopping posting session")
        self._set_runtime_status('Stopping')
        self.stop_posting_flag = True
        self.pause_posting_flag = False
        # Update old alias for compatibility
        self.stop_posting = True
        self.is_posting = False
        # is_posting will be set to False when the posting loop finishes
        return True
        
    def cleanup(self):
        """Close WebDriver and clean up resources"""
        if self.driver:
            self.log_action("Closing WebDriver")
            try:
                # Try to take a final screenshot if there were errors
                if self.stats['posts_failed'] > 0:
                    self.take_screenshot("final_state")
                    
                # Properly quit the driver
                try:
                    self.driver.close()
                except Exception as e:
                    self.log_action(f"Warning when closing browser tab: {str(e)}", 'warning')
                    
                try:    
                    self.driver.quit()
                    self.log_action("WebDriver closed successfully")
                except Exception as e:
                    self.log_action(f"Error closing WebDriver: {str(e)}", 'error')
            except Exception as e:
                self.log_action(f"Error during cleanup: {str(e)}", 'error')
            finally:
                # Always ensure driver is set to None to avoid reusing a dead driver
                self.driver = None
                # Reset login state
                self._is_logged_in = False
        
        # Update status if we're not still running
        if self.stats['status'] == 'Running':
            self.stats['status'] = 'Idle'
            
        self.log_action("Cleanup completed")

    def get_status(self):
        """Get the current status of the bot"""
        # Merge live counters into stats before returning
        try:
            self.stats['posts_completed'] = getattr(self, 'posts_completed', self.stats.get('posts_completed', 0))
            self.stats['posts_failed'] = getattr(self, 'posts_failed', self.stats.get('posts_failed', 0))
            self.stats['groups_total'] = getattr(self, 'groups_total', self.stats.get('groups_total', 0))
            self.stats['is_posting'] = bool(getattr(self, 'is_posting', False))
            self.stats['group_statuses'] = getattr(self, 'group_statuses', {})
            self.stats['recent_events'] = getattr(self, 'recent_events', [])[-100:]
            self.stats['paused'] = bool(getattr(self, 'pause_posting_flag', False))
        except Exception:
            pass
        
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
        
        # Treat manual-login / 2FA waiting as active session states for the UI.
        if status.get('status') in ('Waiting for manual login', 'Waiting for 2FA'):
            status['is_posting'] = True
        return status 

    def post_to_multiple_groups(self, message, groups_file='groups.txt', max_groups=None, use_templates=False, template_mode='random'):
        """Post message to multiple Facebook groups with enhanced error handling"""
        
        try:
            self.log_action("🚀 Starting Facebook Group Posting Session")
            
            # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Сброс счетчика попыток входа при начале новой сессии
            self.log_action("🔄 Resetting login attempts counter for new session")
            self.login_attempts = 0
            self.login_in_progress = False  
            self.last_login_attempt = None
            self.session_restarts = 0
            self._is_logged_in = False  # Force fresh login check
            
            # Initialize status tracking
            self.is_posting = True
            self.should_stop = False
            self.stop_posting_flag = False
            self.pause_posting_flag = False
            self.session_start_time = datetime.now()
            self.stats = {
                'status': 'Starting',
                'posts_completed': 0,
                'posts_failed': 0,
                'groups_total': 0,
                'start_time': self.session_start_time.isoformat(),
                'elapsed_time': '00:00:00',
                'current_group': None,
                'error': None,
                'session_restarts': 0,
                'paused': False
            }
            self.recent_events = []
            
            # Validate message before starting.
            # In template mode the final text is generated per group, so an empty manual message is valid.
            if (not use_templates) and (not message or not message.strip()):
                self.log_action("❌ Message is empty", 'error')
                self.cleanup()
                self.is_posting = False
                self.error = "Message cannot be empty"
                self.stats['status'] = 'Error'
                return False
            
            # Prepare message (templates or regular)
            if use_templates:
                self.log_action(f"🎯 Using template system in '{template_mode}' mode")
                try:
                    from .message_templates import get_template_manager
                    # Ensure manager reads the same shared file as API (/templates_data/message_templates.json)
                    self.template_manager = get_template_manager()
                    if not self.template_manager.has_templates():
                        self.log_action("⚠️ No templates available, falling back to regular message", 'warning')
                        use_templates = False
                        self.template_manager = None
                except ImportError:
                    self.log_action("❌ Template system not available, using regular message", 'warning')
                    use_templates = False
                    self.template_manager = None
            
            # Check and preprocess message
            self.log_action("✅ Message validation passed, preprocessing...")
            processed_message = self.clean_text_for_chromedriver(message)
            self.diagnose_message(processed_message)
            
            # Initialize WebDriver ПОСЛЕ сброса всех флагов
            if not self.driver:
                self.log_action("🌐 Initializing WebDriver...")
                if self.use_profile:
                    success = self.setup_driver_with_profile(self.profile_dir)
                else:
                    success = self.setup_driver()
                    
                if not success:
                    self.log_action("❌ Failed to initialize WebDriver", 'error')
                    self.cleanup()
                    self.is_posting = False
                    self.error = "Failed to initialize WebDriver"
                    self.stats['status'] = 'Error'
                    return False
            
            # УЛУЧШЕННАЯ ПРОВЕРКА СОСТОЯНИЯ БРАУЗЕРА
            try:
                # Проверяем что окно браузера еще открыто
                current_url = self.driver.current_url
                self.log_action(f"✅ Browser window is active: {current_url}")
            except Exception as e:
                error_str = str(e).lower()
                if "no such window" in error_str or "target window already closed" in error_str:
                    self.log_action("❌ Browser window was closed, restarting driver session", 'error')
                    if not self.restart_driver_session():
                        self.log_action("❌ Failed to restart driver session", 'error')
                        self.cleanup()
                        self.is_posting = False
                        self.error = "Browser window closed and could not restart"
                        self.stats['status'] = 'Error'
                        return False
                else:
                    self.log_action(f"⚠️ Unknown browser error: {str(e)}", 'warning')
            
            # Login to Facebook if not already logged in with profile
            if not self._is_logged_in:
                self.log_action("🔐 Need to login to Facebook")
                if not self.login():
                    self.log_action("❌ Failed to login to Facebook", 'error')
                    self.cleanup()
                    self.is_posting = False
                    self.error = "Failed to login to Facebook"
                    self.stats['status'] = 'Error'
                    return False
            else:
                self.log_action("✅ Already logged in to Facebook, proceeding to post")
                
            # Verify login state после успешного входа
            try:
                self.driver.get("https://www.facebook.com")
                time.sleep(2)
                self.log_action("✅ Login verification successful")
            except Exception as e:
                self.log_action(f"❌ Login verification failed: {str(e)}", 'error')
                # Force re-login
                self._is_logged_in = False
                self.login_attempts = 0  # Reset counter for fresh attempt
                if not self.login():
                    self.log_action("❌ Re-login failed", 'error')
                    self.cleanup()
                    self.is_posting = False
                    self.error = "Login verification failed"
                    self.stats['status'] = 'Error'
                    return False
            
            # Load groups
            groups = self.load_groups(groups_file)
            if not groups:
                self.log_action("❌ No valid groups found in the file", 'error')
                self.cleanup()
                self.is_posting = False
                self.error = "No valid groups found in the file"
                self.stats['status'] = 'Error'
                return False
            
            # Limit the number of groups to process
            groups_to_process = groups[:max_groups]
            self.groups_total = len(groups_to_process)
            self.log_action(f"📊 Will post to {len(groups_to_process)} groups in this session")
            
            # Initialize group statuses
            for group_url in groups_to_process:
                group_id = group_url.split('/')[-1].split('?')[0]
                self._sync_group_state(group_id, {
                    'url': group_url,
                    'status': 'Pending',
                    'timestamp': None,
                    'error': None
                })
            
            # Initialize batch tracking for smart notifications
            batch_size = self.batch_size
            batch_num = 1
            batch_success_count = 0
            batch_error_count = 0
            failed_groups_batch = []  # [(group_name, error_reason), ...]
            processed_in_batch = 0
            
            # Post to each group
            for i, group_url in enumerate(groups_to_process):
                self._wait_if_paused()
                if self.stop_posting_flag:
                    self.log_action("Posting process stopped by user", 'warning')
                    self._set_runtime_status('Stopped')
                    break

                if group_url in self.skip_success_urls:
                    group_id = group_url.split('/')[-1].split('?')[0]
                    self.log_action(f"Skipping already successful group: {group_url}")
                    self.group_statuses.setdefault(group_id, {'url': group_url, 'status': 'Skipped'})
                    self.group_statuses[group_id]['status'] = 'Skipped'
                    self._sync_group_state(group_id, self.group_statuses[group_id])
                    continue

                if self.health_monitor and self.account_id:
                    blocked, reason = self.health_monitor.is_blocked(self.account_id)
                    if blocked:
                        self.log_action(f"Account health block: {reason}", 'warning')
                        self.error = reason
                        self.stats['status'] = 'Paused'
                        self._set_runtime_status('Paused')
                        break

                if self.rate_limiter and self.account_id:
                    allowed, reason = self.rate_limiter.can_post(
                        self.account_id, self.hourly_limit, self.daily_limit
                    )
                    if not allowed:
                        self.log_action(f"Rate limit reached: {reason}", 'warning')
                        self.error = reason
                        self.stats['status'] = 'Paused'
                        self._set_runtime_status('Paused')
                        break
                
                # Extract group ID for status tracking
                group_id = group_url.split('/')[-1].split('?')[0]
                
                # Update group status to Processing
                self.stats['current_group'] = group_url
                self.group_statuses[group_id]['status'] = 'Processing'
                self.group_statuses[group_id]['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._sync_group_state(group_id, self.group_statuses[group_id])
                
                self.log_action(f"Processing group {i+1}/{len(groups_to_process)}: {group_url}")
                
                # Generate message for this group (template or standard)
                group_message = processed_message  # Default to standard message
                template_info = {}
                
                if use_templates and self.template_manager:
                    try:
                        # Generate unique message for this group.
                        template_count = len(self.template_manager.templates)
                        if template_mode == 'random':
                            template_index = None
                        elif template_mode == 'reverse':
                            template_index = (template_count - 1) - (i % template_count)
                        elif template_mode == 'shuffle_cycle':
                            if not hasattr(self, '_template_shuffle_cycle') or len(getattr(self, '_template_shuffle_cycle', [])) != template_count:
                                self._template_shuffle_cycle = list(range(template_count))
                                random.shuffle(self._template_shuffle_cycle)
                            template_index = self._template_shuffle_cycle[i % template_count]
                        else:
                            # Default sequential mode: use every saved template in order, then repeat.
                            template_index = i % template_count
                        generated_message, used_index, used_variables = self.template_manager.generate_message(template_index)
                        
                        # Clean the generated message
                        group_message = self.clean_text_for_chromedriver(generated_message)
                        
                        template_info = {
                            'template_index': used_index,
                            'variables_used': used_variables,
                            'original_template': self.template_manager.templates[used_index]
                        }
                        
                        # Log template usage if enabled
                        import configparser
                        config = configparser.ConfigParser()
                        config.read('config.ini')
                        log_template_usage = config.getboolean('Templates', 'log_template_usage', fallback=True)
                        
                        if log_template_usage:
                            self.log_action(f"🧠 Template #{used_index + 1}: {self.template_manager.templates[used_index][:50]}...")
                            variables_str = ', '.join([f"{k}={v}" for k, v in used_variables.items()])
                            self.log_action(f"📤 Generated: {group_message[:100]}{'...' if len(group_message) > 100 else ''}")
                            self.log_action(f"🎯 Variables: {variables_str}")
                            
                            # Send Telegram notification about template usage
                            telegram_msg = f"🧠 Использован шаблон: #{used_index + 1}\n📤 Итоговый текст: {group_message[:200]}{'...' if len(group_message) > 200 else ''}"
                            self.send_telegram_notification(telegram_msg)
                    
                    except Exception as e:
                        self.log_action(f"Error generating template message: {e}, falling back to standard message", 'warning')
                        group_message = processed_message  # Fallback to standard message
                
                # Post to group with generated message
                try:
                    success = self.post_to_group(group_url, group_message)
                    
                    # Update group status and batch counters
                    if success:
                        self.posts_completed += 1
                        self.success_count += 1
                        batch_success_count += 1
                        self.group_statuses[group_id]['status'] = 'Success'
                        self._sync_group_state(group_id, self.group_statuses[group_id])
                        self.log_action(f"✓ Successfully posted to group {i+1}/{len(groups_to_process)}")
                        if self.rate_limiter and self.account_id:
                            self.rate_limiter.record_post(self.account_id, self.user_id or 0, group_url, True)
                        if self.health_monitor and self.account_id:
                            self.health_monitor.record_result(self.account_id, True)
                    else:
                        self.posts_failed += 1
                        batch_error_count += 1
                        # error_count увеличивается в send_error_notification
                        self.group_statuses[group_id]['status'] = 'Failed'
                        error_reason = "Failed to post to group"
                        self.group_statuses[group_id]['error'] = error_reason
                        self._sync_group_state(group_id, self.group_statuses[group_id])
                        self.log_action(f"✗ Failed to post to group {i+1}/{len(groups_to_process)}")
                        if self.rate_limiter and self.account_id:
                            self.rate_limiter.record_post(self.account_id, self.user_id or 0, group_url, False)
                        if self.health_monitor and self.account_id:
                            self.health_monitor.record_result(self.account_id, False, error_reason)
                        
                        group_display_name = self.extract_group_name(group_url)
                        failed_groups_batch.append((group_display_name, error_reason))
                    
                except Exception as e:
                    # Catch any unexpected errors and continue with next group
                    self.posts_failed += 1
                    batch_error_count += 1
                    error_reason = f"Exception during posting: {str(e)}"
                    self.group_statuses[group_id]['status'] = 'Failed'
                    self.group_statuses[group_id]['error'] = error_reason
                    self._sync_group_state(group_id, self.group_statuses[group_id])
                    self.log_action(f"✗ Exception posting to group {i+1}/{len(groups_to_process)}: {str(e)}", 'error')
                    
                    # Добавляем в список неудачных для батча
                    group_display_name = self.extract_group_name(group_url)
                    failed_groups_batch.append((group_display_name, error_reason))
                    
                    # НЕ отправляем индивидуальные уведомления об ошибках
                    # self.send_error_notification(group_url, error_reason)
                    
                    # Take a screenshot for debugging
                    self.take_screenshot(f"exception_group_{group_id}")
                    
                    # Continue with next group instead of failing entire process
                
                # Update timestamp and batch counter
                self.group_statuses[group_id]['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._sync_group_state(group_id, self.group_statuses[group_id])
                processed_in_batch += 1
                
                # Отправляем батч-сводку каждые 10 групп
                if processed_in_batch >= batch_size or i == len(groups_to_process) - 1:
                    total_processed = i + 1
                    self.send_batch_summary_notification(
                        batch_num=batch_num,
                        batch_success=batch_success_count,
                        batch_failed=batch_error_count,
                        failed_groups=failed_groups_batch.copy(),
                        total_processed=total_processed,
                        total_groups=len(groups_to_process)
                    )
                    
                    # Сбрасываем счетчики батча
                    batch_num += 1
                    batch_success_count = 0
                    batch_error_count = 0
                    failed_groups_batch = []
                    processed_in_batch = 0
                
                if i < len(groups_to_process) - 1 and not self.stop_posting_flag:
                    # Random delay between posts with feedback
                    delay = random.randint(self.min_delay, self.max_delay)
                    self.log_action(f"Waiting {delay} seconds before next post")
                    
                    # Progressive delay message for long waits
                    if delay > 30:
                        halfway = delay // 2
                        self._set_runtime_status(f"Waiting ({halfway}s remaining)")
                        if callable(getattr(self, 'task_control_sleep', None)):
                            self.task_control_sleep(halfway)
                        else:
                            time.sleep(halfway)
                        self._wait_if_paused()
                        self._set_runtime_status(f"Waiting ({delay - halfway}s remaining)")
                        if callable(getattr(self, 'task_control_sleep', None)):
                            self.task_control_sleep(delay - halfway)
                        else:
                            time.sleep(delay - halfway)
                    else:
                        self._set_runtime_status(f"Waiting ({delay}s)")
                        if callable(getattr(self, 'task_control_sleep', None)):
                            self.task_control_sleep(delay)
                        else:
                            time.sleep(delay)
                    
                    # Reset status to Running
                    self._wait_if_paused()
                    self._set_runtime_status('Running')
            
            # Final report
            elapsed_time = datetime.now() - self.stats['start_time']
            elapsed_mins = elapsed_time.total_seconds() / 60
            avg_per_post = elapsed_mins / max(1, (self.posts_completed + self.posts_failed))
            
            # Generate summary with template info
            template_info = ""
            if use_templates and self.template_manager:
                template_info = f" using {len(self.template_manager.templates)} templates"
                if hasattr(self, 'session_restarts') and self.session_restarts > 0:
                    template_info += f" (sessions restarted: {self.session_restarts})"
            
            summary = (f"Completed posting to multiple groups{template_info}: {self.posts_completed} successful, "
                       f"{self.posts_failed} failed in {elapsed_mins:.1f} minutes "
                       f"(avg {avg_per_post:.1f} min/post)")
            
            self.log_action(summary)
            
            # Send final Telegram notification with template stats
            self.send_session_complete_notification(use_templates)
            
            # Store results in stats
            self.stats['posts_completed'] = self.posts_completed
            self.stats['posts_failed'] = self.posts_failed
            self.stats['status'] = 'Completed' if self.posts_completed > 0 else 'Failed'
            self.stats['elapsed_time'] = str(elapsed_time).split('.')[0]  # Format as HH:MM:SS
            self.stats['group_statuses'] = self.group_statuses
            
            self.is_posting = False
            
            # Make sure to cleanup and close the driver
            self.cleanup()
            return True
        except Exception as e:
            self.log_action(f"Error posting to multiple groups: {str(e)}", 'error')
            self.is_posting = False
            self.error = str(e)
            self.stats['status'] = 'Error'
            
            # Take a screenshot of the error state
            if self.driver:
                self.take_screenshot("multiple_groups_error")
            
            # Always cleanup in case of errors
            self.cleanup()
            return False

    def take_screenshot(self, reason="error"):
        """Take a screenshot of the current browser window for debugging"""
        if not self.driver:
            self.log_action("Cannot take screenshot - WebDriver is not initialized", 'error')
            return
        
        # Check session before taking screenshot
        if not self.check_driver_session():
            self.log_action("Cannot take screenshot - driver session is dead", 'warning')
            return
            
        try:
            # Create screenshots directory if it doesn't exist
            screenshots_dir = os.path.join(os.getcwd(), 'screenshots')
            if not os.path.exists(screenshots_dir):
                os.makedirs(screenshots_dir)
                
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{screenshots_dir}/{reason}_{timestamp}.png"
            
            # Take screenshot with session protection
            def take_screenshot_safe():
                self.driver.save_screenshot(filename)
                return filename
            
            result = self.safe_driver_operation(take_screenshot_safe)
            if result:
                self.log_action(f"Screenshot saved to {result}")
                return result
            else:
                self.log_action("Failed to take screenshot due to session issues", 'warning')
                return None
        except (InvalidSessionIdException, WebDriverException) as e:
            error_str = str(e).lower()
            if "invalid session id" in error_str or "session deleted" in error_str or "no such window" in error_str:
                self.log_action(f"Cannot take screenshot - session error: {str(e)}", 'warning')
            else:
                self.log_action(f"Failed to take screenshot: {str(e)}", 'error')
            return None
        except Exception as e:
            self.log_action(f"Failed to take screenshot: {str(e)}", 'error')
            return None 

    def send_batch_summary_notification(self, batch_num, batch_success, batch_failed, failed_groups, total_processed, total_groups):
        """
        Отправка сводки по батчу (каждые 10 групп)
        
        Args:
            batch_num (int): Номер батча
            batch_success (int): Количество успешных постов в батче
            batch_failed (int): Количество неудачных постов в батче  
            failed_groups (list): Список неудачных групп с причинами
            total_processed (int): Общее количество обработанных групп
            total_groups (int): Общее количество групп
        """
        # Формируем основное сообщение
        if batch_failed == 0:
            batch_emoji = "🎉"
            batch_status = "Все успешно!"
        elif batch_success > batch_failed:
            batch_emoji = "✅"
            batch_status = "Преимущественно успешно"
        else:
            batch_emoji = "⚠️"
            batch_status = "Много ошибок"
        
        # Базовая информация о батче
        message = (
            f"{batch_emoji} <b>Сводка по батчу #{batch_num}</b>\n\n"
            f"📊 <b>Результаты батча:</b>\n"
            f"✅ Успешно: <b>{batch_success}</b>\n"
            f"❌ Ошибок: <b>{batch_failed}</b>\n"
            f"📈 <b>Общий прогресс:</b> {total_processed}/{total_groups}\n\n"
        )
        
        # Добавляем информацию о неудачных группах если есть
        if failed_groups:
            message += f"🚫 <b>Неудачные группы в этом батче:</b>\n"
            for i, (group_name, error_reason) in enumerate(failed_groups[:5]):  # Показываем максимум 5
                # Ограничиваем длину названия группы
                if len(group_name) > 30:
                    group_name = group_name[:27] + "..."
                # Ограничиваем длину причины ошибки  
                if len(error_reason) > 40:
                    error_reason = error_reason[:37] + "..."
                message += f"• <code>{group_name}</code>\n  <i>{error_reason}</i>\n"
            
            # Если неудачных групп больше 5, показываем количество
            if len(failed_groups) > 5:
                message += f"... и ещё <b>{len(failed_groups) - 5}</b> групп\n"
        
        # Добавляем процент успешности батча
        batch_total = batch_success + batch_failed
        if batch_total > 0:
            success_rate = (batch_success / batch_total) * 100
            message += f"\n🎯 <b>Успешность батча:</b> {success_rate:.1f}%"
        
        self.send_telegram_notification(message, error_level=(batch_failed > batch_success))