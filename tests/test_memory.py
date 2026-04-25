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

    def test_interaction_pattern_roundtrip_hydrates_search_query_for_focused_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            screen_summary = {
                "page": "messages_search",
                "visible_text": ["Search or type URL"],
                "possible_targets": [
                    {
                        "label": "Search or type URL",
                        "resource_id": "com.android.chrome:id/url_bar",
                        "class_name": "android.widget.EditText",
                        "clickable": True,
                        "focused": True,
                        "target_id": "n017",
                    }
                ],
            }
            remembered = memory.remember_interaction_pattern(
                task_type="guided_ui_task",
                app="com.android.chrome",
                page="messages_search",
                goal="open chrome, open bilibili, and find videos about llm",
                screen_summary=screen_summary,
                recent_actions=[{"action": "tap", "success": True, "detail": "Tapped target Search or type URL."}],
                skill="type_text",
                args={
                    "target_id": "n017",
                    "text": "bilibili llm",
                    "press_enter": True,
                },
                confidence=0.94,
            )
            matched = memory.find_interaction_pattern(
                task_type="guided_ui_task",
                app="com.android.chrome",
                page="messages_search",
                goal="open chrome, open bilibili, and find videos about llm",
                screen_summary=screen_summary,
                recent_actions=[{"action": "tap", "success": True, "detail": "Tapped target Search or type URL."}],
            )

        self.assertTrue(remembered)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["skill"], "type_text")
        self.assertEqual(matched["args"]["text"], "bilibili llm")
        self.assertEqual(matched["args"]["target_id"], "n017")
        self.assertTrue(matched["args"]["press_enter"])

    def test_clear_guided_ui_learning_removes_guided_ui_trajectories_and_patterns_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            memory.add_successful_trajectory(
                task_type="guided_ui_task",
                app="unknown",
                intent="open gmail",
                steps_summary="open_app > tap",
                confidence=1.0,
                verified=True,
            )
            memory.add_failure_pattern(
                task_type="guided_ui_task",
                app="unknown",
                intent="open chrome",
                steps_summary="tap > tap",
                confidence=0.4,
            )
            memory.add_manual_intervention_episode(
                task_type="guided_ui_task",
                app="unknown",
                page="messages_search",
                intent="open gmail",
                trigger_reason="looped on onboarding",
                resolution_label="dismiss_overlay",
                before_summary={"page": "messages_search"},
                after_summary={"page": "gmail_home"},
            )
            memory.add_manual_reflection(
                task_type="guided_ui_task",
                app="unknown",
                page="messages_search",
                intent="open gmail",
                trigger_reason="looped on onboarding",
                resolution_label="dismiss_overlay",
                failed_skill="tap",
                failed_args={"target": "OK"},
                agent_actions=[],
                before_summary={"page": "messages_search"},
                after_summary={"page": "gmail_home"},
                reflection={"observed_error": "looped", "should_auto_execute": False},
                confidence=0.9,
            )
            memory.remember_interaction_pattern(
                task_type="guided_ui_task",
                app="com.android.chrome",
                page="messages_search",
                goal="open chrome and search for llm",
                screen_summary={
                    "page": "messages_search",
                    "visible_text": ["Search or type URL"],
                    "possible_targets": [],
                },
                recent_actions=[],
                skill="type_text",
                args={"text": "llm"},
                confidence=0.9,
            )
            memory.add_successful_trajectory(
                task_type="send_message",
                app="com.google.android.apps.messaging",
                intent="send hello",
                steps_summary="open_message_thread > tap",
                confidence=1.0,
                verified=True,
            )
            memory.upsert_learned_procedure(
                task_type="guided_ui_task",
                app="unknown",
                intent="open gmail",
                title="filtered gmail procedure",
                procedure={
                    "steps": [
                        {"skill": "tap", "target": "TAKE ME TO GMAIL"},
                        {"skill": "tap", "target": "Allow"},
                    ],
                    "safety": {"auto_execute": False},
                },
                confidence=0.85,
                verified=True,
            )

            counts = memory.clear_guided_ui_learning()
            guided_successes = memory.get_relevant_successes(task_type="guided_ui_task", app="unknown", limit=5)
            send_successes = memory.get_relevant_successes(
                task_type="send_message",
                app="com.google.android.apps.messaging",
                limit=5,
            )
            interventions = memory.list_manual_interventions(limit=5)
            reflections = memory.list_manual_reflections(limit=5)

        self.assertEqual(counts["successful_trajectories"], 1)
        self.assertEqual(counts["failure_patterns"], 1)
        self.assertEqual(counts["manual_interventions"], 1)
        self.assertEqual(counts["manual_reflections"], 1)
        self.assertEqual(counts["interaction_patterns"], 1)
        self.assertEqual(counts["learned_procedures"], 1)
        self.assertEqual(guided_successes, [])
        self.assertEqual(len(send_successes), 1)
        self.assertEqual(interventions, [])
        self.assertEqual(reflections, [])

    def test_learned_procedures_are_retrievable_as_filtered_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            saved = memory.upsert_learned_procedure(
                task_type="guided_ui_task",
                app="com.google.android.gm",
                intent="open gmail and create a new email draft",
                title="filtered gmail compose procedure",
                procedure={
                    "steps": [
                        {"skill": "tap", "target": "TAKE ME TO GMAIL"},
                        {"skill": "tap", "target": "Allow"},
                        {"skill": "tap", "target": "Compose"},
                    ],
                    "stop_conditions": {"after_visible_text": ["Send", "From"]},
                    "safety": {"auto_execute": False, "raw_memory_filtered": True},
                },
                source_refs=[{"table": "manual_reflections", "id": 31}],
                confidence=0.88,
                verified=True,
            )
            results = memory.get_relevant_learned_procedures(
                task_type="guided_ui_task",
                app="com.google.android.gm",
                intent="open gmail and create a new email draft",
                limit=3,
            )

        self.assertTrue(saved)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "learned_procedure")
        self.assertIn("TAKE ME TO GMAIL", results[0]["steps_summary"])
        self.assertFalse(results[0]["procedure"]["safety"]["auto_execute"])


if __name__ == "__main__":
    unittest.main()
