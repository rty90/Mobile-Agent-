from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.memory import SQLiteMemory
from app.state import AgentState
from app.task_types import (
    TASK_CREATE_REMINDER,
    TASK_EXTRACT_AND_COPY,
    TASK_SEND_MESSAGE,
    detect_task_type,
    extract_contact_query,
)


class ContextBuilder(object):
    """Builds a compact task-aware context object for planning."""

    def __init__(self, memory: SQLiteMemory) -> None:
        self.memory = memory

    @staticmethod
    def _trim_screen_summary(summary: Dict[str, Any], task_type: str) -> Dict[str, Any]:
        visible_text = list(summary.get("visible_text", []))
        trimmed = {
            "app": summary.get("app"),
            "page": summary.get("page"),
            "visible_text": visible_text[:12],
        }
        if task_type == TASK_EXTRACT_AND_COPY:
            trimmed["visible_text"] = visible_text[:20]
        return trimmed

    def _build_memories(
        self,
        task_type: str,
        goal: str,
        app_name: str,
    ) -> List[Dict[str, Any]]:
        successes = self.memory.get_relevant_successes(task_type=task_type, app=app_name, limit=2)
        failures = self.memory.get_relevant_failures(task_type=task_type, app=app_name, limit=1)

        if len(successes) + len(failures) < 3:
            generic = self.memory.get_relevant_memories(intent=goal, app=app_name, limit=3)
            seen = set()
            merged = []
            for item in successes + failures + generic:
                key = (item.get("source"), item.get("intent"), item.get("steps_summary"))
                if key in seen:
                    continue
                merged.append(item)
                seen.add(key)
                if len(merged) >= 3:
                    return merged
            return merged
        return (successes + failures)[:3]

    def _build_contact_context(self, goal: str, task_type: str) -> Optional[Dict[str, Any]]:
        if task_type != TASK_SEND_MESSAGE:
            return None
        contact_query = extract_contact_query(goal)
        if contact_query:
            contacts = self.memory.get_relevant_contacts(contact_query, limit=1)
            if contacts:
                return contacts[0]
        best = self.memory.get_best_contact(prefer_ascii=True)
        return best

    def build(
        self,
        goal: str,
        state: AgentState,
        task_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_task_type = task_type or state.task_type or detect_task_type(goal)
        current_app = state.current_app or ""
        reminder_time = state.artifacts.get("parsed_reminder_time")
        extracted_value = state.artifacts.get("extracted_value")

        context = {
            "goal": goal,
            "task_type": resolved_task_type,
            "screen_summary": self._trim_screen_summary(state.screen_summary or {}, resolved_task_type),
            "recent_actions": state.recent_action_context(limit=2),
            "relevant_memories": self._build_memories(resolved_task_type, goal, current_app),
            "known_contact": self._build_contact_context(goal, resolved_task_type),
            "risk_flag": state.risk_flag,
        }

        if resolved_task_type == TASK_EXTRACT_AND_COPY:
            context["extracted_value"] = extracted_value
        if resolved_task_type == TASK_CREATE_REMINDER:
            context["parsed_reminder_time"] = reminder_time
        return context

