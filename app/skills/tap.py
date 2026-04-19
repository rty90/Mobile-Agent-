from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from app.skills.base import BaseSkill, SkillContext
from app.skills.read_screen import read_screen_summary
from app.skills.targeting import find_fallback_target, find_semantic_target


def _find_target(summary: Dict[str, Any], target: str) -> Optional[Dict[str, Any]]:
    return find_semantic_target(summary, target)


class TapSkill(BaseSkill):
    name = "tap"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        if "x" in args and "y" in args:
            x, y = int(args["x"]), int(args["y"])
            context.adb.tap(x, y)
            return self.result(
                success=True,
                detail="Tapped coordinates ({0}, {1}).".format(x, y),
                data={"target": {"center_x": x, "center_y": y}, "fallback_used": False},
            )

        target = args.get("target")
        if not target:
            return self.result(success=False, detail="Tap requires x/y or target.")

        summary = context.state.screen_summary or read_screen_summary(
            context.adb,
            "data/tmp/tap_lookup.xml",
            runtime_config=context.runtime_config,
        )
        context.state.update_screen_summary(summary)

        fallback_used = False
        candidate = None
        if args.get("prefer_fallback") and args.get("target_key"):
            candidate = find_fallback_target(
                context.runtime_config,
                context.state.current_page or summary.get("page", ""),
                str(args.get("target_key")),
                context.adb.get_screen_size(),
            )
            fallback_used = bool(candidate)
        if not candidate:
            candidate = _find_target(summary, str(target))
        if (not candidate or not candidate.get("bounds")) and args.get("target_key"):
            candidate = find_fallback_target(
                context.runtime_config,
                context.state.current_page or summary.get("page", ""),
                str(args.get("target_key")),
                context.adb.get_screen_size(),
            )
            fallback_used = bool(candidate)

        if not candidate or not candidate.get("bounds"):
            return self.result(
                success=False,
                detail="Unable to find tap target: {0}".format(target),
                data={"fallback_used": False, "target_name": target},
            )

        bounds = candidate["bounds"]
        context.adb.tap(bounds["center_x"], bounds["center_y"])
        return self.result(
            success=True,
            detail="Tapped target {0}.".format(candidate.get("label")),
            data={"target": candidate, "fallback_used": fallback_used},
        )
