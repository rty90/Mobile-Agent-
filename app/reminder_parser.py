from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, Optional


def _parse_hour_minute(text: str) -> Optional[Dict[str, int]]:
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.IGNORECASE)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3).lower()

    if hour == 12:
        hour = 0
    if meridiem == "pm":
        hour += 12
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
        match = re.search(
            r"(?:create\s+(?:a\s+)?)?reminder(?:\s+for)?\s+(.+?)(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)|\s+tomorrow.*)?$",
            lower,
            re.IGNORECASE,
        )
        if match:
            title = match.group(1).strip()
    if not title:
        chinese_match = re.search(r"提醒(?:事项)?(?:为|：)?(.+?)(?:明天.*|\d{1,2}点.*)?$", normalized)
        if chinese_match:
            title = chinese_match.group(1).strip()
    if not title:
        title = normalized

    time_text = explicit_time
    if not time_text:
        time_match = re.search(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", lower, re.IGNORECASE)
        if time_match:
            time_text = time_match.group(1).strip()

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
        if "tomorrow" not in lower and event_dt <= now:
            event_dt += timedelta(days=1)
        begin_time_ms = int(event_dt.timestamp() * 1000)

    return {
        "title": title.strip(),
        "time_text": time_text,
        "begin_time_ms": begin_time_ms,
    }

