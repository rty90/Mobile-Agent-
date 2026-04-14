from __future__ import annotations

from typing import Any, Dict, List

from app.memory import SQLiteMemory
from app.state import AgentState


class ContextBuilder(object):
    """Builds a small working context instead of sending full history."""

    def __init__(self, memory: SQLiteMemory) -> None:
        self.memory = memory

    def _filter_memories(self, goal: str, app_name: str, limit: int) -> List[Dict[str, Any]]:
        candidates = self.memory.get_relevant_memories(
            intent=goal, app=app_name, limit=max(limit * 2, 3)
        )
        return candidates[:limit]

    def _extract_memory_facts(self, candidates: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        return candidates[:limit]

    def build(self, goal: str, state: AgentState) -> Dict[str, Any]:
        current_app = state.current_app or ""
        filtered = self._filter_memories(goal=goal, app_name=current_app, limit=3)
        relevant = self._extract_memory_facts(filtered, limit=3)
        return {
            "goal": goal,
            "screen_summary": state.screen_summary,
            "recent_actions": state.recent_action_context(limit=2),
            "relevant_memories": relevant,
            "remembered_contacts": self.memory.list_contacts(limit=3),
            "risk_flag": state.risk_flag,
        }
