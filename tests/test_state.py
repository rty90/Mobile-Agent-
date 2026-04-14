import unittest

from app.state import AgentState


class StateTests(unittest.TestCase):
    def test_state_records_recent_step(self):
        state = AgentState()
        state.start_task("demo")
        state.record_step("tap", True, "ok", screenshot_path="shot.png")

        self.assertEqual(state.current_task, "demo")
        self.assertEqual(state.last_action, "tap")
        self.assertTrue(state.last_action_success)
        self.assertEqual(state.recent_screenshots, ["shot.png"])


if __name__ == "__main__":
    unittest.main()
