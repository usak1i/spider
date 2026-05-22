"""ticketplus 訂購流程的順序動作。

每個 step 都包 try/except + 截圖，失敗時 raise FlowError 並由 snipe.py 統一處理。
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout

from . import notify, selectors
from .config import Participant, Preferences

log = logging.getLogger(__name__)

LOGS_DIR = Path("logs")


class FlowError(RuntimeError):
    pass


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _screenshot(page: Page, label: str) -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    path = LOGS_DIR / f"{_ts()}-{label}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        log.info("截圖已存: %s", path)
    except Exception as e:
        log.warning("截圖失敗: %s", e)
    return path


def _click_first_visible_text(page: Page, texts: list[str], timeout: float = 5.0) -> bool:
    """Try each text in order, click the first visible match. Return True on success."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for text in texts:
            loc = page.get_by_text(text, exact=False).first
            try:
                if loc.is_visible(timeout=200):
                    loc.click(timeout=1000)
                    return True
            except PWTimeout:
                continue
            except Exception:
                continue
        time.sleep(0.1)
    return False


def goto_event(page: Page, url: str) -> None:
    log.info("進入訂購頁: %s", url)
    page.goto(url, wait_until="domcontentloaded")


def wait_for_next_stage(page: Page, expect_text_pattern: str, label: str, timeout: float = 45.0) -> None:
    """等待頁面切換完成：直接等下一階段特徵文字出現。

    遠大有兩種 loading 畫面（請別離開頁面 / 排隊購票中）互相切換，所以不依賴 loading
    消失，只等目標文字出現即可。

    expect_text_pattern: 正則字串（給 Playwright text= regex 用），命中即視為到達下一頁
    """
    log.info("等待 %s 載入…", label)
    try:
        page.locator(f"text=/{expect_text_pattern}/").first.wait_for(
            state="visible", timeout=int(timeout * 1000)
        )
    except PWTimeout:
        _screenshot(page, f"stage-wait-timeout-{label}")
        raise FlowError(f"等待 {label} 超時（找不到 /{expect_text_pattern}/）")
    log.info("已進入 %s", label)


def _buy_now_button_locator(page: Page, session_keyword: str | None):
    """回傳「立即購買」按鈕的 locator（過濾掉同名 tab）。

    若有 session_keyword：限定於包含該文字的 row/卡片內找按鈕。
    否則：頁面上第一個 button-role 的「立即購買」。
    """
    for text in selectors.BUY_NOW_TEXTS:
        if session_keyword:
            # 找包含關鍵字的列，再從列內找按鈕
            container = page.locator(
                f"tr:has-text('{session_keyword}'), "
                f"[class*='row']:has-text('{session_keyword}'), "
                f"[class*='session']:has-text('{session_keyword}')"
            ).first
            btn = container.get_by_role("button", name=text).first
        else:
            btn = page.get_by_role("button", name=text).first
        try:
            if btn.count() > 0:
                return btn
        except Exception:
            continue
    return None


def _on_zone_page(page: Page) -> str | None:
    """偵測是否已進到票區選擇頁面。回傳命中的標記，否則 None。"""
    for text in selectors.ZONE_PAGE_TEXT_MARKERS:
        try:
            if page.get_by_text(text, exact=False).first.is_visible(timeout=100):
                return f"text:{text}"
        except Exception:
            continue
    for sel in selectors.ZONE_PAGE_STRUCTURAL_MARKERS:
        try:
            if page.locator(sel).first.is_visible(timeout=100):
                return f"selector:{sel}"
        except Exception:
            continue
    return None


def click_buy_now_until_modal(
    page: Page,
    session_keyword: str | None = None,
    max_seconds: float = 30.0,
) -> None:
    """高頻點擊「立即購買」按鈕直到票區選擇頁出現。

    偵測票區頁的條件（任一命中即視為已進入）：
    - 文字「選擇票種」或「選擇票區」可見
    - 出現 .v-expansion-panel-header（正式場次的票區清單）
    - 出現含「剩餘」字樣的 .v-card
    """
    if session_keyword:
        log.info("嘗試點擊「立即購買」（場次關鍵字: %s）", session_keyword)
    else:
        log.info("嘗試點擊「立即購買」（第一個可用場次）")

    deadline = time.time() + max_seconds
    while time.time() < deadline:
        marker = _on_zone_page(page)
        if marker:
            log.info("票區選擇頁已出現（%s）", marker)
            return

        btn = _buy_now_button_locator(page, session_keyword)
        if btn is not None:
            try:
                if btn.is_visible(timeout=100) and btn.is_enabled(timeout=100):
                    btn.click(timeout=500, no_wait_after=True)
            except Exception:
                pass
        time.sleep(0.1)

    _screenshot(page, "buy-now-timeout")
    raise FlowError("超時未進入票區選擇頁面")


