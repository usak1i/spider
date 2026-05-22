#!/usr/bin/env python3
"""一次性登入工具：開啟瀏覽器讓使用者手動登入 ticketplus，並儲存 session。

使用方式:
    .venv/bin/python prep.py
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from snipe import browser

LOGIN_PAGE = "https://ticketplus.com.tw/"
DEFAULT_STATE_PATH = Path("state/storage_state.json")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="登入 ticketplus 並儲存 session")
    parser.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_STATE_PATH,
        help=f"storage_state 儲存路徑（預設 {DEFAULT_STATE_PATH}）",
    )
    args = parser.parse_args()

    # 不載入舊 state，讓使用者重新登入
    p, browser_obj, context, page = browser.launch(storage_state_path=None)

    try:
        page.goto(LOGIN_PAGE)
        print()
        print("=" * 60)
        print("請在開啟的瀏覽器中完成會員登入。")
        print("登入完成後回到本終端機，按 Enter 儲存 session。")
        print("（按 Ctrl+C 取消）")
        print("=" * 60)
        input()

        browser.save_storage_state(context, args.state)
        print(f"\n[OK] session 已儲存到 {args.state}")
        return 0
    except KeyboardInterrupt:
        print("\n[INFO] 已取消，未儲存 session", file=sys.stderr)
        return 130
    finally:
        context.close()
        browser_obj.close()
        p.stop()


if __name__ == "__main__":
    sys.exit(main())
