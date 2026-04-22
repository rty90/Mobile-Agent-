import tempfile
import unittest
from pathlib import Path

from app.memory import SQLiteMemory


class MemoryTests(unittest.TestCase):
    def test_memory_helpers_filter_by_task_type_and_contact_query(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            memory.upsert_contact("Dave Zhu", "+18059577464")
            memory.upsert_contact("Daisy", "+18050000000")
            memory.add_successful_trajectory(
                task_type="send_message",
                app="com.google.android.apps.messaging",
                intent="send hello",
                steps_summary="open_message_thread > tap",
                confidence=1.0,
                verified=True,
            )
            memory.add_failure_pattern(
                task_type="create_reminder",
                app="com.google.android.calendar",
                intent="create reminder",
                steps_summary="open_calendar_event > tap",
                confidence=0.6,
            )
            memory.add_successful_trajectory(
                task_type="send_message",
                app="com.google.android.apps.messaging",
                intent="unverified send",
                steps_summary="open_message_thread",
                confidence=0.2,
                verified=False,
            )

            contacts = memory.get_relevant_contacts("dave")
            successes = memory.get_relevant_successes(
                task_type="send_message",
                app="com.google.android.apps.messaging",
                limit=3,
            )
            failures = memory.get_relevant_failures(
                task_type="create_reminder",
                app="com.google.android.calendar",
                limit=3,
            )

        self.assertEqual(contacts[0]["contact_name"], "Dave Zhu")
        self.assertEqual(successes[0]["task_type"], "send_message")
        self.assertEqual(len(successes), 1)
        self.assertEqual(failures[0]["task_type"], "create_reminder")

    def test_ui_shortcut_roundtrip_and_visibility_filter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            memory.remember_ui_shortcut(
                task_type="guided_ui_task",
                app="com.google.android.keep",
                page="keep_home",
                intent="open keep and create a note",
                skill="tap",
                args={"target": "Create a note", "target_key": "new_note"},
                confidence=0.95,
            )

            matched = memory.find_ui_shortcut(
                task_type="guided_ui_task",
                app="com.google.android.keep",
                page="keep_home",
                intent="open keep and create a note",
                screen_summary={
                    "page": "keep_home",
                    "visible_text": ["Create a note"],
                    "possible_targets": [{"label": "Create a note", "clickable": True}],
                },
            )
            missing = memory.find_ui_shortcut(
                task_type="guided_ui_task",
                app="com.google.android.keep",
                page="keep_home",
                intent="open keep and create a note",
                screen_summary={
                    "page": "keep_home",
                    "visible_text": [],
                    "possible_targets": [],
                },
            )

        self.assertEqual(matched["skill"], "tap")
        self.assertEqual(matched["args"]["target_key"], "new_note")
        self.assertIsNone(missing)

    def test_ui_shortcut_tap_requires_clickable_visible_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            memory.remember_ui_shortcut(
                task_type="guided_ui_task",
                app="com.google.android.keep",
                page="keep_home",
                intent="open keep and create a note",
                skill="tap",
                args={
                    "target": "Keep Notes needs permission to send notifications for reminders",
                    "target_key": "android:id/message",
                },
                confidence=0.95,
            )

            matched = memory.find_ui_shortcut(
                task_type="guided_ui_task",
                app="com.google.android.keep",
                page="keep_home",
                intent="open keep and create a note",
                screen_summary={
                    "page": "keep_home",
                    "visible_text": [
                        "Keep Notes needs permission to send notifications for reminders",
                        "Cancel",
                    ],
                    "possible_targets": [
                        {
                            "label": "Keep Notes needs permission to send notifications for reminders",
                            "resource_id": "android:id/message",
                            "clickable": False,
                        },
                        {
                            "label": "Cancel",
                            "resource_id": "android:id/button2",
                            "clickable": True,
                        },
                    ],
                },
            )

        self.assertIsNone(matched)

    def test_ui_shortcut_rejects_new_note_alias_pointing_to_sort_notes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            memory.remember_ui_shortcut(
                task_type="guided_ui_task",
                app="com.google.android.keep",
                page="keep_home",
                intent="open keep and create a note",
                skill="tap",
                args={"target": "Sort notes", "target_key": "new_note", "prefer_fallback": True},
                confidence=0.75,
            )

            matched = memory.find_ui_shortcut(
                task_type="guided_ui_task",
                app="com.google.android.keep",
                page="keep_home",
                intent="open keep and create a note",
                screen_summary={
                    "page": "keep_home",
                    "visible_text": ["Sort notes", "Create a note"],
                    "possible_targets": [
                        {"label": "Sort notes", "resource_id": "menu_sort_order", "clickable": True},
                        {
                            "label": "Create a note",
                            "resource_id": "speed_dial_create_close_button",
                            "content_desc": "Create a note",
                            "clickable": True,
                        },
                    ],
                },
            )

        self.assertIsNone(matched)

    def test_ui_shortcut_short_text_target_does_not_match_existing_text_note(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            memory.remember_ui_shortcut(
                task_type="guided_ui_task",
                app="com.google.android.keep",
                page="keep_home",
                intent="open keep and create a note",
                skill="tap",
                args={"target": "Text"},
                confidence=0.95,
            )

            matched = memory.find_ui_shortcut(
                task_type="guided_ui_task",
                app="com.google.android.keep",
                page="keep_home",
                intent="open keep and create a note",
                screen_summary={
                    "page": "keep_home",
                    "visible_text": ["Text note. ZX-2048.", "Create a note"],
                    "possible_targets": [
                        {
                            "label": "Text note. ZX-2048.",
                            "resource_id": "com.google.android.keep:id/browse_text_note",
                            "clickable": True,
                        },
                        {
                            "label": "Create a note",
                            "resource_id": "com.google.android.keep:id/speed_dial_create_close_button",
                            "clickable": True,
                        },
                    ],
                },
            )

        self.assertIsNone(matched)


if __name__ == "__main__":
    unittest.main()