_PLUS_SELECTOR = (
    "button:has-text('+'), "
    "button:has(i.mdi-plus), "
    "button[aria-label*='增加'], "
    "button[aria-label*='plus' i], "
    "[class*='plus' i] button, "
    ".v-btn:has(i.mdi-plus)"
)

_SOLD_OUT_RE = re.compile(selectors.SOLD_OUT_PATTERN)


def _is_sold_out(text: str) -> bool:
    if not text:
        return False
    if any(ind in text for ind in selectors.SOLD_OUT_INDICATORS):
        return True
    return bool(_SOLD_OUT_RE.search(text))


_EXPANSION_DEBUG_PRINTED = {"v": False}
_WS_OR_COMMA_RE = re.compile(r"[\s,，]")


def _norm(s: str) -> str:
    """移除所有空白（含 NBSP、全形空白）與逗號。"""
    if not s:
        return ""
    return _WS_OR_COMMA_RE.sub("", s)


def _try_select_via_expansion(page: Page, keyword: str, count: int) -> bool:
    """嘗試 expansion panel 模式：點 header 展開後在 panel content 內按 +。

    用 normalized text 比對（去逗號），讓 "3200" 也能命中 "NT.3,200"。
    """
    headers = page.locator(selectors.EXPANSION_PANEL_HEADER)
    try:
        n = headers.count()
    except Exception:
        n = 0
    if n == 0:
        log.debug("  - %r: 沒找到 expansion-panel-header", keyword)
        return False

    norm_kw = _norm(keyword)
    matched_idx: int | None = None
    matched_text = ""
    print_all = not _EXPANSION_DEBUG_PRINTED["v"]
    if print_all:
        log.info("  - 發現 %d 個 expansion-panel-header，列出所有 inner_text:", n)

    for i in range(n):
        h = headers.nth(i)
        try:
            text = h.inner_text(timeout=300)
        except Exception as e:
            log.debug("    header[%d] inner_text 失敗: %s", i, e)
            continue
        if print_all:
            log.info("    header[%d] raw=%r norm=%r", i, text[:80], _norm(text)[:80])
        if norm_kw and norm_kw in _norm(text):
            if _is_sold_out(text):
                log.info("  - %r matched header[%d] %r 但售完，跳過", keyword, i, text[:60])
                continue
            matched_idx = i
            matched_text = text
            break

    if print_all:
        _EXPANSION_DEBUG_PRINTED["v"] = True

    if matched_idx is None:
        return False

    log.info("  - %r 命中 header[%d]: %r", keyword, matched_idx, matched_text[:80])
    header = headers.nth(matched_idx)
    try:
        header.scroll_into_view_if_needed(timeout=500)
    except Exception:
        pass
    try:
        header.click(timeout=1500)
    except Exception as e:
        log.warning("  - 點開 header 失敗: %s", e)
        return False

    # 找展開後的 content（同一個 .v-expansion-panel 容器）
    # 用 nth-of-type 配對 header idx 到 panel idx
    panels = page.locator(".v-expansion-panel")
    panel = panels.nth(matched_idx)
    content = panel.locator(selectors.EXPANSION_PANEL_CONTENT).first
    try:
        content.wait_for(state="visible", timeout=3000)
    except Exception:
        log.warning("  - %r expansion content 沒展開（可能 panel 不對位）", keyword)
        return False

    # 在 content 內找 + 按鈕（多種樣式）
    plus_btn = content.locator(_PLUS_SELECTOR).first
    if plus_btn.count() == 0:
        # fallback: v-btn--fab（FAB 風格按鈕，+ 是 SVG 圖示）
        plus_candidates = content.locator(".v-btn--fab, button.v-btn")
        try:
            n_btn = plus_candidates.count()
        except Exception:
            n_btn = 0
        # FAB 按鈕通常成對出現（- 與 +），取最後一個（+ 通常在右側）
        if n_btn >= 2:
            plus_btn = plus_candidates.nth(n_btn - 1)
        elif n_btn == 1:
            plus_btn = plus_candidates.first
        else:
            log.warning("  - %r content 內找不到 + 按鈕", keyword)
            return False

    try:
        for i in range(count):
            plus_btn.click(timeout=1500)
            page.wait_for_timeout(60)
        log.info("已選擇票區 %s 並設定張數 %d（expansion 模式）", keyword, count)
        return True
    except Exception as e:
        log.warning("  - %r 點 + 失敗: %s", keyword, e)
        return False


