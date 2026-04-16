from __future__ import annotations

from typing import Any, Dict, Optional

from app.screenshot_reader import read_screenshot_context


def build_page_bundle(
    screen_summary: Optional[Dict[str, Any]],
    screenshot_path: Optional[str],
) -> Dict[str, Any]:
    summary = screen_summary or {}
    return {
        "screen_summary": summary,
        "app": summary.get("app"),
        "page": summary.get("page"),
        "visible_text": list(summary.get("visible_text", [])),
        "possible_targets": list(summary.get("possible_targets", [])),
        "screenshot": read_screenshot_context(screenshot_path),
    }
