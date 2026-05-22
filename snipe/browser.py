from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)


def launch(storage_state_path: Path | None) -> tuple[Playwright, Browser, BrowserContext, Page]:
    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context_kwargs: dict = {
        "user_agent": UA,
        "locale": "zh-TW",
        "timezone_id": "Asia/Taipei",
        "viewport": {"width": 1280, "height": 900},
    }
    if storage_state_path and Path(storage_state_path).exists():
        context_kwargs["storage_state"] = str(storage_state_path)
        log.info("載入 storage_state: %s", storage_state_path)
    context = browser.new_context(**context_kwargs)
    page = context.new_page()
    return p, browser, context, page


def save_storage_state(context: BrowserContext, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
    log.info("storage_state 已存到 %s", path)
