import unittest
from pathlib import Path

from app.skills.base import SkillContext
from app.skills.type_text import TypeTextSkill
from app.state import AgentState
from app.utils.logger import setup_logger
from app.utils.screenshot import ScreenshotManager


TYPE_TEXT_BEFORE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="Search or type URL" resource-id="com.android.chrome:id/url_bar" content-desc="" clickable="true" focusable="true" focused="true" enabled="true" bounds="[192,166][932,316]" class="android.widget.EditText" hint="Search or type URL" />
</hierarchy>
"""


TYPE_TEXT_AFTER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy>
  <node text="bilibili llm" resource-id="com.android.chrome:id/url_bar" content-desc="" clickable="true" focusable="true" focused="true" enabled="true" bounds="[192,166][932,316]" class="android.widget.EditText" hint="Search or type URL" />
</hierarchy>
"""


class MockTypeTextADB(object):
    def __init__(self, apply_text: bool):
        self.apply_text = apply_text
        self.device_id = "emulator-5554"
        self.input_history = []
        self.tap_history = []
        self.keyevents = []
        self.back_count = 0
        self._current_xml = TYPE_TEXT_BEFORE_XML

    def dump_ui_xml(self, local_path):
        path = Path(local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._current_xml, encoding="utf-8")
        return path

    def get_current_focus(self):
        return "mCurrentFocus=Window{123 u0 com.android.chrome/com.google.android.apps.chrome.Main}"

    def tap(self, x, y):
        self.tap_history.append((x, y))

    def back(self):
        self.back_count += 1

    def keyevent(self, key_code):
        self.keyevents.append(key_code)

    def input_text_best_effort(self, text):
        self.input_history.append(text)
        if self.apply_text:
            self._current_xml = TYPE_TEXT_AFTER_XML
        return "shell_input"


class TypeTextSkillTests(unittest.TestCase):
    def _build_context(self, adb):
        return SkillContext(
            adb=adb,
            state=AgentState(),
            logger=setup_logger("test-type-text"),
            screenshot_manager=ScreenshotManager(base_dir="data/screenshots/test"),
            registry={},
            memory=None,
            context_builder=None,
            page_reasoner=None,
            runtime_config=None,
        )

    def test_type_text_fails_when_ui_does_not_change(self):
        adb = MockTypeTextADB(apply_text=False)
        context = self._build_context(adb)
        context.state.update_screen_summary(
            {
                "app": "chrome",
                "page": "chrome_search",
                "visible_text": ["Search or type URL"],
                "possible_targets": [
                    {
                        "target_id": "n001",
                        "label": "Search or type URL",
                        "resource_id": "com.android.chrome:id/url_bar",
                        "bounds": {
                            "left": 192,
                            "top": 166,
                            "right": 932,
                            "bottom": 316,
                            "center_x": 562,
                            "center_y": 241,
                        },
                        "clickable": True,
                        "focusable": True,
                        "focused": True,
                        "hint": "Search or type URL",
                    }
                ],
                "focus": "",
            }
        )
        result = TypeTextSkill().execute(
            {"target_id": "n001", "text": "bilibili llm", "press_enter": True},
            context,
        )
        self.assertFalse(result["success"])
        self.assertIn("did not change the UI", result["detail"])
        self.assertEqual(adb.input_history, ["bilibili llm"])

    def test_type_text_succeeds_when_field_value_changes(self):
        adb = MockTypeTextADB(apply_text=True)
        context = self._build_context(adb)
        context.state.update_screen_summary(
            {
                "app": "chrome",
                "page": "chrome_search",
                "visible_text": ["Search or type URL"],
                "possible_targets": [
                    {
                        "target_id": "n001",
                        "label": "Search or type URL",
                        "resource_id": "com.android.chrome:id/url_bar",
                        "bounds": {
                            "left": 192,
                            "top": 166,
                            "right": 932,
                            "bottom": 316,
                            "center_x": 562,
                            "center_y": 241,
                        },
                        "clickable": True,
                        "focusable": True,
                        "focused": True,
                        "hint": "Search or type URL",
                    }
                ],
                "focus": "",
            }
        )
        result = TypeTextSkill().execute(
            {"target_id": "n001", "text": "bilibili llm", "press_enter": True},
            context,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["input_backend"], "shell_input")
        self.assertEqual(adb.keyevents, [66])


if __name__ == "__main__":
    unittest.main()
