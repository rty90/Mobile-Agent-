import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from app.demo_config import build_demo_message_config
from app.executor import Executor
from app.memory import SQLiteMemory
from app.planner import RuleBasedPlanner
from app.skills import build_skill_registry
from app.state import AgentState
from app.utils.logger import setup_logger
from app.utils.screenshot import ScreenshotManager


THREAD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="Go back" resource-id="back_button" content-desc="Go back" clickable="true" bounds="[60,180][204,324]" class="android.widget.ImageButton" />
  <node text="Message" resource-id="message_input" content-desc="" clickable="true" bounds="[80,2080][820,2200]" class="android.widget.EditText" />
  <node text="Send" resource-id="send_button" content-desc="Send SMS" clickable="true" bounds="[930,2060][1060,2200]" class="android.widget.ImageButton" />
</hierarchy>
"""

BOOKING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="Order number: ZX-2048" resource-id="order_number" content-desc="" clickable="false" bounds="[80,220][900,320]" class="android.widget.TextView" />
  <node text="Hotel check-in time: 7pm" resource-id="check_in_time" content-desc="" clickable="false" bounds="[80,360][900,460]" class="android.widget.TextView" />
</hierarchy>
"""

KEEP_HOME_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="Take a note" resource-id="new_note" content-desc="Take a note" clickable="true" bounds="[360,2080][720,2240]" class="android.widget.Button" />
</hierarchy>
"""

KEEP_EDITOR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="Editing note" resource-id="note_editor" content-desc="" clickable="true" bounds="[80,240][1000,1800]" class="android.widget.EditText" />
</hierarchy>
"""

REMINDER_EDITOR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="Calendar" resource-id="calendar_title" content-desc="" clickable="false" bounds="[80,140][360,220]" class="android.widget.TextView" />
  <node text="Save" resource-id="save_button" content-desc="Save" clickable="true" bounds="[900,120][1050,220]" class="android.widget.Button" />
</hierarchy>
"""

REMINDER_SAVED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="Buy milk" resource-id="event_title" content-desc="" clickable="false" bounds="[80,240][700,320]" class="android.widget.TextView" />
</hierarchy>
"""

