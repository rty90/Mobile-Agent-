import tempfile
import unittest
from pathlib import Path

from app.context_builder import ContextBuilder
from app.memory import SQLiteMemory
from app.state import AgentState


class ContextBuilderTests(unittest.TestCase):
    def test_context_builder_limits_memory_and_includes_contacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = SQLiteMemory(db_path=str(Path(temp_dir) / "memory.db"))
            for index in range(5):
                memory.add_failure_pattern(
                    app="com.example.app",
                    intent="demo task",
                    steps_summary="step {0}".format(index),
                    confidence=0.9 - index * 0.1,
                )
            memory.upsert_contact("Dave Zhu", "+18059577464")

            state = AgentState(current_app="com.example.app", screen_summary={"page": "home"})
            builder = ContextBuilder(memory=memory)
            context = builder.build(goal="demo task", state=state)

        self.assertEqual(len(context["relevant_memories"]), 3)
        self.assertEqual(context["remembered_contacts"][0]["contact_name"], "Dave Zhu")


if __name__ == "__main__":
    unittest.main()
