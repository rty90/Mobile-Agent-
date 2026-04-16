from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.memory import SQLiteMemory
from app.reminder_parser import parse_reminder_task
from app.state import AgentState
from app.task_types import (
    TASK_CREATE_REMINDER,
    TASK_EXTRACT_AND_COPY,
    TASK_GUIDED_UI_TASK,
    TASK_READ_CURRENT_SCREEN,
    TASK_SEND_MESSAGE,
    detect_task_type,
    extract_contact_query,
    parse_guided_ui_task,
    parse_extract_task,
    parse_screen_read_task,
)


class ContextBuilder(object):
    """Build a compact task-aware context object for planning."""

    def __init__(self, memory: SQLiteMemory) -> None:
        self.memory = memory

    @staticmethod
    def _trim_screen_summary(summary: Dict[str, Any], task_type: str) -> Dict[str, Any]:
        visible_text = list(summary.get("visible_text", []))
        limit = 20 if task_type in (TASK_EXTRACT_AND_COPY, TASK_READ_CURRENT_SCREEN) else 12
        return {
            "app": summary.get("app"),
            "page": summary.get("page"),
            "visible_text": visible_text[:limit],
        }

    @staticmethod
    def _top_targets(summary: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
        targets = []
        seen = set()
        for candidate in summary.get("possible_targets", []):
            label = str(candidate.get("label", "")).strip()
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            targets.append(
                {
                    "label": label,
                    "resource_id": candidate.get("resource_id"),
                    "clickable": bool(candidate.get("clickable")),
                    "confidence": candidate.get("confidence", 0.0),
                }
            )
            if len(targets) >= limit:
                break
        return targets

    def _build_memories(
        self,
        task_type: str,
        goal: str,
        app_name: str,
    ) -> List[Dict[str, Any]]:
        successes = self.memory.get_relevant_successes(task_type=task_type, app=app_name, limit=2)
        failures = self.memory.get_relevant_failures(task_type=task_type, app=app_name, limit=1)
        merged = successes + failures
        if merged:
            return merged[:3]

        generic = self.memory.get_relevant_memories(intent=goal, app=app_name, limit=5)
        filtered = []
        for item in generic:
            item_task_type = item.get("task_type")
            if item_task_type and item_task_type != task_type:
                continue
            filtered.append(item)
            if len(filtered) >= 3:
                break
        return filtered

    def _build_contact_context(self, goal: str) -> List[Dict[str, Any]]:
        contact_query = extract_contact_query(goal)
        if contact_query:
            contacts = self.memory.get_relevant_contacts(contact_query, limit=3)
            if contacts:
                return contacts[:3]
        best = self.memory.get_best_contact(prefer_ascii=True)
        return [best] if best else []

    def build(
        self,
        goal: str,
        state: AgentState,
        task_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved_task_type = task_type or state.task_type or detect_task_type(goal)
        current_app = state.current_app or ""
        context = {
            "goal": goal,
            "task_type": resolved_task_type,
            "current_app": current_app or (state.screen_summary or {}).get("app"),
            "screen_summary": self._trim_screen_summary(state.screen_summary or {}, resolved_task_type),
            "visible_text_excerpt": list((state.screen_summary or {}).get("visible_text", []))[:8],
            "top_targets": self._top_targets(state.screen_summary or {}),
            "recent_actions": state.recent_action_context(limit=2),
            "relevant_memories": self._build_memories(resolved_task_type, goal, current_app),
            "risk_flag": state.risk_flag,
        }

        if resolved_task_type == TASK_SEND_MESSAGE:
            remembered_contacts = self._build_contact_context(goal)
            if remembered_contacts:
                context["remembered_contacts"] = remembered_contacts
                context["known_contact"] = remembered_contacts[0]

        if resolved_task_type == TASK_EXTRACT_AND_COPY:
            extract_task = parse_extract_task(goal)
            context["source_app_hint"] = current_app or (state.screen_summary or {}).get("app")
            context["target_app_hint"] = extract_task["target_app"]
            context["target_package"] = extract_task["target_package"]
            if state.artifacts.get("extracted_value"):
                context["extracted_value"] = state.artifacts["extracted_value"]

        if resolved_task_type == TASK_READ_CURRENT_SCREEN:
            read_task = parse_screen_read_task(goal)
            if read_task.get("field_hint"):
                context["field_hint"] = read_task["field_hint"]
            context["summary_style"] = read_task["summary_style"]

        if resolved_task_type == TASK_CREATE_REMINDER:
            parsed = parse_reminder_task(goal)
            context["parsed_reminder"] = {
                "title": parsed["title"],
                "time_text": parsed["time_text"],
            }

        if resolved_task_type == TASK_GUIDED_UI_TASK:
            guided_task = parse_guided_ui_task(goal)
            if guided_task.get("target_alias"):
                context["target_app_hint"] = guided_task["target_alias"]
            if guided_task.get("target_package"):
                context["target_package"] = guided_task["target_package"]

        return context
