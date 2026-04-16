from __future__ import annotations

from typing import Any, Dict, Mapping

from app.skills.base import BaseSkill, SkillContext
from app.task_types import detect_task_type


class ReasonAboutPageSkill(BaseSkill):
    name = "reason_about_page"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        if not context.page_reasoner:
            return self.result(success=False, detail="Page reasoner is not configured.")

        goal = str(args.get("goal") or context.state.current_task or "")
        task_type = str(args.get("task_type") or context.state.task_type or detect_task_type(goal))
        screenshot_path = context.state.recent_screenshots[-1] if context.state.recent_screenshots else None
        reasoning_context = {}
        if context.context_builder:
            reasoning_context = context.context_builder.build(
                goal=goal,
                state=context.state,
                task_type=task_type,
            )

        reasoning = context.page_reasoner.reason(
            goal=goal,
            task_type=task_type,
            screen_summary=context.state.screen_summary or {},
            screenshot_path=screenshot_path,
            recent_actions=reasoning_context.get("recent_actions"),
            relevant_memories=reasoning_context.get("relevant_memories"),
        )

        artifacts = {"last_page_reasoning": reasoning}
        for fact in reasoning.get("facts", []):
            if fact.get("type") == "extracted_value" and fact.get("value"):
                artifacts["extracted_value"] = fact["value"]
                break

        return self.result(
            success=True,
            detail="Page reasoning completed.",
            data={
                "page_reasoning": reasoning,
                "artifacts": artifacts,
            },
        )
