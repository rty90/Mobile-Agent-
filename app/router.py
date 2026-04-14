from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.state import AgentState


HIGH_RISK_KEYWORDS = (
    "付款",
    "转账",
    "删除",
    "正式邮件",
    "send email",
    "wire transfer",
    "payment",
    "delete",
    "calendar invite",
    "对外发送",
)


@dataclass
class RouteDecision(object):
    mode: str
    requires_confirmation: bool = False
    reason: str = ""


class TaskRouter(object):
    """Minimal router for simple execute / replan / confirm decisions."""

    def route(self, task_text: str, state: Optional[AgentState] = None) -> RouteDecision:
        lower_task = task_text.lower()
        for keyword in HIGH_RISK_KEYWORDS:
            if keyword.lower() in lower_task:
                return RouteDecision(
                    mode="execute",
                    requires_confirmation=True,
                    reason="Task contains a high-risk action keyword.",
                )

        if state and state.needs_replan:
            return RouteDecision(mode="replan", reason="Previous execution failed.")

        return RouteDecision(mode="execute", requires_confirmation=False, reason="Simple task path.")
