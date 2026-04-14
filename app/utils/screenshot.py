from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from app.utils.adb import ADBClient


def make_screenshot_name(prefix: str = "shot") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return "{0}_{1}.png".format(prefix, timestamp)


def sanitize_path_component(value: str) -> str:
    sanitized = []
    for char in value:
        if char.isalnum() or char in ("-", "_"):
            sanitized.append(char)
        elif char.isspace():
            sanitized.append("_")
        else:
            sanitized.append("_")
    cleaned = "".join(sanitized).strip("_")
    return cleaned or "task"


class ScreenshotManager(object):
    """Manage stable screenshot paths grouped by task."""

    def __init__(self, base_dir: str = "data/screenshots") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def build_path(self, task_name: Optional[str] = None, prefix: str = "shot") -> Path:
        save_dir = self.base_dir / sanitize_path_component(task_name) if task_name else self.base_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir / make_screenshot_name(prefix=prefix)

    def capture(
        self,
        adb_client: ADBClient,
        task_name: Optional[str] = None,
        prefix: str = "shot",
    ) -> Path:
        path = self.build_path(task_name=task_name, prefix=prefix)
        return adb_client.screenshot(str(path))
