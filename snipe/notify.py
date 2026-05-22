from __future__ import annotations

import logging
import shlex
import subprocess

log = logging.getLogger(__name__)

SUCCESS_SOUND = "/System/Library/Sounds/Glass.aiff"
FAILURE_SOUND = "/System/Library/Sounds/Sosumi.aiff"


def _play(path: str, repeats: int = 1) -> None:
    for _ in range(repeats):
        try:
            subprocess.run(["afplay", path], check=False, timeout=5)
        except Exception as e:
            log.warning("afplay failed: %s", e)
            return


def _notify(title: str, message: str) -> None:
    safe_title = title.replace('"', "'")
    safe_msg = message.replace('"', "'")
    script = (
        f'display notification "{safe_msg}" with title "{safe_title}" sound name "Glass"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=5)
    except Exception as e:
        log.warning("osascript failed: %s", e)


def success(message: str = "搶票送出成功，請接手付款") -> None:
    _play(SUCCESS_SOUND, repeats=3)
    _notify("Ticket Plus", message)


def failure(reason: str) -> None:
    _play(FAILURE_SOUND, repeats=1)
    _notify("Ticket Plus 失敗", reason[:200])


def alert_captcha() -> None:
    _play(SUCCESS_SOUND, repeats=1)
    _notify("Ticket Plus", "請輸入驗證碼")
