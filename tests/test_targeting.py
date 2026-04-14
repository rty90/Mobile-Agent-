import unittest

from app.demo_config import build_demo_message_config
from app.skills.targeting import find_fallback_target, find_semantic_target


class TargetingTests(unittest.TestCase):
    def test_semantic_target_prefers_label_match(self):
        summary = {
            "possible_targets": [
                {
                    "label": "com.app:id/search_button",
                    "resource_id": "com.app:id/search_button",
                    "content_desc": "",
                    "bounds": {"center_x": 10, "center_y": 10},
                },
                {
                    "label": "Search",
                    "resource_id": "com.app:id/toolbar_search",
                    "content_desc": "",
                    "bounds": {"center_x": 20, "center_y": 20},
                },
            ]
        }
        target = find_semantic_target(summary, "search")
        self.assertEqual(target["bounds"]["center_x"], 20)

    def test_fallback_target_scales_coordinates(self):
        config = build_demo_message_config()
        fallback = find_fallback_target(
            config,
            "messages_home",
            "search",
            (1000, 2000),
        )
        self.assertEqual(fallback["bounds"]["center_x"], 900)
        self.assertEqual(fallback["bounds"]["center_y"], 200)


if __name__ == "__main__":
    unittest.main()
