import unittest

from app.router import TaskRouter
from app.state import AgentState


class RouterTests(unittest.TestCase):
    def test_read_current_screen_routes_to_execute(self):
        decision = TaskRouter().route("read the current screen and summarize it")
        self.assertEqual(decision.mode, "execute")
        self.assertEqual(decision.task_type, "read_current_screen")
        self.assertTrue(decision.supported)

    def test_guided_ui_task_routes_to_execute_without_fallback(self):
        decision = TaskRouter().route("open keep and tell me what is on the current page")
        self.assertEqual(decision.mode, "execute")
        self.assertEqual(decision.task_type, "guided_ui_task")
        self.assertFalse(decision.fallback_allowed)

    def test_supported_message_task_routes_to_execute(self):
        decision = TaskRouter().route('send message to Dave "hello"')
        self.assertEqual(decision.mode, "execute")
        self.assertEqual(decision.task_type, "send_message")
        self.assertTrue(decision.supported)

    def test_high_risk_keyword_routes_to_confirm_first(self):
        decision = TaskRouter().route("send official message about payment to vendor")
        self.assertEqual(decision.mode, "confirm-first")
        self.assertTrue(decision.requires_confirmation)
        self.assertEqual(decision.risk_level, "high")

    def test_replan_mode_when_state_marks_needs_replan(self):
        state = AgentState(needs_replan=True, last_failure_reason="send button missing")
        decision = TaskRouter().route("create a reminder for buy milk at 7pm", state=state)
        self.assertEqual(decision.mode, "replan")
        self.assertIn("send button missing", decision.reason)

    def test_replan_mode_when_recent_failures_repeat(self):
        state = AgentState()
        state.record_step("tap", False, "missing target")
        state.record_step("tap", False, "missing target")
        decision = TaskRouter().route("extract the order number and copy it into notes", state=state)
        self.assertEqual(decision.mode, "replan")
        self.assertEqual(decision.task_type, "extract_and_copy")

    def test_unsupported_task_routes_to_unsupported_mode(self):
        decision = TaskRouter().route("book me a flight to tokyo")
        self.assertEqual(decision.mode, "unsupported-task")
        self.assertEqual(decision.task_type, "unsupported")
        self.assertFalse(decision.supported)


if __name__ == "__main__":
    unittest.main()