def _try_select_via_direct_row(page: Page, keyword: str, count: int) -> bool:
    """嘗試 direct row 模式（測試場次用），row 直接包含 +/- 按鈕。"""
    candidates = [
        f".v-card:has-text('{keyword}')",
        f".v-list-item:has-text('{keyword}')",
        f"[class*='ticket-row']:has-text('{keyword}')",
        f"[class*='ticket-card']:has-text('{keyword}')",
        f"[class*='zone']:has-text('{keyword}')",
        f"tr:has-text('{keyword}')",
        f"[role='row']:has-text('{keyword}')",
        f"li:has-text('{keyword}')",
    ]
    row = None
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                row = loc
                break
        except Exception:
            continue
    if row is None:
        return False

    try:
        row_text = row.inner_text(timeout=500)
    except Exception:
        row_text = ""

    if _is_sold_out(row_text):
        log.info("  - %r 售完，跳過", keyword)
        return False

    try:
        row.click(timeout=500, no_wait_after=True)
    except Exception:
        pass

    plus_btn = row.locator(_PLUS_SELECTOR).first
    if plus_btn.count() == 0:
        plus_btn = page.locator(_PLUS_SELECTOR).first
    if plus_btn.count() == 0:
        log.warning("  - %r 找不到 + 按鈕", keyword)
        return False

    try:
        for i in range(count):
            plus_btn.click(timeout=1500)
            page.wait_for_timeout(60)
        log.info("已選擇票區 %s 並設定張數 %d（direct row 模式）", keyword, count)
        return True
    except Exception as e:
        log.warning("  - %r 點 + 失敗: %s", keyword, e)
        return False


def select_zone_and_set_count(
    page: Page,
    zone_priority: list[str],
    count: int,
) -> str:
    """依優先序選票區並設定張數。

    支援兩種頁面結構：
    - Expansion panel（正式場次）：button.v-expansion-panel-header 點開後 +/- 顯示
    - Direct row（測試場次）：row 直接包含 +/-
    """
    log.info("依優先序選票區並設定張數=%d: %s", count, zone_priority)
    page.wait_for_timeout(400)  # 讓票區資訊載入

    for keyword in zone_priority:
        log.info("嘗試票區: %s", keyword)
        # 優先試 expansion panel（正式場次）
        if _try_select_via_expansion(page, keyword, count):
            return keyword
        # fallback：direct row（測試場次）
        if _try_select_via_direct_row(page, keyword, count):
            return keyword
        log.info("  - %r 兩種模式都失敗，跳過", keyword)

    _screenshot(page, "no-zone-available")
    raise FlowError(f"沒有可用票區，已嘗試: {zone_priority}")


def choose_allocation(page: Page, allocation: str) -> None:
    log.info("選擇選位方式: %s", allocation)
    if not _click_first_visible_text(page, [allocation], timeout=1.0):
        log.info("找不到 %r 選項（本場次無選位需求，沿用預設）", allocation)


def wait_for_captcha_if_present(page: Page, timeout: float = 120.0) -> bool:
    """若偵測到驗證碼 input，提示使用者並等待填完。回傳是否有處理 captcha。"""
    captcha_input = None
    for sel in selectors.CAPTCHA_INPUT_HINTS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=200):
                captcha_input = loc
                break
        except Exception:
            continue

    if captcha_input is None:
        log.info("未偵測到驗證碼欄位，繼續")
        return False

    log.info("偵測到驗證碼，等待使用者輸入…")
    notify.alert_captcha()

    # 等到 input 有值且長度 >= 4
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            value = captcha_input.input_value(timeout=200)
            if value and len(value.strip()) >= 4:
                log.info("驗證碼已填入 (%d 字元)，繼續", len(value.strip()))
                return True
        except Exception:
            pass
        time.sleep(0.2)

    _screenshot(page, "captcha-timeout")
    raise FlowError("驗證碼等待超時")


