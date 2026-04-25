from __future__ import annotations

import os
from typing import Any, Dict, Mapping

from app.skills.base import BaseSkill, SkillContext
from app.skills.read_screen import read_screen_summary


def _infer_resolution_label(
    before_summary: Dict[str, Any],
    after_summary: Dict[str, Any],
    intent: str,
) -> str:
    before_text = " ".join(str(item or "").strip().lower() for item in (before_summary or {}).get("visible_text", []))
    after_text = " ".join(str(item or "").strip().lower() for item in (after_summary or {}).get("visible_text", []))
    after_url = str((after_summary or {}).get("current_url") or "").strip().lower()
    after_domain = str((after_summary or {}).get("current_domain") or "").strip().lower()
    if "/search" in after_url and ("keyword=" in after_url or "q=" in after_url):
        if "bilibili" in after_domain:
            return "reach_site_search_results"
        return "reach_search_results"
    if after_domain and before_summary.get("current_domain") != after_summary.get("current_domain"):
        return "navigate_to_site"
    if (
        any(marker in before_text for marker in ("try out your stylus", "write here", "use your stylus"))
        and not any(marker in after_text for marker in ("try out your stylus", "write here", "use your stylus"))
    ):
        return "dismiss_overlay"
    if intent:
        lowered_intent = str(intent).strip().lower()
        if "search" in lowered_intent or "find " in lowered_intent:
            if "search?keyword=" in after_text or "results" in after_text:
                return "reach_search_results"
    if before_summary.get("page") != after_summary.get("page"):
        return "navigate_to_correct_page"
    return "manual_continue"


def _compact_action(action: Dict[str, Any]) -> Dict[str, Any]:
    data = action.get("data") if isinstance(action.get("data"), dict) else {}
    return {
        "action": action.get("action"),
        "success": action.get("success"),
        "detail": action.get("detail", ""),
        "page": (data.get("screen_summary") or {}).get("page"),
    }


def _build_reflection(
    intent: str,
    trigger_reason: str,
    resolution_label: str,
    failed_skill: str,
    failed_args: Dict[str, Any],
    before_summary: Dict[str, Any],
    after_summary: Dict[str, Any],
    recent_actions: list,
) -> Dict[str, Any]:
    before_text = [str(item) for item in (before_summary or {}).get("visible_text", [])[:8]]
    after_text = [str(item) for item in (after_summary or {}).get("visible_text", [])[:8]]
    failed_target = failed_args.get("target") or failed_args.get("target_id") or failed_args.get("text") or ""
    compact_actions = [_compact_action(item) for item in recent_actions[-5:]]
    before_page = str((before_summary or {}).get("page") or "")
    after_page = str((after_summary or {}).get("page") or "")

    if resolution_label == "dismiss_overlay":
        observed_error = "The agent treated the underlying app as actionable while an overlay was blocking input."
        corrected_strategy = "Detect blocking overlay text/buttons first, then dismiss or complete the overlay before retrying the original action."
    elif resolution_label in {"reach_search_results", "reach_site_search_results"}:
        observed_error = "The agent did not reliably convert the search goal into a completed search-results state."
        corrected_strategy = "Prefer a focused search/url field, type the query, press Enter, and verify that results or a search URL appeared."
    elif resolution_label == "navigate_to_site":
        observed_error = "The agent reached a website, but had not yet completed the full goal."
        corrected_strategy = "Treat site navigation as an intermediate milestone, then continue with the site's own search or target UI."
    elif resolution_label == "navigate_to_correct_page":
        observed_error = "The agent's selected action did not move the UI toward the intended page."
        corrected_strategy = "Compare before/after page and visible target hints, then choose navigation actions that reduce the gap to the task goal."
    else:
        observed_error = "The agent could not make confident progress without human state correction."
        corrected_strategy = "Ask for manual takeover after repeated no-progress actions, then use the captured before/after state as diagnostic evidence."

    return {
        "goal": intent,
        "agent_attempt": {
            "failed_skill": failed_skill,
            "failed_target": str(failed_target),
            "failed_args": failed_args,
            "recent_actions": compact_actions,
        },
        "observed_error": observed_error,
        "human_resolution": {
            "label": resolution_label,
            "before_page": before_page,
            "after_page": after_page,
            "before_visible_text": before_text,
            "after_visible_text": after_text,
        },
        "corrected_strategy": corrected_strategy,
        "next_time_checklist": [
            "Check for modal or onboarding overlays before acting on background controls.",
            "Verify that the page or visible text changed after each action.",
            "If two similar actions do not change the state, pause for manual intervention instead of looping.",
        ],
        "should_auto_execute": False,
    }


