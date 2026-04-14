from __future__ import annotations

import time
from typing import Any, Dict, Mapping

from app.skills.base import BaseSkill, SkillContext


class WaitSkill(BaseSkill):
    name = "wait"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        seconds = float(args.get("seconds", 1.0))
        time.sleep(seconds)
        return self.result(success=True, detail="Waited for {0:.2f}s.".format(seconds))