def click_next(page: Page, timeout: float = 8.0) -> None:
    log.info("點擊「下一步」")
    deadline = time.time() + timeout
    while time.time() < deadline:
        # 優先用遠大專用 CSS class
        try:
            btn = page.locator(f"{selectors.NEXT_BTN_CSS}:not([disabled])").first
            if btn.count() > 0 and btn.is_visible(timeout=150):
                btn.scroll_into_view_if_needed(timeout=300)
                btn.click(timeout=1500)
                log.info("  - 已點擊（%s）", selectors.NEXT_BTN_CSS)
                return
        except Exception as e:
            log.debug("  - %s 失敗: %s", selectors.NEXT_BTN_CSS, e)

        # fallback: role=button + 文字
        for text in selectors.NEXT_TEXTS:
            try:
                btn = page.get_by_role("button", name=text).first
                if btn.count() > 0 and btn.is_visible(timeout=150):
                    if not btn.is_enabled(timeout=150):
                        continue  # disabled，等狀態變化
                    btn.click(timeout=1500)
                    log.info("  - 已點擊（role=button name=%r）", text)
                    return
            except Exception as e:
                log.debug("  - role=button name=%r 失敗: %s", text, e)
                continue
        time.sleep(0.2)

    _screenshot(page, "next-not-found")
    raise FlowError("找不到「下一步」按鈕")


def confirm_seat_result_if_present(page: Page, timeout: float = 4.0) -> bool:
    """若進到「確認選位結果」中間頁就點下一步。回傳是否有處理。

    (Deprecated: 使用 navigate_to_data_stage 替代，因為要處理 loading 切換)
    """
    try:
        marker = page.get_by_text(selectors.SEAT_CONFIRM_HEADER, exact=False).first
        marker.wait_for(state="visible", timeout=int(timeout * 1000))
    except Exception:
        return False
    log.info("偵測到「確認選位結果」中間頁，點下一步")
    click_next(page)
    return True


def navigate_to_data_stage(page: Page, timeout: float = 60.0) -> None:
    """從票區選擇後等待，可能經過「確認選位結果」中間頁，最終到達「填寫資料」頁。

    用 polling 迴圈處理：
    - 若看到「參加者資訊」或「同意/閱讀並」就視為已抵達 → 返回
    - 若看到「確認選位結果」就點下一步，繼續等
    - 中間若有 loading 畫面（請別離開頁面 / 排隊購票中）就忽略，繼續輪詢
    """
    log.info("等待中間頁/填寫資料頁載入…")
    deadline = time.time() + timeout
    seat_confirmed = False

    while time.time() < deadline:
        # 條件 A：已抵達填寫資料頁
        try:
            data_marker = page.locator("text=/參加者資訊|同意|閱讀並/").first
            if data_marker.is_visible(timeout=150):
                log.info("已抵達 填寫資料頁")
                return
        except Exception:
            pass

        # 條件 B：仍在「確認選位結果」中間頁 → 點下一步
        if not seat_confirmed:
            try:
                seat_marker = page.get_by_text(selectors.SEAT_CONFIRM_HEADER, exact=False).first
                if seat_marker.is_visible(timeout=150):
                    log.info("偵測到「確認選位結果」中間頁，點下一步")
                    click_next(page)
                    seat_confirmed = True
                    page.wait_for_timeout(300)
                    continue
            except Exception:
                pass

        time.sleep(0.3)

    _screenshot(page, "navigate-to-data-timeout")
    raise FlowError("等待填寫資料頁超時")


def fill_participants(page: Page, participants: list[Participant]) -> None:
    """編輯每位參加者並填入姓名/身分證/國籍。"""
    if not participants:
        log.info("config 無 participants，略過參加者填寫")
        return

    # 等參加者區塊標題出現
    try:
        page.get_by_text(selectors.PARTICIPANT_SECTION_HEADER, exact=False).first.wait_for(
            state="visible", timeout=10000
        )
    except Exception:
        log.info("頁面無「參加者資訊」區塊，可能本場次非實名制")
        return

    # 等「編輯」鍵實際 render 出來（rows 載入完成）
    log.info("等待「編輯」鍵 render…")
    try:
        page.get_by_text("編輯", exact=True).first.wait_for(state="visible", timeout=15000)
        log.info("  - 「編輯」鍵已出現")
    except Exception:
        # 沒等到，dump HTML 給人類除錯
        log.warning("  - 15 秒內未出現「編輯」鍵，dump 周邊 HTML：")
        try:
            section_html = page.evaluate("""
                () => {
                    const els = Array.from(document.querySelectorAll('*'));
                    const target = els.find(e => e.textContent && e.textContent.trim() === '參加者資訊');
                    if (!target) return 'NOT FOUND: 參加者資訊';
                    let parent = target.closest('.v-card, section, [class*="participant"]') || target.parentElement;
                    if (parent && parent.parentElement) parent = parent.parentElement;
                    return parent ? parent.outerHTML.substring(0, 4000) : 'NO PARENT';
                }
            """)
            log.warning("HTML 片段:\n%s", section_html)
        except Exception as e:
            log.debug("dump HTML 失敗: %s", e)
        _screenshot(page, "no-edit-button")
        raise FlowError("找不到「編輯」鍵")

    for i, p in enumerate(participants, start=1):
        log.info("填寫參加者 #%d: name=%s", i, p.name)
        if not _open_and_fill_participant(page, i, p):
            _screenshot(page, f"participant-{i}-fail")
            raise FlowError(f"填寫參加者 #{i} 失敗")


