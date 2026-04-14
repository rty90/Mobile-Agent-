from __future__ import annotations

from typing import Dict, Mapping

from app.skills.base import BaseSkill, SkillContext


APP_NAME_TO_PACKAGE = {
    "messages": "com.google.android.apps.messaging",
    "message": "com.google.android.apps.messaging",
    "sms": "com.google.android.apps.messaging",
    "chrome": "com.android.chrome",
    "settings": "com.android.settings",
    "gmail": "com.google.android.gm",
    "keep": "com.google.android.keep",
    "notes": "com.google.android.keep",
    "calendar": "com.google.android.calendar",
}


class OpenAppSkill(BaseSkill):
    name = "open_app"

    def execute(self, args: Mapping[str, object], context: SkillContext) -> Dict[str, object]:
        package_name = args.get("package_name")
        if not package_name and args.get("name"):
            package_name = APP_NAME_TO_PACKAGE.get(str(args["name"]).lower())

        if not package_name:
            return self.result(success=False, detail="Missing package_name or supported app name.")

        activity_name = args.get("activity_name")
        context.adb.open_app(package_name=str(package_name), activity_name=activity_name)
        context.state.current_app = str(package_name)
        return self.result(success=True, detail="Opened app {0}.".format(package_name))
