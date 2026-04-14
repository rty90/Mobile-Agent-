import tempfile
import unittest
from pathlib import Path

from app.context_builder import ContextBuilder
from app.demo_config import build_demo_message_config
from app.memory import SQLiteMemory
from app.planner import TaskPlanner
from app.state import AgentState


class PlannerTests(unittest.TestCase):
    def _build_planner(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        memory = SQLiteMemory(db_path=str(Path(temp_dir.name) / "memory.db"))
        memory.upsert_contact("Dave Zhu", "+18059577464")
        planner = TaskPlanner(
            context_builder=ContextBuilder(memory),
            backend="rule",
            demo_config=build_demo_message_config(
                contact_name="Dave Zhu",
                phone_number="+18059577464",
                message_text="hello from emulator",
            ),
        )
        return planner

    def test_rule_planner_message_task_uses_phone_thread_when_available(self):
        planner = self._build_planner()
        state = AgentState()
        plan = planner.create_plan('send message to Dave Zhu "hello from emulator"', state)

        self.assertEqual(plan.task_type, "send_message")
        self.assertEqual(plan.steps[0].skill, "open_message_thread")
        self.assertEqual(plan.steps[0].args["phone_number"], "+18059577464")

    def test_rule_planner_extract_and_copy_flow_is_bounded(self):
        planner = self._build_planner()
        state = AgentState()
        plan = planner.create_plan("extract the order number and copy it into notes", state)

        self.assertEqual(plan.task_type, "extract_and_copy")
        self.assertEqual(
            [step.skill for step in plan.steps[:3]],
            ["read_screen", "extract_value", "open_app"],
        )

    def test_rule_planner_create_reminder_flow_uses_calendar_editor(self):
        planner = self._build_planner()
        state = AgentState()
        plan = planner.create_plan("create a reminder for buy milk at 7pm", state)

        self.assertEqual(plan.task_type, "create_reminder")
        self.assertEqual(plan.steps[0].skill, "open_calendar_event")
        self.assertEqual(plan.steps[2].skill, "confirm_action")

    def test_rule_planner_marks_unsupported_tasks(self):
        planner = self._build_planner()
        state = AgentState()
        plan = planner.create_plan("book me a flight to tokyo", state)

        self.assertEqual(plan.status, "unsupported")
        self.assertEqual(plan.task_type, "unsupported")
        self.assertEqual(plan.steps, [])


if __name__ == "__main__":
    unittest.main()