def _open_and_fill_participant(page: Page, idx: int, p: Participant) -> bool:
    """點擊第 idx 位參加者編輯鍵開啟 modal，填入 3 欄並按完成。

    遠大的編輯鍵是 <span class="d-none d-sm-block">編輯</span>（純文字「編輯」）
    """
    # Step 1：找到所有「編輯」鍵（嘗試多種策略 + 印出每個的命中數）
    strategies: list[tuple[str, object]] = [
        ("get_by_text exact", page.get_by_text("編輯", exact=True)),
        ("get_by_role button name=編輯", page.get_by_role("button", name="編輯")),
        ("span:has-text('編輯')", page.locator("span:has-text('編輯')")),
        ("button:has-text('編輯')", page.locator("button:has-text('編輯')")),
        ("text=編輯", page.locator("text=編輯")),
    ]
    edit_btns = None
    n_btns = 0
    for label, loc in strategies:
        try:
            count = loc.count()
        except Exception as e:
            log.debug("  - %s: count 失敗 %s", label, e)
            continue
        log.info("  - 策略 %s 命中 %d 個", label, count)
        if count > 0 and edit_btns is None:
            edit_btns = loc
            n_btns = count

    if edit_btns is None or n_btns < idx:
        log.warning("  - 找不到參加者 #%d 的編輯鍵（最佳策略 %d 個）", idx, n_btns)
        return False

    # Step 2：點第 idx 個編輯鍵開啟 modal
    target = edit_btns.nth(idx - 1)
    try:
        target.scroll_into_view_if_needed(timeout=500)
    except Exception:
        pass
    try:
        target.click(timeout=2000)
    except Exception as e:
        log.warning("  - 點擊編輯鍵失敗: %s", e)
        return False

    # Step 3：等 modal 出現（Vuetify 的 v-dialog）
    modal = None
    for sel in (".v-dialog--active", ".v-dialog[style*='display: block']", ".v-dialog"):
        try:
            m = page.locator(sel).last  # 最後一個（最新打開的）
            m.wait_for(state="visible", timeout=3000)
            modal = m
            log.info("  - 編輯 modal 已開啟 (selector=%s)", sel)
            break
        except Exception:
            continue

    if modal is None:
        log.warning("  - 編輯 modal 未出現")
        return False

    # Step 4：在 modal scope 內填三個欄位
    # Vuetify 的 label 不是標準 <label for=...>，所以改成「找含 label 文字的容器，
    # 再從容器內取 input」的方式，比 get_by_label 可靠。
    def _fill_in_modal(labels: list[str], value: str, is_autocomplete: bool = False) -> bool:
        for label in labels:
            container_sels = [
                f".v-text-field:has-text('{label}')",
                f".v-autocomplete:has-text('{label}')",
                f".v-input:has-text('{label}')",
                f"div:has(> label:has-text('{label}'))",
            ]
            for csel in container_sels:
                try:
                    container = modal.locator(csel).first
                    if container.count() == 0:
                        continue
                    inp = container.locator("input").first
                    if inp.count() == 0:
                        inp = container.locator("textarea").first
                    if inp.count() == 0:
                        continue
                    if not inp.is_visible(timeout=200):
                        continue

                    inp.click(timeout=500)
                    try:
                        inp.fill("", timeout=300)
                    except Exception:
                        pass

                    if is_autocomplete:
                        # autocomplete 用 type() 模擬鍵盤輸入，比 fill() 更能觸發 dropdown
                        inp.type(value, delay=30, timeout=2000)
                        page.wait_for_timeout(500)
                        menu_item = page.locator(
                            f".v-menu__content .v-list-item:has-text('{value}'), "
                            f".v-list-item:has-text('{value}')"
                        ).first
                        try:
                            if menu_item.count() > 0 and menu_item.is_visible(timeout=400):
                                menu_item.click(timeout=1500)
                                log.info("    - %r 已從 dropdown 選取", label)
                                return True
                        except Exception:
                            pass
                        try:
                            inp.press("Enter")
                            log.info("    - %r 已按 Enter 確認", label)
                        except Exception:
                            pass
                        return True
                    else:
                        inp.fill(value, timeout=1500)
                        log.info("    - %r 已填入", label)
                        return True
                except Exception as e:
                    log.debug("    - %s 失敗: %s", csel, e)
                    continue
        return False

    ok_name = _fill_in_modal(selectors.PARTICIPANT_FIELD_LABELS["name"], p.name)
    ok_id = _fill_in_modal(selectors.PARTICIPANT_FIELD_LABELS["id_number"], p.id_number)
    ok_nat = _fill_in_modal(selectors.PARTICIPANT_FIELD_LABELS["nationality"], p.nationality, is_autocomplete=True)

    if not (ok_name and ok_id and ok_nat):
        log.warning("  - 參加者 #%d 欄位填寫不完整 (name=%s, id=%s, nat=%s)",
                    idx, ok_name, ok_id, ok_nat)
        return False

    # Step 5：點 modal 內的「完成」按鈕
    page.wait_for_timeout(200)  # 等 disabled 狀態解除
    finish_btn = None
    for ft in selectors.FINISH_TEXTS:
        try:
            b = modal.get_by_role("button", name=ft).first
            if b.count() > 0 and b.is_visible(timeout=200):
                finish_btn = b
                break
        except Exception:
            continue

    if finish_btn is None:
        log.warning("  - 找不到「完成」按鈕")
        return False

    # 等按鈕 enable
    for _ in range(20):
        try:
            if finish_btn.is_enabled(timeout=200):
                break
        except Exception:
            pass
        page.wait_for_timeout(150)

    try:
        finish_btn.click(timeout=2000)
        log.info("  - 已點「完成」參加者 #%d", idx)
    except Exception as e:
        log.warning("  - 點「完成」失敗: %s", e)
        return False

    # 等 modal 關閉
    try:
        modal.wait_for(state="hidden", timeout=3000)
    except Exception:
        page.wait_for_timeout(500)
    return True


