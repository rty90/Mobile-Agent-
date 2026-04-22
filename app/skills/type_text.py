from __future__ import annotations

from typing import Any, Dict, Mapping

from app.affordances import find_candidate_by_target_id
from app.skills.base import BaseSkill, SkillContext
from app.skills.read_screen import read_screen_summary


class TypeTextSkill(BaseSkill):
    name = "type_text"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        text = args.get("text")
        if text is None:
            return self.result(success=False, detail="type_text requires a text argument.")
        target_id = args.get("target_id")
        if not target_id and isinstance(args.get("action_id"), str) and str(args.get("action_id")).startswith("type:"):
            target_id = str(args.get("action_id")).split(":", 1)[1]
        if target_id:
            summary = context.state.screen_summary or read_screen_summary(
                context.adb,
                "data/tmp/type_text_lookup.xml",
                runtime_config=context.runtime_config,
            )
            context.state.update_screen_summary(summary)
            candidate = find_candidate_by_target_id(summary, str(target_id))
            if not candidate or not candidate.get("bounds"):
                return self.result(
                    success=False,
                    detail="Unable to find text input target_id: {0}".format(target_id),
                )
            bounds = candidate["bounds"]
            context.adb.tap(bounds["center_x"], bounds["center_y"])
        context.adb.input_text(str(text))
        if args.get("press_enter"):
            context.adb.keyevent(66)
        return self.result(success=True, detail="Text input completed.")
