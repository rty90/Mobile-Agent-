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
            state = AgentState(
                current_app="com.google.android.apps.messaging",
                screen_summary={"page": "message_thread", "visible_text": ["Dave Zhu", "Send"]},
            )

            builder = ContextBuilder(memory=memory)
            context = builder.build(goal='send message to Dave Zhu "hello"', state=state)

        self.assertEqual(context["task_type"], "send_message")
        self.assertLessEqual(len(context["relevant_memories"]), 3)
        self.assertEqual(context["known_contact"]["contact_name"], "Dave Zhu")

    def test_context_builder_shaping_for_extract_omits_irrelevant_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            memory.add_successful_trajectory(
                task_type="extract_and_copy",
                app="com.google.android.keep",
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
        self.assertNotIn("known_contact", {k: v for k, v in context.items() if v})


if __name__ == "__main__":
    unittest.main()

