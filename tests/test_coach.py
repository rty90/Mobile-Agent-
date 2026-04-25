import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.coach import run_coach_session
from app.context_builder import ContextBuilder
from app.memory import SQLiteMemory
from app.state import AgentState
from app.utils.screenshot import ScreenshotManager


BEFORE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="Compose" resource-id="compose_button" content-desc="Compose" clickable="true" focusable="true" focused="false" enabled="true" bounds="[900,2200][1200,2400]" class="android.widget.Button" hint="" />
</hierarchy>
"""

AFTER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="To" resource-id="to_field" content-desc="" clickable="true" focusable="true" focused="true" enabled="true" bounds="[100,300][900,420]" class="android.widget.EditText" hint="To" />
  <node text="Subject" resource-id="subject_field" content-desc="" clickable="true" focusable="true" focused="false" enabled="true" bounds="[100,500][900,620]" class="android.widget.EditText" hint="Subject" />
</hierarchy>
"""


class CoachADB(object):
    def __init__(self):
        self.current_screen = "before"
        self.xml_map = {"before": BEFORE_XML, "after": AFTER_XML}
        self.device_id = "emulator-5554"

    def dump_ui_xml(self, local_path):
        path = Path(local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.xml_map[self.current_screen], encoding="utf-8")
        return path

    def get_current_focus(self):
        return "mCurrentFocus=Window{123 u0 com.google.android.gm/.ConversationListActivity}"

    def screenshot(self, save_path):
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mock")
        return path


class CoachReasoner(object):
    def reason(self, **kwargs):
        return {
            "page_type": kwargs["screen_summary"].get("page"),
            "summary": "Gmail compose button is visible.",
            "reason_summary": "Tap Compose to start a draft.",
            "facts": [],
            "targets": [],
            "next_action": {"skill": "tap", "args": {"target": "Compose", "target_id": "n001"}},
            "confidence": 0.88,
            "requires_confirmation": False,
        }


class CoachModeTests(unittest.TestCase):
    def test_coach_session_prints_suggestion_and_records_reflection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            adb = CoachADB()
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            runtime = {
                "adb": adb,
                "state": AgentState(),
                "memory": memory,
                "context_builder": ContextBuilder(memory=memory),
                "page_reasoner": CoachReasoner(),
                "executor": type(
                    "ExecutorLike",
                    (),
                    {"screenshot_manager": ScreenshotManager(base_dir=str(Path(temp_dir) / "screens"))},
                )(),
                "runtime_config": None,
            }

            def user_done(_prompt):
                adb.current_screen = "after"
                return "done"

            with mock.patch("builtins.input", side_effect=user_done):
                result = run_coach_session(
                    runtime=runtime,
                    task_text="open gmail and create a new email draft",
                    task_type="guided_ui_task",
                    max_steps=3,
                )

            reflections = memory.list_manual_reflections(limit=5)
            successes = memory.get_relevant_successes(task_type="guided_ui_task", app=None, limit=5)

        self.assertTrue(result["success"])
        self.assertEqual(result["agent_mode"], "coach")
        self.assertEqual(result["rounds"][0]["agent_suggestion"]["skill"], "tap")
        self.assertEqual(len(reflections), 1)
        self.assertEqual(reflections[0]["failed_skill"], "tap")
        self.assertEqual(reflections[0]["reflection"]["agent_suggestion"]["args"]["target"], "Compose")
        self.assertEqual(len(successes), 1)


if __name__ == "__main__":
    unittest.main()
