from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.state import AgentState
from app.task_types import (
    TASK_EXTRACT_AND_COPY,
    TASK_GUIDED_UI_TASK,
    TASK_READ_CURRENT_SCREEN,
    TASK_UNSUPPORTED,
    contains_high_risk_keyword,
    detect_task_type,
    is_formal_message,
    is_supported_task_type,
)


@dataclass
class RouteDecision(object):
    mode: str
    task_type: str = TASK_UNSUPPORTED
    supported: bool = False
    requires_confirmation: bool = False
    reason: str = ""
    risk_level: str = "low"
    fallback_allowed: bool = True

    @property
    def supported_task_type(self) -> str:
        return self.task_type


class TaskRouter(object):
    """Small deterministic router for supported v0.2 task flows."""

    def route(
        self,
        task_text: str,
        state: Optional[AgentState] = None,
        task_type_override: Optional[str] = None,
    ) -> RouteDecision:
        task_type = detect_task_type(task_text, override=task_type_override)
        supported = is_supported_task_type(task_type)
        repeated_failures = state.recent_failure_count(limit=3) if state else 0
        cross_app = task_type == TASK_EXTRACT_AND_COPY

        if not supported:
            return RouteDecision(
                mode="unsupported-task",
                task_type=task_type,
                supported=False,
                reason="Task does not match the currently supported bounded flows.",
                risk_level="unknown",
                fallback_allowed=False,
            )

        if state and state.needs_replan:
            return RouteDecision(
                mode="replan",
                task_type=task_type,
                supported=True,
                reason=state.last_failure_reason or "Previous execution marked needs_replan.",
                risk_level="medium",
                fallback_allowed=False,
            )

        if repeated_failures >= 2:
            return RouteDecision(
                mode="replan",
                task_type=task_type,
                supported=True,
                reason="Recent execution history shows repeated failures.",
                risk_level="medium",
                fallback_allowed=False,
            )

        if contains_high_risk_keyword(task_text):
            return RouteDecision(
                mode="confirm-first",
                task_type=task_type,
                supported=True,
                requires_confirmation=True,
                reason="Task contains a high-risk action keyword.",
                risk_level="high",
                fallback_allowed=False,
            )

        if is_formal_message(task_text):
            return RouteDecision(
                mode="confirm-first",
                task_type=task_type,
                supported=True,
                requires_confirmation=True,
                reason="Outgoing task appears formal or externally sensitive.",
                risk_level="medium",
                fallback_allowed=True,
            )

        return RouteDecision(
            mode="execute",
            task_type=task_type,
            supported=True,
            requires_confirmation=False,
            reason="Supported bounded task flow matched.",
            risk_level="medium" if cross_app or task_type == TASK_GUIDED_UI_TASK else "low",
            fallback_allowed=task_type not in (TASK_EXTRACT_AND_COPY, TASK_GUIDED_UI_TASK),
        )
