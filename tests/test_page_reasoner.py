import unittest

from app.page_reasoner import PageReasoner
from app.schemas.reasoning_decision import ReasoningDecision


class PageReasonerTests(unittest.TestCase):
    def test_rule_reasoner_extracts_order_number_from_visible_text(self):
        reasoner = PageReasoner(backend="rule")
        result = reasoner.reason(
            goal="extract the visible order number from the current page",
            task_type="read_current_screen",
            screen_summary={
                "page": "booking_page",
                "visible_text": ["Order number: ZX-2048", "Status: Ready"],
                "possible_targets": [],
            },
        )

        self.assertEqual(result["page_type"], "booking_page")
        self.assertEqual(result["facts"][0]["field"], "order_number")
        self.assertEqual(result["facts"][0]["value"], "ZX-2048")
        self.assertIsNone(result["next_action"])

    def test_rule_reasoner_suggests_keep_note_action_for_action_oriented_goal(self):
        reasoner = PageReasoner(backend="rule")
        result = reasoner.reason(
            goal="open keep and create a note",
            task_type="guided_ui_task",
            screen_summary={
                "page": "keep_home",
                "visible_text": ["Take a note"],
                "possible_targets": [
                    {"label": "Take a note", "clickable": True, "confidence": 0.9},
                ],
            },
        )

        self.assertEqual(result["next_action"]["skill"], "tap")
        self.assertEqual(result["next_action"]["args"]["target_key"], "new_note")
        self.assertEqual(result["next_action"]["args"]["target"], "Take a note")

    def test_rule_reasoner_accepts_create_a_note_variant_for_action_oriented_goal(self):
        reasoner = PageReasoner(backend="rule")
        result = reasoner.reason(
            goal="open keep and create a note",
            task_type="guided_ui_task",
            screen_summary={
                "page": "keep_home",
                "visible_text": ["Create a note"],
                "possible_targets": [
                    {"label": "Create a note", "clickable": True, "confidence": 0.9},
                ],
            },
        )

        self.assertEqual(result["next_action"]["skill"], "tap")
        self.assertEqual(result["next_action"]["args"]["target"], "Create a note")

    def test_rule_reasoner_does_not_pick_sort_notes_for_create_note(self):
        reasoner = PageReasoner(backend="rule")
        result = reasoner.reason(
            goal="open keep and create a note",
            task_type="guided_ui_task",
            screen_summary={
                "page": "keep_home",
                "visible_text": ["Search Keep", "Sort notes", "Create a note"],
                "possible_targets": [
                    {"label": "Sort notes", "clickable": True, "confidence": 0.85},
                    {
                        "label": "Create a note",
                        "content_desc": "Create a note",
                        "resource_id": "com.google.android.keep:id/speed_dial_create_close_button",
                        "clickable": True,
                        "confidence": 0.85,
                    },
                ],
            },
        )

        self.assertEqual(result["next_action"]["skill"], "tap")
        self.assertEqual(result["next_action"]["args"]["target"], "Create a note")

    def test_rule_reasoner_selects_speed_dial_text_note_option(self):
        reasoner = PageReasoner(backend="rule")
        result = reasoner.reason(
            goal="open keep and create a note",
            task_type="guided_ui_task",
            screen_summary={
                "page": "keep_home",
                "visible_text": ["Audio", "Image", "Drawing", "List", "Text"],
                "possible_targets": [
                    {
                        "label": "Text",
                        "content_desc": "New text note",
                        "resource_id": "com.google.android.keep:id/new_note_button",
                        "clickable": True,
                        "confidence": 0.95,
                    },
                    {
                        "label": "Close",
                        "content_desc": "Close",
                        "resource_id": "com.google.android.keep:id/speed_dial_create_close_button",
                        "clickable": True,
                        "confidence": 0.85,
                    },
                ],
            },
        )

        self.assertEqual(result["next_action"]["skill"], "tap")
        self.assertEqual(result["next_action"]["args"]["target"], "Text")

    def test_rule_reasoner_dismisses_keep_onboarding(self):
        reasoner = PageReasoner(backend="rule")
        result = reasoner.reason(
            goal="open keep and create a note",
            task_type="guided_ui_task",
            screen_summary={
                "page": "keep_home",
                "visible_text": ["Capture anything", "Get started"],
                "possible_targets": [{"label": "Get started", "clickable": True, "confidence": 0.95}],
            },
        )

        self.assertEqual(result["next_action"]["skill"], "tap")
        self.assertEqual(result["next_action"]["args"]["target"], "Get started")

    def test_rule_reasoner_dismisses_keep_notification_prompt(self):
        reasoner = PageReasoner(backend="rule")
        result = reasoner.reason(
            goal="open keep and create a note",
            task_type="guided_ui_task",
            screen_summary={
                "page": "keep_home",
                "visible_text": [
                    "Keep Notes needs permission to send notifications for reminders and for notes shared with you",
                    "Cancel",
                    "Continue",
                ],
                "possible_targets": [
                    {"label": "Cancel", "clickable": True, "confidence": 0.95},
                    {"label": "Continue", "clickable": True, "confidence": 0.95},
                ],
            },
        )

        self.assertEqual(result["next_action"]["skill"], "tap")
        self.assertEqual(result["next_action"]["args"]["target"], "Cancel")

    def test_rule_reasoner_does_not_click_for_read_only_guided_request(self):
        reasoner = PageReasoner(backend="rule")
        result = reasoner.reason(
            goal="open keep and tell me what is on the current page",
            task_type="guided_ui_task",
            screen_summary={
                "page": "keep_home",
                "visible_text": ["Create a note", "ZX-2048"],
                "possible_targets": [
                    {"label": "Create a note", "clickable": True, "confidence": 0.9},
                    {"label": "ZX-2048", "clickable": False, "confidence": 0.95},
                ],
            },
        )

        self.assertIsNone(result["next_action"])

    def test_stack_backend_adapts_reasoning_decision(self):
        class StubOrchestrator(object):
            def resolve(self, **kwargs):
                decision = ReasoningDecision(
                    decision="execute",
                    task_type="guided_ui_task",
                    skill="tap",
                    args={"target": "Create a note"},
                    confidence=0.88,
                    requires_confirmation=False,
                    reason_summary="Create a note is visible.",
                    validation_errors=[],
                    selected_backend="local_text",
                    fallback_used=False,
                )
                return {
                    "decision": decision,
                    "trace_path": "data/logs/reasoning_trace.jsonl",
                    "legacy_reasoning": decision.to_legacy_reasoning_payload(
                        {"page": "keep_home", "visible_text": ["Create a note"], "possible_targets": []}
                    ),
                }

        reasoner = PageReasoner(backend="stack", orchestrator=StubOrchestrator())
        result = reasoner.reason(
            goal="open keep and create a note",
            task_type="guided_ui_task",
            screen_summary={
                "page": "keep_home",
                "visible_text": ["Create a note"],
                "possible_targets": [],
            },
        )

        self.assertEqual(result["next_action"]["skill"], "tap")
        self.assertEqual(result["selected_backend"], "local_text")
        self.assertEqual(result["trace_path"], "data/logs/reasoning_trace.jsonl")

    def test_rule_reasoner_types_requested_text_in_keep_editor(self):
        reasoner = PageReasoner(backend="rule")
        result = reasoner.reason(
            goal="open keep and create a note, then type 'agent smoke test'",
            task_type="guided_ui_task",
            screen_summary={
                "page": "keep_editor",
                "visible_text": ["Title", "Note"],
                "possible_targets": [
                    {
                        "label": "Note",
                        "resource_id": "com.google.android.keep:id/edit_note_text",
                        "class_name": "android.widget.EditText",
                        "clickable": True,
                        "target_id": "n013",
                    }
                ],
            },
        )

        self.assertEqual(result["next_action"]["skill"], "type_text")
        self.assertEqual(result["next_action"]["args"]["text"], "agent smoke test")
        self.assertEqual(result["next_action"]["args"]["target_id"], "n013")


if __name__ == "__main__":
    unittest.main()
