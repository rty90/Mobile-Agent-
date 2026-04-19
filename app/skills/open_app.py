from __future__ import annotations

from typing import Dict, Mapping

from app.skills.base import BaseSkill, SkillContext
from app.utils.adb import ADBError


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
        if not package_name:
            package_name = self._resolve_package_name(args)

        if not package_name:
            return self.result(success=False, detail="Missing package_name or supported app name.")

        activity_name = args.get("activity_name")
        package_name = str(package_name)
        if hasattr(context.adb, "is_package_installed") and not context.adb.is_package_installed(package_name):
            return self.result(
                success=False,
                detail="Target app is not installed: {0}".format(package_name),
                data={"package_name": package_name},
            )

        try:
            context.adb.open_app(package_name=package_name, activity_name=activity_name)
        except ADBError as exc:
            return self.result(
                success=False,
                detail="Failed to open app {0}: {1}".format(package_name, exc),
                data={"package_name": package_name},
            )

        context.state.current_app = str(package_name)
        return self.result(success=True, detail="Opened app {0}.".format(package_name))

    @staticmethod
    def _resolve_package_name(args: Mapping[str, object]) -> object:
        for key in ("name", "app_name", "app"):
            value = args.get(key)
            if not value:
                continue
            text = str(value).strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in APP_NAME_TO_PACKAGE:
                return APP_NAME_TO_PACKAGE[lowered]
            if "." in text:
                return text
        return None
