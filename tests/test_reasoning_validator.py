import unittest

from app.reasoning_validator import ReasoningValidator


class ReasoningValidatorTests(unittest.TestCase):
    def setUp(self):
        self.validator = ReasoningValidator(allowed_task_types=["guided_ui_task", "read_current_screen"])

    def test_accepts_valid_bounded_payload(self):
        decision = self.validator.validate_payload(
            payload={
                "decision": "execute",
                "task_type": "guided_ui_task",
                "skill": "tap",
                "args": {"target": "Create a note"},
                "confidence": 0.91,
                "requires_confirmation": False,
                "reason_summary": "The note entry target is visible.",
            },
            expected_task_type="guided_ui_task",
            goal="open keep and create a note",
            selected_backend="local_text",
        )

        self.assertEqual(decision.skill, "tap")
        self.assertEqual(decision.validation_errors, [])

    def test_rejects_invalid_json_string(self):
        decision = self.validator.validate_payload(
            payload="not json",
            expected_task_type="guided_ui_task",
            goal="open keep and inspect the current page",
            selected_backend="local_text",
        )

        self.assertTrue(decision.validation_errors)

    def test_rejects_unbounded_skill(self):
        decision = self.validator.validate_payload(
            payload={
                "decision": "execute",
                "task_type": "guided_ui_task",
                "skill": "reason_about_page",
                "args": {},
                "confidence": 0.88,
                "requires_confirmation": False,
                "reason_summary": "Not allowed.",
            },
            expected_task_type="guided_ui_task",
            goal="open keep and inspect the current page",
            selected_backend="local_text",
        )

        self.assertIn("skill is not allowed.", decision.validation_errors)

    def test_rejects_container_tap_target(self):
        decision = self.validator.validate_payload(
            payload={
                "decision": "execute",
                "task_type": "guided_ui_task",
                "skill": "tap",
                "args": {"target": "com.google.android.keep:id/pages", "target_key": "pages"},
                "confidence": 0.95,
                "requires_confirmation": False,
                "reason_summary": "The pages container is visible.",
            },
            expected_task_type="guided_ui_task",
            goal="open keep and create a note",
            selected_backend="local_text",
        )

        self.assertIn("tap target appears to be a non-actionable container.", decision.validation_errors)

    def test_rejects_non_clickable_tap_target_when_screen_context_is_available(self):
        decision = self.validator.validate_payload(
            payload={
                "decision": "execute",
                "task_type": "guided_ui_task",
                "skill": "tap",
                "args": {
                    "target": "Keep Notes needs permission to send notifications for reminders",
                    "target_key": "android:id/message",
                },
                "confidence": 0.9,
                "requires_confirmation": False,
                "reason_summary": "The notification message is visible.",
            },
            expected_task_type="guided_ui_task",
            goal="open keep and create a note",
            selected_backend="local_text",
            context={
                "screen_summary": {
                    "possible_targets": [
                        {
                            "label": "Keep Notes needs permission to send notifications for reminders",
                            "resource_id": "android:id/message",
                            "clickable": False,
                        },
                        {
                            "label": "Cancel",
                            "resource_id": "android:id/button2",
                            "clickable": True,
                        },
                    ]
                }
            },
        )

        self.assertIn(
            "tap target is not a clickable target on the current screen.",
            decision.validation_errors,
        )

    def test_rejects_new_note_alias_pointing_to_sort_notes(self):
        decision = self.validator.validate_payload(
            payload={
                "decision": "execute",
                "task_type": "guided_ui_task",
                "skill": "tap",
                "args": {"target": "Sort notes", "target_key": "new_note"},
                "confidence": 0.9,
                "requires_confirmation": False,
                "reason_summary": "Sort notes is visible.",
            },
            expected_task_type="guided_ui_task",
            goal="open keep and create a note",
            selected_backend="memory_rule",
            context={
                "screen_summary": {"page": "keep_home", "visible_text": ["Sort notes"]},
                "top_targets": [
                    {"label": "Sort notes", "resource_id": "menu_sort_order", "clickable": True},
                    {
                        "label": "Create a note",
                        "resource_id": "speed_dial_create_close_button",
                        "content_desc": "Create a note",
                        "clickable": True,
                    },
                ],
            },
        )

        self.assertIn(
            "tap target is not a clickable target on the current screen.",
            decision.validation_errors,
        )

    def test_rejects_short_text_target_matching_existing_note_card(self):
        decision = self.validator.validate_payload(
            payload={
                "decision": "execute",
                "task_type": "guided_ui_task",
                "skill": "tap",
                "args": {"target": "Text"},
                "confidence": 0.9,
                "requires_confirmation": False,
                "reason_summary": "Text is visible.",
            },
            expected_task_type="guided_ui_task",
            goal="open keep and create a note",
            selected_backend="memory_rule",
            context={
                "screen_summary": {"page": "keep_home", "visible_text": ["Text note. ZX-2048."]},
                "top_targets": [
                    {
                        "label": "Text note. ZX-2048.",
                        "resource_id": "com.google.android.keep:id/browse_text_note",
                        "clickable": True,
                    }
                ],
            },
        )

        self.assertIn(
            "tap target is not a clickable target on the current screen.",
            decision.validation_errors,
        )

    def test_accepts_tap_target_id_from_affordance_graph(self):
        decision = self.validator.validate_payload(
            payload={
                "decision": "execute",
                "task_type": "guided_ui_task",
                "skill": "tap",
                "args": {"action_id": "tap:n010", "target_id": "n010", "target": "Create a note"},
                "confidence": 0.92,
                "requires_confirmation": False,
                "reason_summary": "Use the visible Create a note affordance.",
            },
            expected_task_type="guided_ui_task",
            goal="open keep and create a note",
            selected_backend="cloud_reviewer",
            context={
                "_validation_screen_summary": {
                    "possible_targets": [
                        {"target_id": "n010", "label": "Create a note", "clickable": True}
                    ]
                }
            },
        )

        self.assertEqual(decision.validation_errors, [])
        self.assertEqual(decision.args["target_id"], "n010")

    def test_rejects_type_text_target_id_when_target_is_not_input(self):
        decision = self.validator.validate_payload(
            payload={
                "decision": "execute",
                "task_type": "guided_ui_task",
                "skill": "type_text",
                "args": {"action_id": "type:n002", "target_id": "n002", "text": "hello"},
                "confidence": 0.92,
                "requires_confirmation": False,
                "reason_summary": "Type into the selected target.",
            },
            expected_task_type="guided_ui_task",
            goal="type a note",
            selected_backend="cloud_reviewer",
            context={
                "_validation_screen_summary": {
                    "possible_targets": [
                        {
                            "target_id": "n002",
                            "label": "Create a note",
                            "class_name": "android.widget.Button",
                            "clickable": True,
                        }
                    ]
                }
            },
        )

        self.assertIn(
            "type_text target is not an input target on the current screen.",
            decision.validation_errors,
        )

    def test_normalizes_action_style_payload_into_bounded_schema(self):
        decision = self.validator.validate_payload(
            payload={
                "action": "click",
                "target": "Create a note",
                "resource_id": "new_note",
                "confidence": 0.92,
            },
            expected_task_type="guided_ui_task",
            goal="open keep and create a note",
            selected_backend="local_text",
        )

        self.assertEqual(decision.decision, "execute")
        self.assertEqual(decision.skill, "tap")
        self.assertEqual(decision.args["target"], "Create a note")
        self.assertEqual(decision.args["resource_id"], "new_note")
        self.assertEqual(decision.validation_errors, [])

    def test_normalizes_open_app_alias_fields(self):
        decision = self.validator.validate_payload(
            payload={
                "action": "open",
                "app": "Keep",
                "confidence": 0.95,
                "summary": "Keep is the target app.",
            },
            expected_task_type="guided_ui_task",
            goal="open keep",
            selected_backend="local_text",
        )

        self.assertEqual(decision.skill, "open_app")
        self.assertEqual(decision.args["app_name"], "Keep")
        self.assertEqual(decision.reason_summary, "Keep is the target app.")
        self.assertEqual(decision.validation_errors, [])

    def test_read_only_guided_request_drops_redundant_open_app(self):
        decision = self.validator.validate_payload(
            payload={
                "action": "open",
                "app": "Keep",
                "confidence": 0.95,
                "summary": "Keep is already open.",
                "screen_summary": {
                    "app": "Keep",
                    "page": "keep_home",
                },
            },
            expected_task_type="guided_ui_task",
            goal="open keep and inspect the current page",
            selected_backend="local_text",
        )

        self.assertIsNone(decision.skill)
        self.assertEqual(decision.args, {})
        self.assertEqual(decision.validation_errors, [])


if __name__ == "__main__":
    unittest.main()
