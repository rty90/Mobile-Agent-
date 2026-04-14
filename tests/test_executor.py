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
  <node text="Send" resource-id="send_button" content-desc="" clickable="true" bounds="[930,2060][1060,2200]" class="android.widget.ImageButton" />
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

    def get_screen_size(self):
        return (1080, 2400)

    def dump_ui_xml(self, local_path):
        path = Path(local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.xml_map[self.current_screen], encoding="utf-8")
        return path

    def get_current_focus(self):
        return "mCurrentFocus=Window{123 u0 com.google.android.apps.messaging/.ui.conversation.ConversationActivity}"

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

    def tap(self, x, y):
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

    def test_successful_demo_flow_records_success_memory(self):
        adb = MockADB({"message_thread": THREAD_XML})
        memory = self._build_memory("executor_success.db")
        executor, _state = self._build_executor(adb, memory, "test-agent-success")
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
        self.assertEqual(adb.intent_history[0]["phone_number"], "+18059577464")
        self.assertEqual(adb.intent_history[0]["body"], "hello from emulator")

        with sqlite3.connect(str(Path("tmp/test_dbs/executor_success.db"))) as conn:
            count = conn.execute("SELECT COUNT(*) FROM successful_trajectories").fetchone()[0]
        self.assertEqual(count, 1)

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
            count = conn.execute("SELECT COUNT(*) FROM failure_patterns").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
