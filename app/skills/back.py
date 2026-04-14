from __future__ import annotations

from typing import Any, Dict, Mapping

from app.skills.base import BaseSkill, SkillContext


class BackSkill(BaseSkill):
    name = "back"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        context.adb.back()
        return self.result(success=True, detail="Back key pressed.")