def tick_agreement(page: Page) -> None:
    """勾選同意條款。

    重要：絕不點擊同意文字本身，因為文字內含「會員服務條款」、「隱私條款」超連結，
    點到會開新分頁/modal。只點擊 checkbox 本身的 input 或視覺方塊。
    """
    log.info("勾選同意條款")

    # 策略 1：找包含同意文字的 v-input 容器，在容器內 .check() 真正的 input
    for text in selectors.AGREE_TEXTS:
        for container_sel in (
            f".v-input--checkbox:has-text('{text}')",
            f".v-input--selection-controls:has-text('{text}')",
            f".v-checkbox:has-text('{text}')",
            f".v-input:has-text('{text}')",
            f"div:has(> label:has-text('{text}'))",
        ):
            container = page.locator(container_sel).first
            try:
                if container.count() == 0:
                    continue
            except Exception:
                continue

            # 在容器內找 input[type=checkbox] 並用 force check（Vuetify input 通常 hidden）
            try:
                cb_input = container.locator("input[type='checkbox']").first
                if cb_input.count() > 0:
                    cb_input.check(force=True, timeout=2000)
                    log.info("  - 已勾選同意條款 (input[type=checkbox], container=%s)", container_sel)
                    return
            except Exception as e:
                log.debug("  - input.check failed: %s", e)

            # 視覺方塊：點 selection-controls__input 區塊（不會點到文字裡的超連結）
            for visual_sel in (
                ".v-input--selection-controls__input",
                ".v-selection-control__input",
                ".v-input--checkbox__input",
                ".v-input__control .v-icon",
            ):
                try:
                    visual = container.locator(visual_sel).first
                    if visual.count() > 0 and visual.is_visible(timeout=200):
                        visual.click(timeout=2000)
                        log.info("  - 已勾選同意條款 (click %s)", visual_sel)
                        return
                except Exception as e:
                    log.debug("  - visual click %s failed: %s", visual_sel, e)
                    continue

    # 策略 2：頁面第一個未勾選的 checkbox（不靠文字定位）
    try:
        all_inputs = page.locator("input[type='checkbox']")
        for i in range(all_inputs.count()):
            inp = all_inputs.nth(i)
            try:
                if not inp.is_checked():
                    inp.check(force=True, timeout=1000)
                    log.info("  - 已勾選 (fallback: 第 %d 個 input)", i)
                    return
            except Exception:
                continue
    except Exception as e:
        log.debug("agree fallback failed: %s", e)

    _screenshot(page, "agree-failed")
    raise FlowError("找不到同意條款的 checkbox")


