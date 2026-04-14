from __future__ import annotations

import os
from typing import Any, Dict, Mapping

from app.skills.base import BaseSkill, SkillContext


class ConfirmActionSkill(BaseSkill):
    name = "confirm_action"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        auto_confirm = args.get("auto_confirm")
        if auto_confirm is None:
            auto_confirm = os.environ.get("AGENT_AUTO_CONFIRM", "").strip().lower() in (
                "1",
                "true",
                "yes",
                "y",
            )
        if auto_confirm:
            return self.result(success=True, detail="Manual confirmation bypassed by auto_confirm.")

        prompt = args.get("prompt", "Confirm action? [y/N]: ")
        response = input("{0} ".format(prompt)).strip().lower()
        approved = response in ("y", "yes")
        return self.result(success=approved, detail="Manual confirmation: {0}".format(approved))
