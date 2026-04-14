from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.state import AgentState
from app.task_types import (
    HIGH_RISK_KEYWORDS,
    TASK_EXTRACT_AND_COPY,
    TASK_SEND_MESSAGE,
    TASK_UNSUPPORTED,
    detect_task_type,
)


@dataclass
class RouteDecision(object):
    mode: str
    requires_confirmation: bool = False
    reason: str = ""
    supported_task_type: str = TASK_UNSUPPORTED
    risk_level: str = "low"
    fallback_allowed: bool = True


class TaskRouter(object):
    """Small deterministic router for supported v0.2 task flows."""

    def route(
        self,
        task_text: str,
        state: Optional[AgentState] = None,
        task_type_override: Optional[str] = None,
    ) -> RouteDecision:
        task_type = detect_task_type(task_text, override=task_type_override)
        lower_task = task_text.lower()
        repeated_failures = state.recent_failure_count(limit=3) if state else 0
        cross_app = task_type == TASK_EXTRACT_AND_COPY

        if task_type == TASK_UNSUPPORTED:
            return RouteDecision(
                mode="unsupported-task",
                supported_task_type=task_type,
                reason="Task does not match the currently supported task flows.",
                risk_level="unknown",
                fallback_allowed=False,
            )

        if state and state.needs_replan:
            return RouteDecision(
                mode="replan",
                supported_task_type=task_type,
                reason=state.last_failure_reason or "Previous execution marked needs_replan.",
                risk_level="medium",
                fallback_allowed=False,
            )

        if repeated_failures >= 2:
            return RouteDecision(
                mode="replan",
                supported_task_type=task_type,
                reason="Recent execution history shows repeated failures.",
                risk_level="medium",
                fallback_allowed=False,
            )

        for keyword in HIGH_RISK_KEYWORDS:
            if keyword.lower() in lower_task:
                return RouteDecision(
                    mode="confirm-first",
                    requires_confirmation=True,
                    supported_task_type=task_type,
                    reason="Task contains a high-risk action keyword.",
                    risk_level="high",
                    fallback_allowed=False,
                )

        if task_type == TASK_SEND_MESSAGE and any(
            keyword in lower_task for keyword in ("official", "formal", "professional", "正式")
        ):
            return RouteDecision(
                mode="confirm-first",
                requires_confirmation=True,
                supported_task_type=task_type,
                reason="Outgoing messaging task appears formal or externally sensitive.",
                risk_level="medium",
                fallback_allowed=True,
            )

        return RouteDecision(
            mode="execute",
            requires_confirmation=False,
            supported_task_type=task_type,
            reason="Supported bounded task flow matched.",
            risk_level="medium" if cross_app else "low",
            fallback_allowed=not cross_app,
        )