class ManualInterventionSkill(BaseSkill):
    name = "manual_intervention"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        auto_confirm = os.environ.get("AGENT_AUTO_CONFIRM", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "y",
        )
        if auto_confirm:
            return self.result(
                success=False,
                detail="Manual intervention is required, but auto_confirm is enabled.",
            )

        task_name = context.state.current_task or "manual_intervention"
        before_screenshot = context.screenshot_manager.capture(
            context.adb,
            task_name=task_name,
            prefix="manual_before",
        )
        before_summary = read_screen_summary(
            context.adb,
            "data/tmp/manual_intervention_before.xml",
            runtime_config=context.runtime_config,
        )
        context.state.update_screen_summary(before_summary)

        prompt = str(
            args.get("prompt")
            or "Manual intervention needed. Fix the UI, then press Enter to continue or type 'fail' to abort."
        ).strip()
        response = input("{0} ".format(prompt))
        response_text = str(response or "").strip()
        if response_text.lower() in {"fail", "abort", "skip"}:
            return self.result(
                success=False,
                detail="Manual intervention was declined.",
                data={
                    "before_summary": before_summary,
                    "before_screenshot_path": str(before_screenshot),
                },
            )

        after_screenshot = context.screenshot_manager.capture(
            context.adb,
            task_name=task_name,
            prefix="manual_after",
        )
        after_summary = read_screen_summary(
            context.adb,
            "data/tmp/manual_intervention_after.xml",
            runtime_config=context.runtime_config,
        )
        context.state.update_screen_summary(after_summary)

        intent = context.state.current_task or ""
        resolution_label = _infer_resolution_label(before_summary, after_summary, intent)
        recent_actions = list(context.state.recent_actions or [])
        failed_skill = str(args.get("failed_skill") or "").strip()
        failed_args = args.get("failed_args") if isinstance(args.get("failed_args"), dict) else {}
        reflection = _build_reflection(
            intent=intent,
            trigger_reason=str(args.get("reason") or "").strip(),
            resolution_label=resolution_label,
            failed_skill=failed_skill,
            failed_args=failed_args,
            before_summary=before_summary,
            after_summary=after_summary,
            recent_actions=recent_actions,
        )
        if context.memory:
            context.memory.add_manual_intervention_episode(
                task_type=context.state.task_type or "",
                app=context.state.current_app or str(before_summary.get("app") or ""),
                page=context.state.current_page or str(before_summary.get("page") or ""),
                intent=intent,
                trigger_reason=str(args.get("reason") or "").strip(),
                resolution_label=resolution_label,
                before_summary=before_summary,
                after_summary=after_summary,
                recent_actions=recent_actions,
                before_screenshot_path=str(before_screenshot),
                after_screenshot_path=str(after_screenshot),
                before_ui_dump_path=str(before_summary.get("ui_dump_path") or ""),
                after_ui_dump_path=str(after_summary.get("ui_dump_path") or ""),
                user_note=response_text,
                confidence=0.95,
            )
            context.memory.add_manual_reflection(
                task_type=context.state.task_type or "",
                app=context.state.current_app or str(before_summary.get("app") or ""),
                page=context.state.current_page or str(before_summary.get("page") or ""),
                intent=intent,
                trigger_reason=str(args.get("reason") or "").strip(),
                resolution_label=resolution_label,
                failed_skill=failed_skill,
                failed_args=failed_args,
                agent_actions=recent_actions,
                before_summary=before_summary,
                after_summary=after_summary,
                reflection=reflection,
                confidence=0.9,
            )

        return self.result(
            success=True,
            detail="Manual intervention completed; continuing from the updated UI state.",
            screenshot_path=str(after_screenshot),
            data={
                "screen_summary": after_summary,
                "manual_intervention": {
                    "trigger_reason": str(args.get("reason") or "").strip(),
                    "resolution_label": resolution_label,
                    "user_note": response_text,
                    "before_screenshot_path": str(before_screenshot),
                    "after_screenshot_path": str(after_screenshot),
                    "before_ui_dump_path": str(before_summary.get("ui_dump_path") or ""),
                    "after_ui_dump_path": str(after_summary.get("ui_dump_path") or ""),
                    "before_summary": before_summary,
                    "after_summary": after_summary,
                    "reflection": reflection,
                },
            },
        )