_RADIO_CONTAINER_SELECTORS = (
    ".v-radio",
    ".v-input--radio",
    ".v-selection-control",  # Vuetify 3
    "[role='radio']",
)


def _click_radio_with_text(page: Page, texts: list[str], label_for_log: str, timeout: float = 8.0) -> bool:
    """迭代頁面上所有 radio 容器，挑 inner_text 包含關鍵字的一個並點擊。

    Vuetify 把點擊事件綁在 .v-radio 容器上，所以要點整個容器，不能只點到 inner span。
    """
    log.info("尋找 %s（候選文字 %s）", label_for_log, texts)
    deadline = time.time() + timeout

    # 先等任一 radio 容器出現
    try:
        union = ", ".join(_RADIO_CONTAINER_SELECTORS)
        page.locator(union).first.wait_for(state="visible", timeout=int(timeout * 1000))
    except Exception:
        log.warning("  - %s: 頁面沒有任何 radio 容器出現", label_for_log)
        return False

    debug_printed = False
    log_counter = 0
    while time.time() < deadline:
        log_counter += 1
        for sel in _RADIO_CONTAINER_SELECTORS:
            radios = page.locator(sel)
            try:
                n = radios.count()
            except Exception:
                n = 0
            if n == 0:
                continue
            if log_counter == 1:
                log.info("  - 用 %s 找到 %d 個容器", sel, n)
            for i in range(n):
                r = radios.nth(i)
                try:
                    if not r.is_visible(timeout=100):
                        continue
                    inner = r.inner_text(timeout=300) or ""
                except Exception:
                    continue

                if log_counter == 1 and not debug_printed and sel == ".v-radio":
                    log.info("    radio[%d].inner_text=%r", i, inner[:120])
                    if i == n - 1:
                        debug_printed = True

                for text in texts:
                    if text in inner:
                        try:
                            r.scroll_into_view_if_needed(timeout=500)
                        except Exception:
                            pass
                        # 按精準度試多種 click target
                        # 1) Vuetify 2: .v-input--selection-controls__input（綁 @click 的 wrapper）
                        # 2) Vuetify 3: .v-selection-control__wrapper
                        # 3) .v-input--selection-controls__ripple（視覺圓圈）
                        # 4) input[type=radio] + check（最後手段，可能不觸發 Vuetify v-model）
                        click_targets = (
                            ".v-input--selection-controls__input",
                            ".v-selection-control__wrapper",
                            ".v-input--selection-controls__ripple",
                            "label",
                        )
                        for ct in click_targets:
                            try:
                                t = r.locator(ct).first
                                if t.count() > 0 and t.is_visible(timeout=150):
                                    t.click(timeout=1500)
                                    log.info(
                                        "  - 已選擇 %s (selector=%s, idx=%d, matched=%r, method=click(%s))",
                                        label_for_log, sel, i, text, ct,
                                    )
                                    return True
                            except Exception as e:
                                log.debug("  - click(%s) idx=%d 失敗: %s", ct, i, e)
                                continue
                        # 最終 fallback：input.check
                        try:
                            inp = r.locator("input[type='radio']").first
                            if inp.count() > 0:
                                inp.check(force=True, timeout=2000)
                                log.info(
                                    "  - 已選擇 %s (selector=%s, idx=%d, matched=%r, method=input.check)",
                                    label_for_log, sel, i, text,
                                )
                                return True
                        except Exception as e:
                            log.warning("  - 所有點擊方式都失敗 idx=%d: %s", i, e)

        # role=radio fallback
        for text in texts:
            try:
                r = page.get_by_role("radio", name=text).first
                if r.count() > 0 and r.is_visible(timeout=100):
                    r.check(force=True, timeout=2000)
                    log.info("  - 已選擇 %s (role=radio name=%r)", label_for_log, text)
                    return True
            except Exception as e:
                log.debug("  - role=radio name=%r 失敗: %s", text, e)
                continue

        time.sleep(0.3)
    return False