MISSING_SEND_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="Go back" resource-id="back_button" content-desc="Go back" clickable="true" bounds="[60,180][204,324]" class="android.widget.ImageButton" />
</hierarchy>
"""


class MockADB(object):
    def __init__(self, xml_map, initial_screen="message_thread"):
        self.xml_map = xml_map
        self.current_screen = initial_screen
        self.device_id = "emulator-5554"
        self.input_history = []
        self.intent_history = []
        self.calendar_history = []

    def get_screen_size(self):
        return (1080, 2400)

    def dump_ui_xml(self, local_path):
        path = Path(local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.xml_map[self.current_screen], encoding="utf-8")
        return path

    def get_current_focus(self):
        screen_to_focus = {
            "message_thread": "mCurrentFocus=Window{123 u0 com.google.android.apps.messaging/.ui.conversation.ConversationActivity}",
            "booking_page": "mCurrentFocus=Window{123 u0 com.android.chrome/.Main}",
            "keep_home": "mCurrentFocus=Window{123 u0 com.google.android.keep/.activities.BrowseActivity}",
            "keep_editor": "mCurrentFocus=Window{123 u0 com.google.android.keep/.activities.NoteActivity}",
            "reminder_editor": "mCurrentFocus=Window{123 u0 com.google.android.calendar/.event.EditEventActivity}",
            "reminder_saved": "mCurrentFocus=Window{123 u0 com.google.android.calendar/.AllInOneActivity}",
        }
        return screen_to_focus[self.current_screen]

    def screenshot(self, save_path):
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mock")
        return path

    def force_stop_app(self, package_name):
        return None

    def start_sendto_intent(self, phone_number, body=None, wait_time=1.0):
        self.intent_history.append({"phone_number": phone_number, "body": body})
        self.current_screen = "message_thread"

    def start_calendar_event_intent(self, title, begin_time_ms=None, package_name=None, wait_time=1.0):
        self.calendar_history.append(
            {
                "title": title,
                "begin_time_ms": begin_time_ms,
                "package_name": package_name,
            }
        )
        self.current_screen = "reminder_editor"

    def open_app(self, package_name, activity_name=None, wait_time=1.0):
        if package_name == "com.google.android.keep":
            self.current_screen = "keep_home"

    def tap(self, x, y):
        if self.current_screen == "keep_home":
            self.current_screen = "keep_editor"
        elif self.current_screen == "reminder_editor":
            self.current_screen = "reminder_saved"
        return None

    def input_text(self, text):
        self.input_history.append(text)

    def keyevent(self, key_code):
        return None

    def back(self):
        return None


class ExecutorTests(unittest.TestCase):
    def _build_memory(self, name):
        db_dir = Path("tmp/test_dbs")
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / name
        if db_path.exists():
            db_path.unlink()
        return SQLiteMemory(db_path=str(db_path))

    def _build_executor(self, adb, memory, logger_name):
        logger = setup_logger(name=logger_name)
        state = AgentState()
        screenshot_manager = ScreenshotManager(base_dir="data/screenshots/test")
        executor = Executor(
            adb=adb,
            state=state,
            logger=logger,
            screenshot_manager=screenshot_manager,
            skill_registry=build_skill_registry(),
            memory=memory,
            runtime_config=build_demo_message_config(
                contact_name="Dave Zhu",
                phone_number="+18059577464",
                message_text="hello from emulator",
            ),
        )
        return executor, state

    def test_successful_message_flow_records_success_memory(self):
        adb = MockADB({"message_thread": THREAD_XML})
        memory = self._build_memory("executor_success_message.db")
        executor, _state = self._build_executor(adb, memory, "test-agent-success-message")
        planner = RuleBasedPlanner(
            demo_config=build_demo_message_config(
                contact_name="Dave Zhu",
                phone_number="+18059577464",
                message_text="hello from emulator",
            )
        )
        plan = planner.create_demo_message_plan()

        with mock.patch("builtins.input", return_value="y"):
            result = executor.execute_plan(plan)

        self.assertTrue(result["success"])
        self.assertEqual(result["task_type"], "send_message")
        self.assertEqual(adb.intent_history[0]["phone_number"], "+18059577464")

        with sqlite3.connect(str(Path("tmp/test_dbs/executor_success_message.db"))) as conn:
            task_type = conn.execute(
                "SELECT task_type FROM successful_trajectories LIMIT 1"
            ).fetchone()[0]
        self.assertEqual(task_type, "send_message")

    def test_extract_and_copy_flow_uses_extracted_artifact(self):
        adb = MockADB(
            {
                "booking_page": BOOKING_XML,
                "keep_home": KEEP_HOME_XML,
                "keep_editor": KEEP_EDITOR_XML,
            },
            initial_screen="booking_page",
        )
        memory = self._build_memory("executor_extract.db")
        executor, state = self._build_executor(adb, memory, "test-agent-extract")
        planner = RuleBasedPlanner(demo_config=build_demo_message_config())
        plan = planner.plan("extract the order number and copy it into notes", {})

        result = executor.execute_plan(plan)

        self.assertTrue(result["success"])
        self.assertEqual(state.artifacts["extracted_value"], "ZX-2048")
        self.assertIn("ZX-2048", adb.input_history[-1])

    def test_create_reminder_flow_opens_calendar_and_saves(self):
        adb = MockADB(
            {
                "reminder_editor": REMINDER_EDITOR_XML,
                "reminder_saved": REMINDER_SAVED_XML,
            },
            initial_screen="reminder_editor",
        )
        memory = self._build_memory("executor_reminder.db")
        executor, state = self._build_executor(adb, memory, "test-agent-reminder")
        planner = RuleBasedPlanner(demo_config=build_demo_message_config())
        plan = planner.plan("create a reminder for buy milk at 7pm", {})

        with mock.patch("builtins.input", return_value="y"):
            result = executor.execute_plan(plan)

        self.assertTrue(result["success"])
        self.assertEqual(result["task_type"], "create_reminder")
        self.assertEqual(adb.calendar_history[0]["title"], "buy milk")
        self.assertEqual(state.current_page, "reminder_saved")

    def test_missing_send_marks_replan_and_records_failure(self):
        adb = MockADB({"message_thread": MISSING_SEND_XML})
        memory = self._build_memory("executor_failure.db")
        executor, state = self._build_executor(adb, memory, "test-agent-failure")
        planner = RuleBasedPlanner(
            demo_config=build_demo_message_config(
                contact_name="Dave Zhu",
                phone_number="+18059577464",
                message_text="hello from emulator",
            )
        )
        plan = planner.create_demo_message_plan()

        with mock.patch("builtins.input", return_value="y"):
            result = executor.execute_plan(plan)

        self.assertFalse(result["success"])
        self.assertTrue(state.needs_replan)

        with sqlite3.connect(str(Path("tmp/test_dbs/executor_failure.db"))) as conn:
            task_type = conn.execute(
                "SELECT task_type FROM failure_patterns LIMIT 1"
            ).fetchone()[0]
        self.assertEqual(task_type, "send_message")


if __name__ == "__main__":
    unittest.main()

