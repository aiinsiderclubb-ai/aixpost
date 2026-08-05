"""Reusable selector strategies for fragile Facebook UI automation."""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    InvalidSessionIdException,
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class SelectorEngine:
    """Try ordered selector strategies until one succeeds."""

    def __init__(self, driver, logger: Optional[logging.Logger] = None):
        self.driver = driver
        self.logger = logger or logging.getLogger("SelectorEngine")

    def find_and_click_xpath(
        self,
        selectors: List[str],
        wait_seconds: int = 8,
        scroll: bool = True,
        safe_operation: Optional[Callable] = None,
    ):
        for index, selector in enumerate(selectors, start=1):
            try:
                self.logger.info("Trying selector %s/%s", index, len(selectors))

                def _click():
                    element = WebDriverWait(self.driver, wait_seconds).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    if scroll:
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                            element,
                        )
                    try:
                        element.click()
                    except ElementClickInterceptedException:
                        self.driver.execute_script("arguments[0].click();", element)
                    return element

                element = safe_operation(_click) if safe_operation else _click()
                if element is not None:
                    self.logger.info("Selector matched: %s", selector)
                    return element
            except (TimeoutException, NoSuchElementException, ElementNotInteractableException) as exc:
                self.logger.debug("Selector %s failed: %s", index, type(exc).__name__)
            except (InvalidSessionIdException, WebDriverException) as exc:
                self.logger.warning("WebDriver error on selector %s: %s", index, exc)
                raise
        return None

    @staticmethod
    def post_creation_selectors() -> List[str]:
        return [
            "//div[@role='button' and contains(@aria-label, 'Напишите что-нибудь')]",
            "//div[contains(@aria-label, 'Напишите что-нибудь')]",
            "//span[contains(text(), 'Напишите что-нибудь')]//ancestor::div[@role='button'][1]",
            "//div[@role='button' and contains(@aria-label, 'Write something')]",
            "//div[contains(@aria-label, 'Write something')]",
            "//span[contains(text(), 'Write something')]//ancestor::div[@role='button'][1]",
            "//div[@contenteditable='true' and @role='textbox']",
            "//div[@role='textbox' and @contenteditable='true']",
            "//div[contains(@class, 'notranslate') and @contenteditable='true']",
            "//div[@role='button' and (contains(text(), 'Write something') or contains(text(), 'What') or contains(text(), 'Что у вас') or contains(text(), 'Напишите'))]",
            "//div[contains(@aria-label, 'What') or contains(@aria-label, 'Написать')]",
            "//span[contains(text(), 'Create Post') or contains(text(), 'What') or contains(text(), 'Что у вас') or contains(text(), 'Создать публикацию')]//ancestor::div[@role='button']",
            "//div[contains(@data-pagelet, 'GroupComposer') or contains(@data-pagelet, 'composer')]",
            "//div[@role='button' and contains(@class, 'x1i10hfl') and (contains(@aria-label, 'Post') or contains(@aria-label, 'публикац'))]",
        ]

    @staticmethod
    def publish_button_selectors() -> List[str]:
        return [
            "//div[@role='dialog']//div[@role='button'][.//span[contains(text(), 'Опубликовать')]]",
            "//div[@role='button' and contains(@aria-label, 'Опубликовать')]",
            "//span[contains(text(), 'Опубликовать')]//ancestor::div[@role='button'][1]",
            "//div[@role='dialog']//div[@role='button'][.//span[contains(text(), 'Post')]]",
            "//div[@role='button' and contains(@aria-label, 'Post')]",
            "//span[contains(text(), 'Post')]//ancestor::div[@role='button'][1]",
            "//div[@role='dialog']//div[@role='button'][.//span[contains(text(), 'Поделиться')]]",
            "//div[@role='button' and contains(@aria-label, 'Share')]",
            "//span[contains(text(), 'Share')]//ancestor::div[@role='button'][1]",
        ]
