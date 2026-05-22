#!/usr/bin/env python3
"""Ticket Plus 遠大售票 搶票主程式。

使用方式:
    .venv/bin/python snipe.py [--config config.yaml] [--dry-run] [--url URL]

--dry-run: 不倒數，直接進入流程（用來演練 selector）
--url:     覆寫 config 中的 event.url（用來測試其他場次）
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from snipe import browser, config, flow, notify, timer


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Ticket Plus 搶票腳本")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--dry-run", action="store_true",
                        help="不倒數，直接執行（用來測試 selector）")
    parser.add_argument("--url", type=str, default=None,
                        help="覆寫 config 的 event.url")
    args = parser.parse_args()

    try:
        cfg = config.load(args.config)
    except config.ConfigError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    event_url = args.url or cfg.event.url

    if not args.dry_run:
        offset = timer.sync_ntp()
        print(f"[INFO] NTP 時差: {offset:+.3f} 秒")
        print(f"[INFO] 開賣時間: {cfg.event.sale_time.isoformat()}")
        print(f"[INFO] 提前 {cfg.lead_seconds} 秒進入訂購頁\n")
        try:
            timer.sleep_until(cfg.event.sale_time, cfg.lead_seconds, offset=offset)
        except KeyboardInterrupt:
            print("\n[INFO] 倒數已中斷")
            return 130
        print()  # 換行

    print("[INFO] 啟動瀏覽器…")
    p, browser_obj, context, page = browser.launch(cfg.state.storage_state_path)

    exit_code = 0
    try:
        flow.run(page, cfg.preferences, event_url)
        notify.success()
        print("\n[OK] 流程完成，請於瀏覽器完成 3D 驗證 / 付款。")
        print("    瀏覽器將保持開啟，完成後請按 Enter 結束本程式。")
        try:
            input()
        except KeyboardInterrupt:
            pass
    except flow.FlowError as e:
        msg = str(e)
        print(f"\n[ERROR] 流程中斷: {msg}", file=sys.stderr)
        notify.failure(msg)
        exit_code = 1
        # 失敗時也保留瀏覽器，方便人工接手
        print("[INFO] 瀏覽器將保持開啟以便人工接手，按 Enter 結束。")
        try:
            input()
        except KeyboardInterrupt:
            pass
    except Exception as e:
        traceback.print_exc()
        notify.failure(f"未預期錯誤: {e}")
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
