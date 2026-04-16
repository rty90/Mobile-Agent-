from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional


def read_screenshot_context(screenshot_path: Optional[str]) -> Dict[str, object]:
    if not screenshot_path:
        return {
            "available": False,
            "screenshot_path": None,
            "notes": "No screenshot path was provided.",
        }

    path = Path(screenshot_path)
    return {
        "available": path.exists(),
        "screenshot_path": str(path),
        "notes": "Screenshot OCR/vision is not enabled yet; path is provided for future backends.",
    }
