"""Extract Facebook post permalinks from the active Selenium session."""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

POST_HREF_PATTERNS = (
    r"/groups/\d+/posts/\d+",
    r"/groups/\d+/permalink/\d+",
    r"story_fbid=",
    r"/posts/\d+",
)


def _normalize_post_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("/"):
        url = urljoin("https://www.facebook.com", url)
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.netloc else url


def _message_snippet(message: str, length: int = 80) -> str:
    snippet = re.sub(r"\s+", " ", (message or "").strip())
    return snippet[:length].lower()


def extract_post_link_from_driver(driver, message: str, group_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Try to find the permalink of the post we just published."""
    snippet = _message_snippet(message)
    group_id_match = re.search(r"/groups/(\d+)", group_url or "")
    group_id = group_id_match.group(1) if group_id_match else None

    try:
        candidates = driver.execute_script(
            """
            const snippet = arguments[0];
            const groupId = arguments[1];
            const patterns = ['/posts/', '/permalink/', 'story_fbid='];
            const results = [];
            const anchors = document.querySelectorAll('a[href]');
            for (const anchor of anchors) {
                const href = anchor.getAttribute('href') || '';
                if (!patterns.some((p) => href.includes(p))) continue;
                if (groupId && !href.includes(groupId)) continue;
                let container = anchor;
                for (let i = 0; i < 8 && container; i++) {
                    const text = (container.innerText || '').toLowerCase();
                    if (!snippet || text.includes(snippet)) {
                        results.push({href, text: text.slice(0, 200)});
                        break;
                    }
                    container = container.parentElement;
                }
            }
            return results.slice(0, 10);
            """,
            snippet,
            group_id,
        )
    except Exception as exc:
        logger.debug("DOM permalink extraction failed: %s", exc)
        candidates = []

    for item in candidates or []:
        href = _normalize_post_url(item.get("href", ""))
        if href and any(re.search(pattern, href) for pattern in POST_HREF_PATTERNS):
            post_id = _extract_post_id(href)
            return href, post_id

    try:
        current_url = driver.current_url or ""
        if any(re.search(pattern, current_url) for pattern in POST_HREF_PATTERNS):
            normalized = _normalize_post_url(current_url)
            return normalized, _extract_post_id(normalized)
    except Exception:
        pass

    return None, None


def _extract_post_id(url: str) -> Optional[str]:
    if not url:
        return None
    for pattern in (
        r"/groups/\d+/posts/(\d+)",
        r"/groups/\d+/permalink/(\d+)",
        r"/posts/(\d+)",
        r"story_fbid=(\d+)",
    ):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
