#!/usr/bin/env python3
"""單獨測試「選票區 + 設定張數」這一步。

預設模式：直接呼叫 production 的 flow.select_zone_and_set_count，
            依序試 zone_priority 中每個關鍵字，找到有票就點 + 設定張數。
診斷模式：對每個 keyword 列出多種 selector 各命中幾個，但不點擊。

用法：
    .venv/bin/python test_zone.py "URL"                       # 用 production flow 試預設 5 色
    .venv/bin/python test_zone.py URL --zones 搖滾 藍         # 自訂優先序
    .venv/bin/python test_zone.py URL --count 2               # 試 2 張
    .venv/bin/python test_zone.py URL --diagnose              # 只診斷不點擊
    .venv/bin/python test_zone.py URL --use-config            # 從 config.yaml 讀 zone_priority

瀏覽器會保留開啟，讓你 DevTools 檢查 DOM 與結果。
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from pathlib import Path

from snipe import browser, config, flow

DEFAULT_ZONES = ["搖滾", "藍", "紅", "黃", "紫"]


def diagnose(page, zones: list[str]) -> None:
    """對每個 keyword 列出多種 selector 各命中幾個。"""
    for keyword in zones:
        print()
        print(f"=== 嘗試 keyword: {keyword!r} ===")
        strategies = [
            ("button:has-text",            page.locator(f"button:has-text('{keyword}')")),
            ("[role=button]:has-text",     page.locator(f"[role='button']:has-text('{keyword}')")),
            (".v-card:has-text",           page.locator(f".v-card:has-text('{keyword}')")),
            (".v-list-item:has-text",      page.locator(f".v-list-item:has-text('{keyword}')")),
            ("get_by_text exact",          page.get_by_text(keyword, exact=True)),
            ("get_by_text partial",        page.get_by_text(keyword, exact=False)),
            ("get_by_role button",         page.get_by_role("button", name=keyword)),
            (".v-expansion-panel-header",
                page.locator(f".v-expansion-panel-header:has-text('{keyword}')")),
        ]
        for label, loc in strategies:
            try:
                n = loc.count()
            except Exception as e:
                print(f"  [{label:35}] error: {e}")
                continue
            print(f"  [{label:35}] 命中 {n} 個")
            for i in range(min(n, 3)):
                try:
                    t = loc.nth(i).inner_text(timeout=300)
                except Exception:
                    t = "(無法讀取)"
                print(f"      [{i}] {t[:80]!r}")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="測試選票區邏輯")
    parser.add_argument("url", help="選擇票種頁面的 URL")
    parser.add_argument("--zones", nargs="+", default=None,
                        help=f"票區優先序（空白分隔，預設 {' '.join(DEFAULT_ZONES)}）")
    parser.add_argument("--count", type=int, default=1, help="張數（預設 1）")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--state", type=Path, default=Path("state/storage_state.json"))
    parser.add_argument("--use-config", action="store_true",
                        help="從 config.yaml 讀 zone_priority 與 ticket_count")
    parser.add_argument("--diagnose", action="store_true",
                        help="只列出每個 selector 命中數，不執行 production flow")
    parser.add_argument("--buy-now", action="store_true",
                        help="先點擊「立即購買/尚未開賣/立即訂購」按鈕進入票區頁，再開始測試")
    args = parser.parse_args()

    # 決定 zones 與 count
    if args.use_config:
        try:
            cfg = config.load(args.config)
        except config.ConfigError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 2
        zones = cfg.preferences.zone_priority
        count = cfg.preferences.ticket_count
        print(f"[INFO] 從 {args.config} 讀取 zone_priority={zones}, ticket_count={count}")
    else:
        zones = args.zones if args.zones else DEFAULT_ZONES
        count = args.count

    print()
    print(f"[INFO] URL:    {args.url}")
    print(f"[INFO] zones:  {zones}")
    print(f"[INFO] count:  {count}")
    print(f"[INFO] mode:   {'diagnose' if args.diagnose else 'production flow'}")
    print()

    print("[INFO] 啟動瀏覽器…")
    p, browser_obj, context, page = browser.launch(args.state)

    exit_code = 0
    try:
        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)  # 給 SPA 時間 render

        if args.buy_now:
            PRE_SALE_TEXTS = ["立即購買", "尚未開賣", "立即訂購", "Buy Tickets Now"]
            print(f"[INFO] 等任一購票按鈕出現（最多 8s）…")
            try:
                union = ", ".join(f"button:has-text('{t}')" for t in PRE_SALE_TEXTS)
                page.locator(union).first.wait_for(state="visible", timeout=8000)
                print("[INFO] 購票按鈕已 render")
            except Exception:
                print("[WARN] 8s 內未偵測到購票按鈕")

            clicked = False
            for text in PRE_SALE_TEXTS:
                strategies = [
                    ("role=button name=", page.get_by_role("button", name=text)),
                    ("button:has-text",   page.locator(f"button:has-text('{text}')")),
                    ("button.v-btn:has-text", page.locator(f"button.v-btn:has-text('{text}')")),
                    (".v-btn:has-text",   page.locator(f".v-btn:has-text('{text}')")),
                ]
                for label, loc in strategies:
                    try:
                        n = loc.count()
                    except Exception as e:
                        print(f"  [{text!r:>20} / {label:24}] error: {e}")
                        continue
                    if n == 0:
                        continue
                    print(f"  [{text!r:>20} / {label:24}] 命中 {n} 個")
                    # 取第一個可見的 click
                    try:
                        target = loc.first
                        if not target.is_visible(timeout=200):
                            # 可能多個但第一個 hidden（例如 mobile/desktop 雙版本）
                            for i in range(n):
                                cand = loc.nth(i)
                                if cand.is_visible(timeout=200):
                                    target = cand
                                    break
                        target.scroll_into_view_if_needed(timeout=500)
                        target.click(timeout=2000, force=True)
                        print(f"  [{text!r} / {label}] ✓ 已點擊")
                        clicked = True
                        break
                    except Exception as e:
                        print(f"  [{text!r} / {label}] 點擊失敗: {e}")
                if clicked:
                    break
            if not clicked:
                print("[WARN] 沒找到/點不到購票按鈕，繼續嘗試 zone 選擇")
            page.wait_for_timeout(2000)  # 等頁面切換 + render

        # 診斷：確認到達票區頁
        if page.url != args.url:
            print(f"[WARN] 實際 URL 與輸入不同：{page.url}")
        else:
            print(f"[INFO] 實際 URL：{page.url}")
        try:
            page.locator(".v-expansion-panel-header").first.wait_for(state="visible", timeout=4000)
            n = page.locator(".v-expansion-panel-header").count()
            print(f"[INFO] 偵測到 {n} 個 .v-expansion-panel-header，看似已在票區頁")
        except Exception:
            print("[WARN] 4 秒內找不到 .v-expansion-panel-header，可能：")
            print("       (a) URL 中的 session token 已過期，被導向其他頁")
            print("       (b) 頁面尚未進到選擇票種階段（需先點立即購買）")
            print("       (c) 該活動使用不同 DOM 結構")
            try:
                shot = page.screenshot(full_page=True)
                from pathlib import Path as _P
                _P("logs").mkdir(exist_ok=True)
                from datetime import datetime as _dt
                p_ = f"logs/test-zone-page-state-{_dt.now().strftime('%Y%m%d-%H%M%S')}.png"
                with open(p_, "wb") as f:
                    f.write(shot)
                print(f"       已存截圖：{p_}")
            except Exception:
                pass

        if args.diagnose:
            diagnose(page, zones)
            print()
            print("[INFO] === 診斷完成 ===")
        else:
            print("[INFO] === 呼叫 flow.select_zone_and_set_count ===")
            try:
                matched = flow.select_zone_and_set_count(page, zones, count)
                print()
                print(f"[OK] 已選到票區: {matched!r}")
            except flow.FlowError as e:
                print()
                print(f"[ERROR] 選票區失敗: {e}", file=sys.stderr)
                exit_code = 1

        print()
        print("[INFO] 瀏覽器保留開啟。按 Enter 結束。")
        try:
            input()
        except KeyboardInterrupt:
            pass

    except Exception:
        traceback.print_exc()
        print("[INFO] 瀏覽器保留以便除錯，按 Enter 結束。")
        try:
            input()
        except KeyboardInterrupt:
            pass
        exit_code = 1
    finally:
        try:
            context.close()
            browser_obj.close()
        finally:
            p.stop()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
