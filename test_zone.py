#!/usr/bin/env python3
"""單獨測試「找並點擊票區按鈕」。

直接餵選擇票種頁面的 URL，腳本會嘗試多種 selector 找到「搖滾」、「藍」之類的
按鈕並點擊。每個策略命中幾個會印出來，方便快速判斷哪個 selector 最穩。

用法：
    .venv/bin/python test_zone.py "https://ticketplus.com.tw/order/...選擇票種頁"
    .venv/bin/python test_zone.py URL --zones 搖滾 藍
    .venv/bin/python test_zone.py URL --zones 搖滾A     # 試特定子區
    .venv/bin/python test_zone.py URL --no-click       # 只列出命中數，不點擊

瀏覽器會保留開啟讓你 DevTools 檢查。
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from pathlib import Path

from snipe import browser, config


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="找並點擊票區按鈕")
    parser.add_argument("url", help="選擇票種頁面的 URL")
    parser.add_argument("--zones", nargs="+", default=["搖滾", "藍"],
                        help="要找的票區關鍵字（依優先序，預設 搖滾 藍）")
    parser.add_argument("--state", type=Path, default=Path("state/storage_state.json"),
                        help="storage_state 路徑")
    parser.add_argument("--no-click", action="store_true",
                        help="只列出每個策略命中幾個，不點擊")
    args = parser.parse_args()

    print()
    print(f"[INFO] URL:    {args.url}")
    print(f"[INFO] zones:  {args.zones}")
    print()

    print("[INFO] 啟動瀏覽器…")
    p, browser_obj, context, page = browser.launch(args.state)

    try:
        page.goto(args.url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)  # 給 SPA 時間 render

        for keyword in args.zones:
            print()
            print(f"=== 嘗試 keyword: {keyword!r} ===")

            # 各種候選 selector
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
                (".v-expansion-panel-content row",
                    page.locator(f".v-expansion-panel-content :has-text('{keyword}')")),
            ]

            best = None  # (label, locator, count)
            for label, loc in strategies:
                try:
                    n = loc.count()
                except Exception as e:
                    print(f"  [{label:35}] error: {e}")
                    continue
                print(f"  [{label:35}] 命中 {n} 個")
                if n > 0:
                    # 印出前 3 個元素的 inner_text 預覽
                    for i in range(min(n, 3)):
                        try:
                            t = loc.nth(i).inner_text(timeout=300)
                        except Exception:
                            t = "(無法讀取)"
                        print(f"      [{i}] {t[:80]!r}")
                if n > 0 and best is None:
                    best = (label, loc, n)

            if best is None:
                print(f"  [{keyword}] 所有策略都 0 個，跳過")
                continue

            if args.no_click:
                print(f"  [{keyword}] --no-click，不點擊")
                continue

            # 點第一個
            label, loc, n = best
            print(f"  [{keyword}] 用 {label} 點第一個（共 {n} 個候選）")
            try:
                target = loc.first
                target.scroll_into_view_if_needed(timeout=500)
                target.click(timeout=2000)
                print(f"  [{keyword}] ✓ 已點擊")
                # 點完先停一下，讓使用者觀察結果
                page.wait_for_timeout(800)
                break  # 點到第一個 keyword 就停（依優先序）
            except Exception as e:
                print(f"  [{keyword}] ✗ 點擊失敗: {e}")
                continue

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
        return 1
    finally:
        try:
            context.close()
            browser_obj.close()
        finally:
            p.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
