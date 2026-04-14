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
        self.assertEqual(failures[0]["task_type"], "create_reminder")


if __name__ == "__main__":
    unittest.main()

