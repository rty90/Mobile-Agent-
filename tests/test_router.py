import unittest

from app.router import TaskRouter
from app.state import AgentState


class RouterTests(unittest.TestCase):
    def test_supported_message_task_routes_to_execute(self):
        decision = TaskRouter().route('send message to Dave "hello"')
        self.assertEqual(decision.mode, "execute")
        self.assertEqual(decision.supported_task_type, "send_message")

    def test_high_risk_keyword_routes_to_confirm_first(self):
        decision = TaskRouter().route("send official message about payment to vendor")
        self.assertEqual(decision.mode, "confirm-first")
        self.assertTrue(decision.requires_confirmation)

    def test_replan_mode_when_state_marks_needs_replan(self):
        state = AgentState(needs_replan=True, last_failure_reason="send button missing")
        decision = TaskRouter().route("create a reminder for buy milk at 7pm", state=state)
        self.assertEqual(decision.mode, "replan")
        self.assertIn("send button missing", decision.reason)

    def test_unsupported_task_routes_to_unsupported_mode(self):
        decision = TaskRouter().route("book me a flight to tokyo")
        self.assertEqual(decision.mode, "unsupported-task")
        self.assertEqual(decision.supported_task_type, "unsupported")


if __name__ == "__main__":
    unittest.main()

