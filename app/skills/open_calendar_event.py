from __future__ import annotations

from typing import Any, Dict, Mapping

from app.skills.base import BaseSkill, SkillContext


class OpenCalendarEventSkill(BaseSkill):
    name = "open_calendar_event"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        title = args.get("title")
        if not title:
            return self.result(success=False, detail="open_calendar_event requires title.")

        begin_time_ms = args.get("begin_time_ms")
        package_name = args.get("package_name") or getattr(
            context.runtime_config, "calendar_package_name", "com.google.android.calendar"
        )
        context.adb.start_calendar_event_intent(
            title=str(title),
            begin_time_ms=int(begin_time_ms) if begin_time_ms is not None else None,
            package_name=str(package_name),
            wait_time=float(args.get("wait_time", 1.5)),
        )
        context.state.current_app = str(package_name)
        if args.get("time_text"):
            context.state.remember_artifact("parsed_reminder_time", args.get("time_text"))
        return self.result(
            success=True,
            detail="Opened calendar reminder editor for {0}.".format(title),
            data={
                "title": title,
                "begin_time_ms": begin_time_ms,
            },
        )

