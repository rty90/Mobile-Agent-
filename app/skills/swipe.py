from __future__ import annotations

from typing import Any, Dict, Mapping

from app.skills.base import BaseSkill, SkillContext


class SwipeSkill(BaseSkill):
    name = "swipe"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        required_keys = ("x1", "y1", "x2", "y2")
        if not all(key in args for key in required_keys):
            return self.result(success=False, detail="Swipe requires x1, y1, x2, y2.")
        duration = int(args.get("duration", args.get("duration_ms", 300)))
        context.adb.swipe(
            int(args["x1"]),
            int(args["y1"]),
            int(args["x2"]),
            int(args["y2"]),
            duration,
        )
        return self.result(success=True, detail="Swipe executed.")
