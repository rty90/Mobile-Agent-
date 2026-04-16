from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class PageProfile(object):
    name: str
    keywords: Tuple[str, ...]
    app_hints: Tuple[str, ...] = field(default_factory=tuple)
    fallback_targets: Dict[str, Tuple[float, float]] = field(default_factory=dict)


@dataclass
class DemoMessageConfig(object):
    app_name: str
    package_name: str
    activity_name: Optional[str]
    contact_name: str
    phone_number: Optional[str]
    message_text: str
    notes_package_name: str
    calendar_package_name: str
    page_profiles: Dict[str, PageProfile]


def build_demo_message_config(
    contact_name: str = "Dave Zhu",
    phone_number: Optional[str] = None,
    message_text: str = "hello from emulator",
) -> DemoMessageConfig:
    return DemoMessageConfig(
        app_name="system_messages",
        package_name="com.google.android.apps.messaging",
        activity_name=None,
        contact_name=contact_name,
        phone_number=phone_number,
        message_text=message_text,
        notes_package_name="com.google.android.keep",
        calendar_package_name="com.google.android.calendar",
        page_profiles={
            "messages_home": PageProfile(
                name="messages_home",
                keywords=("messages", "start chat", "new conversation", "new chat"),
                app_hints=("com.google.android.apps.messaging",),
                fallback_targets={
                    "search": (0.90, 0.10),
                    "new_chat": (0.90, 0.90),
                },
            ),
            "messages_search": PageProfile(
                name="messages_search",
                keywords=("search", "conversation", "name", "phone number", "email"),
                app_hints=("com.google.android.apps.messaging",),
                fallback_targets={
                    "search": (0.50, 0.12),
                    "contact_result": (0.50, 0.26),
                },
            ),
            "message_thread": PageProfile(
                name="message_thread",
                keywords=("send", "message", "sms", "mms", "go back", "clear text"),
                app_hints=("com.google.android.apps.messaging",),
                fallback_targets={
                    "message_input": (0.42, 0.94),
                    "send": (0.92, 0.94),
                },
            ),
            "keep_home": PageProfile(
                name="keep_home",
                keywords=("keep", "notes", "take a note", "create a note", "new text note"),
                app_hints=("com.google.android.keep",),
                fallback_targets={
                    "new_note": (0.90, 0.93),
                    "new_text_note": (0.85, 0.86),
                },
            ),
            "keep_editor": PageProfile(
                name="keep_editor",
                keywords=("editing", "title", "note", "pin", "remind me"),
                app_hints=("com.google.android.keep",),
                fallback_targets={},
            ),
            "reminder_editor": PageProfile(
                name="reminder_editor",
                keywords=("save", "title", "event", "task", "birthday", "all-day"),
                app_hints=("com.google.android.calendar",),
                fallback_targets={
                    "save": (0.91, 0.09),
                },
            ),
            "reminder_saved": PageProfile(
                name="reminder_saved",
                keywords=(
                    "jump to today",
                    "open tasks",
                    "creation menu",
                    "open schedule view",
                    "signed in as",
                ),
                app_hints=("com.google.android.calendar",),
                fallback_targets={},
            ),
        },
    )


def scale_ratio_point(
    ratio_point: Tuple[float, float], screen_size: Tuple[int, int]
) -> Tuple[int, int]:
    width, height = screen_size
    return int(width * ratio_point[0]), int(height * ratio_point[1])
