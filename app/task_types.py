from __future__ import annotations

import re
from typing import Dict, Optional


TASK_SEND_MESSAGE = "send_message"
TASK_EXTRACT_AND_COPY = "extract_and_copy"
TASK_CREATE_REMINDER = "create_reminder"
TASK_READ_CURRENT_SCREEN = "read_current_screen"
TASK_GUIDED_UI_TASK = "guided_ui_task"
TASK_UNSUPPORTED = "unsupported"

SUPPORTED_TASK_TYPES = (
    TASK_SEND_MESSAGE,
    TASK_EXTRACT_AND_COPY,
    TASK_CREATE_REMINDER,
    TASK_READ_CURRENT_SCREEN,
    TASK_GUIDED_UI_TASK,
)


APP_ALIASES = {
    "messages": "com.google.android.apps.messaging",
    "message": "com.google.android.apps.messaging",
    "sms": "com.google.android.apps.messaging",
    "keep": "com.google.android.keep",
    "google keep": "com.google.android.keep",
    "notes": "com.google.android.keep",
    "calendar": "com.google.android.calendar",
    "reminder": "com.google.android.calendar",
    "chrome": "com.android.chrome",
    "settings": "com.android.settings",
    "gmail": "com.google.android.gm",
}

HIGH_RISK_KEYWORDS = (
    "payment",
    "pay",
    "wire transfer",
    "bank transfer",
    "delete",
    "remove permanently",
    "send email",
    "formal email",
    "official message",
    "付款",
    "转账",
    "删除",
    "正式邮件",
    "对外正式发送",
    "改别人日历",
)


def detect_task_type(task_text: str, override: Optional[str] = None) -> str:
    if override in SUPPORTED_TASK_TYPES + (TASK_UNSUPPORTED,):
        return override

    normalized = task_text.strip().lower()
    raw = task_text.strip()

    if (
        "send message" in normalized
        or ("send" in normalized and "message" in normalized)
        or ("text" in normalized and "message" in normalized)
        or "发消息" in raw
        or "发短信" in raw
        or "短信" in raw
    ):
        return TASK_SEND_MESSAGE

    if (
        "reminder" in normalized
        or "todo" in normalized
        or "calendar" in normalized
        or "待办" in raw
        or "提醒" in raw
    ):
        return TASK_CREATE_REMINDER

    if (
        ("extract" in normalized or "copy" in normalized)
        and ("note" in normalized or "notes" in normalized or "keep" in normalized)
    ) or ("提取" in raw and "复制" in raw):
        return TASK_EXTRACT_AND_COPY

    if _looks_like_guided_ui_task(normalized, raw):
        return TASK_GUIDED_UI_TASK

    if (
        "current screen" in normalized
        or "current page" in normalized
        or "this screen" in normalized
        or "this page" in normalized
        or "visible" in normalized
        or "当前页面" in raw
        or "当前屏幕" in raw
        or "可见" in raw
    ):
        return TASK_READ_CURRENT_SCREEN

    return TASK_UNSUPPORTED


def _looks_like_guided_ui_task(normalized: str, raw: str) -> bool:
    if "open " not in normalized and "打开" not in raw:
        return False
    if not any(alias in normalized for alias in APP_ALIASES):
        return False
    return (
        "inspect" in normalized
        or "summarize" in normalized
        or "tell me" in normalized
        or "read" in normalized
        or "what is on" in normalized
        or "看看" in raw
        or "读取" in raw
        or "看一下" in raw
    )


def is_supported_task_type(task_type: str) -> bool:
    return task_type in SUPPORTED_TASK_TYPES


def contains_high_risk_keyword(task_text: str) -> bool:
    lower_task = task_text.lower()
    raw_task = task_text.strip()
    return any(keyword.lower() in lower_task or keyword in raw_task for keyword in HIGH_RISK_KEYWORDS)


def is_formal_message(task_text: str) -> bool:
    lower_task = task_text.lower()
    raw_task = task_text.strip()
    return any(
        keyword in lower_task or keyword in raw_task
        for keyword in ("official", "formal", "professional", "正式", "对外")
    )


def extract_contact_query(task_text: str) -> Optional[str]:
    patterns = (
        r"给(.+?)(?:发(?:消息|短信))",
        r"send\s+message\s+to\s+(.+?)(?:\s+['\"]|$)",
        r"text\s+(.+?)(?:\s+['\"]|$)",
        r"to\s+(.+?)\s+(?:send|text)",
    )
    for pattern in patterns:
        match = re.search(pattern, task_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_message_body(task_text: str) -> Optional[str]:
    for pattern in (r'"([^"]+)"', r"'([^']+)'", r"“([^”]+)”"):
        match = re.search(pattern, task_text)
        if match:
            return match.group(1).strip()
    return None


def parse_extract_task(task_text: str) -> Dict[str, str]:
    normalized = task_text.lower()
    field_hint = "generic_value"
    if "order number" in normalized or "订单号" in task_text:
        field_hint = "order_number"
    elif (
        "check-in time" in normalized
        or "check in time" in normalized
        or "入住时间" in task_text
    ):
        field_hint = "check_in_time"

    target_app = "notes"
    if "google keep" in normalized or "keep" in normalized:
        target_app = "keep"
    elif "note" in normalized or "notes" in normalized or "备忘" in task_text:
        target_app = "notes"

    return {
        "field_hint": field_hint,
        "target_app": target_app,
        "target_package": "com.google.android.keep",
        "target_home_page": "keep_home",
        "target_entry_target": "take a note",
        "target_entry_key": "new_note",
        "target_editor_page": "keep_editor",
    }


def parse_screen_read_task(task_text: str) -> Dict[str, Optional[str]]:
    normalized = task_text.lower()
    field_hint = None
    if "order number" in normalized or "订单号" in task_text:
        field_hint = "order_number"
    elif "check-in time" in normalized or "check in time" in normalized or "入住时间" in task_text:
        field_hint = "check_in_time"

    summary_style = "summary"
    if "extract" in normalized or "提取" in task_text:
        summary_style = "extract"

    return {
        "field_hint": field_hint,
        "summary_style": summary_style,
    }


def parse_guided_ui_task(task_text: str) -> Dict[str, Optional[str]]:
    normalized = task_text.lower()
    target_alias = None
    target_package = None
    for alias, package_name in APP_ALIASES.items():
        if alias in normalized:
            target_alias = alias
            target_package = package_name
            break

    return {
        "target_alias": target_alias,
        "target_package": target_package,
    }
