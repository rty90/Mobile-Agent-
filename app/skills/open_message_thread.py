from __future__ import annotations

from typing import Any, Dict, Mapping

from app.skills.base import BaseSkill, SkillContext


class OpenMessageThreadSkill(BaseSkill):
    name = "open_message_thread"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        phone_number = args.get("phone_number")
        if not phone_number:
            return self.result(success=False, detail="open_message_thread requires phone_number.")

        message_text = args.get("message_text")
        context.adb.force_stop_app("com.google.android.apps.messaging")
        context.adb.start_sendto_intent(
            phone_number=str(phone_number),
            body=str(message_text) if message_text is not None else None,
            wait_time=float(args.get("wait_time", 1.5)),
        )
        return self.result(
            success=True,
            detail="Opened SMS thread for {0}.".format(phone_number),
            data={"phone_number": phone_number},
        )
