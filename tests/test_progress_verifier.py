import unittest

from app.progress_verifier import build_action_guard, detect_repeated_no_progress


class ProgressVerifierTests(unittest.TestCase):
    def test_repeated_type_text_same_stage_is_flagged(self):
        goal = "open chrome, open bilibili, and find videos about llm"
        task_type = "guided_ui_task"
        first_summary = {
            "app": "com.android.chrome",
            "page": "browser_page",
            "visible_text": ["Search or type URL", "llm"],
            "possible_targets": [
                {
                    "label": "llm",
                    "resource_id": "com.android.chrome:id/url_bar",
                    "class_name": "android.widget.EditText",
                    "clickable": True,
                    "focused": True,
                    "target_id": "n006",
                }
            ],
        }
        second_summary = {
            "app": "com.android.chrome",
            "page": "browser_page",
            "visible_text": ["Search or type URL", "llmbilibili llm"],
            "possible_targets": [
                {
                    "label": "llmbilibili llm",
                    "resource_id": "com.android.chrome:id/url_bar",
                    "class_name": "android.widget.EditText",
                    "clickable": True,
                    "focused": True,
                    "target_id": "n006",
                }
            ],
        }
        args = {"text": "bilibili llm", "target_id": "n006", "press_enter": True}
        recent_actions = [
            {
                "action": "type_text",
                "success": True,
                "detail": "Text input completed.",
                "data": {
                    "screen_summary": first_summary,
                    "action_guard": build_action_guard(goal, task_type, "type_text", args, first_summary),
                },
            },
            {
                "action": "type_text",
                "success": True,
                "detail": "Text input completed.",
                "data": {
                    "screen_summary": second_summary,
                    "action_guard": build_action_guard(goal, task_type, "type_text", args, second_summary),
                },
            },
        ]

        reason = detect_repeated_no_progress(goal, task_type, recent_actions)

        self.assertIsNotNone(reason)
        self.assertIn("Repeated the same text input", reason)

    def test_completed_progress_is_not_flagged(self):
        goal = "open chrome, open bilibili, and find videos about llm"
        task_type = "guided_ui_task"
        summary = {
            "app": "com.android.chrome",
            "page": "bilibili_search_results",
            "current_domain": "search.bilibili.com",
            "current_url": "https://search.bilibili.com/all?keyword=llm",
            "visible_text": ["llm-哔哩哔哩_Bilibili", "综合"],
            "possible_targets": [],
        }
        args = {"query": "bilibili llm", "prefer_intent": True}
        recent_actions = [
            {
                "action": "search_in_app",
                "success": True,
                "detail": "Search opened through a browser intent.",
                "data": {
                    "screen_summary": summary,
                    "action_guard": build_action_guard(goal, task_type, "search_in_app", args, summary),
                },
            },
            {
                "action": "search_in_app",
                "success": True,
                "detail": "Search opened through a browser intent.",
                "data": {
                    "screen_summary": summary,
                    "action_guard": build_action_guard(goal, task_type, "search_in_app", args, summary),
                },
            },
        ]

        self.assertIsNone(detect_repeated_no_progress(goal, task_type, recent_actions))


if __name__ == "__main__":
    unittest.main()
