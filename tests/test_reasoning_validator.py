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
