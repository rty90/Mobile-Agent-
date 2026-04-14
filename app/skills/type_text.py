from __future__ import annotations

from typing import Any, Dict, Mapping

from app.skills.base import BaseSkill, SkillContext


class TypeTextSkill(BaseSkill):
    name = "type_text"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        text = args.get("text")
        if text is None:
            return self.result(success=False, detail="type_text requires a text argument.")
        context.adb.input_text(str(text))
        if args.get("press_enter"):
            context.adb.keyevent(66)
        return self.result(success=True, detail="Text input completed.")
