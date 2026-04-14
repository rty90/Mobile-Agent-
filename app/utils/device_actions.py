from __future__ import annotations

import time
from typing import Optional

from app.utils.adb import ADBClient


class DeviceActions(object):
    """Compatibility wrapper for manual smoke tests."""

    def __init__(self, adb: Optional[ADBClient] = None) -> None:
        self.adb = adb or ADBClient()

    def ensure_device(self, timeout: int = 10) -> None:
        self.adb.ensure_device(timeout=timeout)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def home(self) -> None:
        self.adb.home()

    def back(self) -> None:
        self.adb.back()

    def recent_apps(self) -> None:
        self.adb.keyevent(187)

    def enter(self) -> None:
        self.adb.keyevent(66)

    def tap(self, x: int, y: int, delay: float = 0.5) -> None:
        self.adb.tap(x, y)
        if delay:
            time.sleep(delay)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
        delay: float = 0.5,
    ) -> None:
        self.adb.swipe(x1, y1, x2, y2, duration_ms)
        if delay:
            time.sleep(delay)

    def input_text(self, text: str, delay: float = 0.5) -> None:
        self.adb.input_text(text)
        if delay:
            time.sleep(delay)

    def open_app_by_monkey(self, package_name: str, delay: float = 1.5) -> None:
        self.adb.open_app(package_name=package_name, wait_time=delay)

    def open_chrome(self, delay: float = 1.5) -> None:
        self.open_app_by_monkey("com.android.chrome", delay=delay)

    def open_settings(self, delay: float = 1.5) -> None:
        self.open_app_by_monkey("com.android.settings", delay=delay)

    def screenshot(self, save_to: str) -> str:
        return str(self.adb.screenshot(save_to))

    def current_focus(self) -> str:
        return self.adb.get_current_focus()

    def screen_size(self) -> str:
        width, height = self.adb.get_screen_size()
        return "{0}x{1}".format(width, height)
