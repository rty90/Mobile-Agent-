from __future__ import annotations

from typing import Any, Dict, Mapping

from app.skills.base import BaseSkill, SkillContext
from app.skills.read_screen import read_screen_summary
from app.skills.tap import _find_target
from app.skills.targeting import find_fallback_target


SEARCH_TARGETS = ("搜索", "search", "find")


class SearchInAppSkill(BaseSkill):
    name = "search_in_app"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        query = args.get("query")
        if not query:
            return self.result(success=False, detail="search_in_app requires a query.")

        summary = context.state.screen_summary or read_screen_summary(
            context.adb,
            "data/tmp/search_lookup.xml",
            runtime_config=context.runtime_config,
        )
        context.state.update_screen_summary(summary)

        search_target = None
        for candidate in SEARCH_TARGETS:
            search_target = _find_target(summary, candidate)
            if search_target:
                break

        fallback_used = False
        if (not search_target or not search_target.get("bounds")) and args.get("target_key", "search"):
            search_target = find_fallback_target(
                context.runtime_config,
                context.state.current_page or summary.get("page", ""),
                str(args.get("target_key", "search")),
                context.adb.get_screen_size(),
            )
            fallback_used = bool(search_target)

        if not search_target or not search_target.get("bounds"):
            return self.result(
                success=False,
                detail="Unable to find search entry point.",
                data={"fallback_used": False, "target_name": "search"},
            )

        bounds = search_target["bounds"]
        context.adb.tap(bounds["center_x"], bounds["center_y"])
        context.adb.input_text(str(query))
        if args.get("press_enter", True):
            context.adb.keyevent(66)

        return self.result(
            success=True,
            detail="Search query entered.",
            data={"fallback_used": fallback_used, "target": search_target},
        )
