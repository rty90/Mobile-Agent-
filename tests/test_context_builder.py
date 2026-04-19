import tempfile
import unittest
from pathlib import Path

from app.context_builder import ContextBuilder
from app.memory import SQLiteMemory
from app.state import AgentState


class ContextBuilderTests(unittest.TestCase):
    def test_context_builder_limits_memories_and_prioritizes_message_contact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            for index in range(4):
                memory.add_successful_trajectory(
                    task_type="send_message",
                    app="com.google.android.apps.messaging",
                    intent="send hello {0}".format(index),
                    steps_summary="open_message_thread > tap",
                    confidence=0.9 - index * 0.1,
                    verified=True,
                )
            memory.upsert_contact("Dave Zhu", "+18059577464")
            memory.upsert_contact("Daisy", "+18050000000")
            state = AgentState(
                current_app="com.google.android.apps.messaging",
                screen_summary={"page": "message_thread", "visible_text": ["Dave Zhu", "Send"]},
            )

            builder = ContextBuilder(memory=memory)
            context = builder.build(goal='send message to Dave Zhu "hello"', state=state)

        self.assertEqual(context["task_type"], "send_message")
        self.assertLessEqual(len(context["relevant_memories"]), 3)
        self.assertLessEqual(len(context["recent_actions"]), 2)
        self.assertEqual(context["remembered_contacts"][0]["contact_name"], "Dave Zhu")

    def test_context_builder_shaping_for_extract_omits_irrelevant_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            memory.add_successful_trajectory(
                task_type="extract_and_copy",
                app="com.android.chrome",
                intent="extract order number",
                steps_summary="read_screen > extract_value > open_app",
                confidence=0.95,
                verified=True,
            )
            memory.add_failure_pattern(
                task_type="send_message",
                app="com.google.android.apps.messaging",
                intent="send hello",
                steps_summary="open_message_thread > tap",
                confidence=0.5,
            )
            state = AgentState(
                current_app="com.android.chrome",
                screen_summary={
                    "page": "booking_page",
                    "visible_text": ["Order number: ZX-2048", "Hotel check-in time: 7pm", "Other text"],
                },
            )
            state.remember_artifact("extracted_value", "ZX-2048")

            builder = ContextBuilder(memory=memory)
            context = builder.build(
                goal="extract the order number and copy it into notes",
                state=state,
            )

        self.assertEqual(context["task_type"], "extract_and_copy")
        self.assertEqual(context["extracted_value"], "ZX-2048")
        self.assertEqual(context["target_app_hint"], "notes")
        self.assertEqual(len(context["visible_text_excerpt"]), 3)
        self.assertNotIn("remembered_contacts", context)
        self.assertTrue(all(item.get("task_type") == "extract_and_copy" for item in context["relevant_memories"]))

    def test_context_builder_for_reminder_adds_parsed_fact_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            memory.add_successful_trajectory(
                task_type="create_reminder",
                app="com.google.android.calendar",
                intent="create reminder buy milk",
                steps_summary="open_calendar_event > tap",
                confidence=0.9,
                verified=True,
            )
            state = AgentState(
                current_app="com.google.android.calendar",
                screen_summary={"page": "reminder_editor", "visible_text": ["Save", "Title"]},
            )
            builder = ContextBuilder(memory=memory)
            context = builder.build("create a reminder for buy milk at 7pm", state=state)

        self.assertIn("parsed_reminder", context)
        self.assertNotIn("remembered_contacts", context)
        self.assertNotIn("target_app_hint", context)

    def test_context_builder_for_read_current_screen_adds_visible_text_and_field_hint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            memory.add_successful_trajectory(
                task_type="read_current_screen",
                app="com.android.chrome",
                intent="read current screen",
                steps_summary="read_screen > reason_about_page",
                confidence=0.9,
                verified=True,
            )
            state = AgentState(
                current_app="com.android.chrome",
                screen_summary={
                    "page": "booking_page",
                    "visible_text": ["Order number: ZX-2048", "Status: Ready", "Other text"],
                    "possible_targets": [
                        {"label": "Refresh", "clickable": True, "confidence": 0.9},
                    ],
                },
            )
            builder = ContextBuilder(memory=memory)
            context = builder.build(
                "extract the visible order number from the current page",
                state=state,
                task_type="read_current_screen",
            )

        self.assertEqual(context["field_hint"], "order_number")
        self.assertEqual(context["visible_text_excerpt"][0], "Order number: ZX-2048")
        self.assertEqual(context["top_targets"][0]["label"], "Refresh")

    def test_context_builder_for_guided_ui_task_adds_target_app_hint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            memory.add_successful_trajectory(
                task_type="guided_ui_task",
                app="com.google.android.keep",
                intent="open keep and inspect",
                steps_summary="open_app > read_screen > reason_about_page",
                confidence=0.9,
                verified=True,
            )
            memory.remember_ui_shortcut(
                task_type="guided_ui_task",
                app="com.google.android.keep",
                page="keep_home",
                intent="open keep and tell me what is on the current page",
                skill="tap",
                args={"target": "Take a note", "target_key": "new_note"},
                confidence=0.97,
            )
            state = AgentState(
                current_app="com.google.android.keep",
                screen_summary={
                    "page": "keep_home",
                    "visible_text": ["Take a note"],
                    "possible_targets": [{"label": "Take a note", "clickable": True, "confidence": 0.9}],
                },
            )
            builder = ContextBuilder(memory=memory)
            context = builder.build(
                "open keep and tell me what is on the current page",
                state=state,
                task_type="guided_ui_task",
            )

        self.assertEqual(context["target_app_hint"], "keep")
        self.assertEqual(len(context["relevant_memories"]), 1)
        self.assertEqual(context["ui_shortcut"]["skill"], "tap")


if __name__ == "__main__":
    unittest.main()
