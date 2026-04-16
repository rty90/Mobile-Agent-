from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, Optional


def _parse_hour_minute(text: str) -> Optional[Dict[str, int]]:
    english_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.IGNORECASE)
    if english_match:
        hour = int(english_match.group(1))
        minute = int(english_match.group(2) or 0)
        meridiem = english_match.group(3).lower()

        if hour == 12:
            hour = 0
        if meridiem == "pm":
            hour += 12
        return {"hour": hour, "minute": minute}

    chinese_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*点(半)?", text)
    if not chinese_match:
        return None

    hour = int(chinese_match.group(1))
    minute = int(chinese_match.group(2) or 0)
    if chinese_match.group(3):
        minute = 30
    return {"hour": hour, "minute": minute}


def parse_reminder_task(
    task_text: str,
    explicit_title: Optional[str] = None,
    explicit_time: Optional[str] = None,
    reference_now: Optional[datetime] = None,
) -> Dict[str, Optional[object]]:
    now = reference_now or datetime.now()
    normalized = task_text.strip()
    lower = normalized.lower()

    title = explicit_title
    if not title:
        english_match = re.search(
            r"(?:create\s+(?:a\s+)?)?reminder(?:\s+for)?\s+(.+?)(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)|\s+tomorrow.*)?$",
            lower,
            re.IGNORECASE,
        )
        if english_match:
            title = english_match.group(1).strip()
    if not title:
        chinese_match = re.search(
            r"(?:创建|建立|新增|添加)?(?:一个)?(?:提醒|提醒事项|待办)(?:为|是|事项为)?\s*(.+?)(?:\s*(?:在|到)?\s*\d{1,2}(?::\d{2})?\s*(?:点|点半|am|pm)|\s*明天.*)?$",
            normalized,
        )
        if chinese_match:
            title = chinese_match.group(1).strip()
    if not title:
        title = normalized

    time_text = explicit_time
    if not time_text:
        english_time_match = re.search(
            r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
            lower,
            re.IGNORECASE,
        )
        if english_time_match:
            time_text = english_time_match.group(1).strip()
    if not time_text:
        chinese_time_match = re.search(r"(\d{1,2}(?::\d{2})?\s*点半?)", normalized)
        if chinese_time_match and ("提醒" in normalized or "待办" in normalized):
            time_text = chinese_time_match.group(1).strip()

    target_date = now.date()
    if "tomorrow" in lower or "明天" in normalized:
        target_date = (now + timedelta(days=1)).date()

    begin_time_ms = None
    parsed_time = _parse_hour_minute(time_text or "")
    if parsed_time:
        event_dt = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            parsed_time["hour"],
            parsed_time["minute"],
        )
        if "tomorrow" not in lower and "明天" not in normalized and event_dt <= now:
            event_dt += timedelta(days=1)
        begin_time_ms = int(event_dt.timestamp() * 1000)

    return {
        "title": title.strip(),
        "time_text": time_text,
        "begin_time_ms": begin_time_ms,
    }
