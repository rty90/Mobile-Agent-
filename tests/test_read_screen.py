import unittest

from app.affordances import build_affordance_graph
from app.demo_config import build_demo_message_config
from app.skills.read_screen import detect_page_name


class ReadScreenTests(unittest.TestCase):
    def test_detect_page_name_prefers_calendar_saved_page_over_generic_search(self):
        config = build_demo_message_config()
        visible_text = [
            "com.google.android.calendar:id/drawer_layout",
            "Search",
            "Jump to Today",
            "Open Tasks",
            "Creation menu",
            "Wednesday 15 April 2026, Open Schedule View",
        ]

        page = detect_page_name(visible_text, "", config)

        self.assertEqual(page, "reminder_saved")

    def test_detect_page_name_prefers_settings_home_over_messages_search(self):
        config = build_demo_message_config()
        visible_text = [
            "com.android.settings:id/settings_homepage_container",
            "com.android.settings:id/search_action_bar",
            "Search Settings",
            "Network & internet",
            "Connected devices",
            "Apps",
            "Notifications",
            "Storage",
        ]

        page = detect_page_name(visible_text, "", config)

        self.assertEqual(page, "settings_home")

    def test_affordance_graph_exposes_click_and_type_actions(self):
        summary = {
            "app": "unknown",
            "page": "keep_editor",
            "possible_targets": [
                {
                    "target_id": "n001",
                    "label": "Note",
                    "resource_id": "com.google.android.keep:id/edit_note_text",
                    "content_desc": "",
                    "class_name": "android.widget.EditText",
                    "clickable": True,
                    "bounds": {
                        "left": 0,
                        "top": 591,
                        "right": 1280,
                        "bottom": 735,
                        "center_x": 640,
                        "center_y": 663,
                    },
                }
            ],
        }

        graph = build_affordance_graph(summary)

        action_ids = [action["action_id"] for action in graph["actions"]]
        self.assertIn("tap:n001", action_ids)
        self.assertIn("type:n001", action_ids)
        self.assertEqual(graph["actions"][0]["args"]["target_id"], "n001")


if __name__ == "__main__":
    unittest.main()
