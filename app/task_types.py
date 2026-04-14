from __future__ import annotations

import re
from typing import Dict, Optional


TASK_SEND_MESSAGE = "send_message"
TASK_EXTRACT_AND_COPY = "extract_and_copy"
TASK_CREATE_REMINDER = "create_reminder"
TASK_UNSUPPORTED = "unsupported"


HIGH_RISK_KEYWORDS = (
    "payment",
    "wire transfer",
    "delete",
    "send email",
    "formal email",
    "official message",
    "正式邮件",
    "付款",
    "转账",
    "删除",
    "对外正式发送",
    "改别人日历",
)


def detect_task_type(task_text: str, override: Optional[str] = None) -> str:
    if override in (
        TASK_SEND_MESSAGE,
        TASK_EXTRACT_AND_COPY,
        TASK_CREATE_REMINDER,
        TASK_UNSUPPORTED,
    ):
        return override

    normalized = task_text.strip().lower()
    raw = task_text.strip()

    if (
        "send message" in normalized
        or ("send" in normalized and "message" in normalized)
        or "text " in normalized
        or "发消息" in raw
        or "发短信" in raw
    ):
        return TASK_SEND_MESSAGE

    if (
        "extract" in normalized
        or "copy" in normalized
        or "order number" in normalized
        or "check-in time" in normalized
        or "提取" in raw
        or "复制" in raw
    ):
        return TASK_EXTRACT_AND_COPY

    if (
        "reminder" in normalized
        or "todo" in normalized
        or "calendar" in normalized
        or "待办" in raw
        or "提醒" in raw
    ):
        return TASK_CREATE_REMINDER

    return TASK_UNSUPPORTED


def extract_contact_query(task_text: str) -> Optional[str]:
    patterns = (
        r"给(.+?)发(?:消息|短信)",
        r"to\s+(.+?)\s+(?:send|text)",
    )
    for pattern in patterns:
        match = re.search(pattern, task_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_message_body(task_text: str) -> Optional[str]:
    for pattern in (r'"([^"]+)"', r"“([^”]+)”", r"'([^']+)'"):
        match = re.search(pattern, task_text)
        if match:
            return match.group(1).strip()
    return None


def parse_extract_task(task_text: str) -> Dict[str, str]:
    normalized = task_text.lower()
    field_hint = "generic_value"
    if "order number" in normalized or "订单号" in task_text:
        field_hint = "order_number"
    elif "check-in time" in normalized or "入住时间" in task_text:
        field_hint = "check_in_time"

    target_app = "notes"
    if "keep" in normalized:
        target_app = "keep"
    elif "note" in normalized or "notes" in normalized or "备忘录" in task_text:
        target_app = "notes"

    return {
        "field_hint": field_hint,
        "target_app": target_app,
    }
