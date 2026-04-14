import tempfile
import unittest
from pathlib import Path

from app.context_builder import ContextBuilder
from app.demo_config import build_demo_message_config
from app.memory import SQLiteMemory
from app.planner import TaskPlanner
from app.state import AgentState


class PlannerTests(unittest.TestCase):
    def test_rule_planner_message_task_uses_phone_thread_when_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            planner = TaskPlanner(
                context_builder=ContextBuilder(memory),
                backend="rule",
                demo_config=build_demo_message_config(
                    contact_name="Dave Zhu",
                    phone_number="+18059577464",
                    message_text="hello from emulator",
                ),
            )
            state = AgentState()
            plan = planner.create_plan('给Dave Zhu发消息 "hello from emulator"', state)
            payload = plan.to_dict()

        self.assertEqual(payload["steps"][0]["skill"], "open_message_thread")
        self.assertEqual(payload["steps"][0]["args"]["phone_number"], "+18059577464")


if __name__ == "__main__":
    unittest.main()