def select_pickup(page: Page, pickup: str) -> None:
    log.info("選擇取票方式: %s", pickup)
    labels = selectors.PICKUP_LABELS.get(pickup, [pickup])
    if not _click_radio_with_text(page, labels, f"取票方式={pickup}", timeout=3.0):
        _screenshot(page, "pickup-failed")
        raise FlowError(f"找不到取票方式: {pickup}")


def select_payment(page: Page, payment: str) -> None:
    log.info("選擇付款方式: %s", payment)
    labels = selectors.PAYMENT_LABELS.get(payment, [payment])
    if not _click_radio_with_text(page, labels, f"付款方式={payment}", timeout=3.0):
        _screenshot(page, "payment-failed")
        raise FlowError(f"找不到付款方式: {payment}")


def _dismiss_3d_confirm_if_present(page: Page) -> bool:
    """若信用卡 3D 驗證確認 popup 出現，按下「確定」。"""
    for text in ("3D 驗證", "3D驗證", "允許信用卡"):
        try:
            popup = page.get_by_text(text, exact=False).first
            if popup.is_visible(timeout=200):
                log.info("偵測到 3D 驗證確認 popup（%s）", text)
                for ok_text in ("確定", "確認", "OK"):
                    btn = page.get_by_role("button", name=ok_text).first
                    if btn.count() > 0 and btn.is_visible(timeout=200):
                        btn.click(timeout=1000)
                        log.info("  - 已按 %s", ok_text)
                        return True
        except Exception:
            continue
    return False


def click_go_to_payment(page: Page, timeout: float = 8.0) -> None:
    """點擊「前往付款」按鈕。"""
    # 點 radio 後給頁面一點時間 re-render
    page.wait_for_timeout(500)

    log.info("點擊「前往付款」")
    _screenshot(page, "before-go-to-payment")  # 點之前先存一張，方便除錯

    deadline = time.time() + timeout
    while time.time() < deadline:
        # 用 role=button 嚴格限定為按鈕（不會誤抓 footer/breadcrumb 文字）
        for text in selectors.GO_TO_PAYMENT_TEXTS:
            try:
                btn = page.get_by_role("button", name=text).first
                if btn.count() > 0 and btn.is_visible(timeout=200):
                    if not btn.is_enabled(timeout=200):
                        log.info("  - 找到「%s」按鈕但目前 disabled，等狀態變化", text)
                        break  # 跳到外層 sleep 後重試
                    btn.scroll_into_view_if_needed(timeout=500)
                    btn.click(timeout=2000)
                    log.info("  - 已點擊「%s」（role=button）", text)
                    return
            except Exception as e:
                log.debug("  - role=button name=%r 失敗: %s", text, e)
                continue
        time.sleep(0.2)

    _screenshot(page, "go-to-payment-not-found")
    raise FlowError("找不到/無法點擊「前往付款」按鈕")


def run(page: Page, prefs: Preferences, event_url: str) -> None:
    """完整搶票流程。"""
    goto_event(page, event_url)

    # Step A: 點立即購買直到票區 modal 出現
    click_buy_now_until_modal(page, session_keyword=prefs.session_keyword)

    # Step B: 選票區 + 張數 + 選位方式
    select_zone_and_set_count(page, prefs.zone_priority, prefs.ticket_count)
    choose_allocation(page, prefs.seat_allocation)

    # Step C: 可能的圖形驗證碼
    wait_for_captcha_if_present(page)

    # Step D: 下一步 → 可能進入「確認選位結果」中間頁，再到填寫資料頁
    click_next(page)
    navigate_to_data_stage(page, timeout=60.0)

    # Step F: 填寫參加者資訊（若實名制）
    fill_participants(page, prefs.participants)

    # Step G: 勾同意條款
    tick_agreement(page)
    click_next(page)
    wait_for_next_stage(page, r"取票方式|付款方式", "付款結帳頁")

    # Step H: 付款結帳頁 — 取票方式 + 付款方式
    select_pickup(page, prefs.pickup)
    select_payment(page, prefs.payment)

    # Step I: 前往付款（使用者接手 3D 驗證）
    click_go_to_payment(page)
    _screenshot(page, "submitted")
    log.info("已送出訂單，請於瀏覽器完成 3D 驗證")
