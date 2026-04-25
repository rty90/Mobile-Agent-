from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.skills.manual_intervention import _infer_resolution_label
from app.skills.read_screen import read_screen_summary
from app.task_types import TASK_GUIDED_UI_TASK


def _top_clickable_targets(screen_summary: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    targets = []
    for item in screen_summary.get("possible_targets", []):
        if not item.get("clickable"):
            continue
        targets.append(
            {
                "label": item.get("label"),
                "target_id": item.get("target_id"),
                "resource_id": item.get("resource_id"),
                "bounds": item.get("bounds"),
            }
        )
        if len(targets) >= limit:
            break
    return targets


def _print_coach_round(
    round_index: int,
    screen_summary: Dict[str, Any],
    reasoning: Dict[str, Any],
) -> None:
    next_action = reasoning.get("next_action") or {}
    args = next_action.get("args") if isinstance(next_action.get("args"), dict) else {}
    print("\n=== Coach round {0} ===".format(round_index), flush=True)
    print("Page: {0} | App: {1}".format(screen_summary.get("page"), screen_summary.get("app")), flush=True)
    if screen_summary.get("current_url"):
        print("URL: {0}".format(screen_summary.get("current_url")), flush=True)
    print("Visible text: {0}".format(" | ".join(str(x) for x in screen_summary.get("visible_text", [])[:10])), flush=True)
    print("Reason summary: {0}".format(reasoning.get("reason_summary") or reasoning.get("summary") or ""), flush=True)
    print("Confidence: {0}".format(reasoning.get("confidence")), flush=True)
    print("Suggested action:", flush=True)
    print(
        json.dumps(
            {
                "skill": next_action.get("skill"),
                "args": args,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    targets = _top_clickable_targets(screen_summary)
    if targets:
        print("Clickable targets:", flush=True)
        for target in targets:
            print(
                "- {label} | target_id={target_id} | resource_id={resource_id} | bounds={bounds}".format(
                    **target
                ),
                flush=True,
            )


def _compact_screen_summary(screen_summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "app": screen_summary.get("app"),
        "page": screen_summary.get("page"),
        "current_package": screen_summary.get("current_package"),
        "current_domain": screen_summary.get("current_domain"),
        "current_url": screen_summary.get("current_url"),
        "visible_text": list(screen_summary.get("visible_text", []))[:8],
        "top_clickable_targets": _top_clickable_targets(screen_summary, limit=5),
        "ui_dump_path": screen_summary.get("ui_dump_path"),
    }


def _coach_resolution_label(
    before_summary: Dict[str, Any],
    after_summary: Dict[str, Any],
    task_text: str,
    response_text: str,
) -> str:
    if response_text.lower() == "done":
        return "coach_goal_done"
    return _infer_resolution_label(before_summary, after_summary, task_text)


def run_coach_session(
    runtime: Dict[str, Any],
    task_text: str,
    task_type: str,
    max_steps: int,
) -> Dict[str, Any]:
    """Observe the UI, suggest actions, let the human act, then record reflections."""
    adb = runtime["adb"]
    state = runtime["state"]
    memory = runtime["memory"]
    context_builder = runtime["context_builder"]
    page_reasoner = runtime["page_reasoner"]
    screenshot_manager = runtime["executor"].screenshot_manager
    runtime_config = runtime["runtime_config"]

    state.start_task(task_text, task_type=task_type or TASK_GUIDED_UI_TASK)
    rounds = []
    success = False

    for round_index in range(1, max_steps + 1):
        before_screenshot = screenshot_manager.capture(
            adb,
            task_name=task_text,
            prefix="coach_before_{0:02d}".format(round_index),
        )
        before_summary = read_screen_summary(
            adb,
            "data/tmp/coach_before_{0:02d}.xml".format(round_index),
            runtime_config=runtime_config,
        )
        state.update_screen_summary(before_summary)
        state.add_screenshot(str(before_screenshot))
        reasoning_context = context_builder.build_reasoning_input(
            goal=task_text,
            state=state,
            task_type=task_type,
        )
        reasoning = page_reasoner.reason(
            goal=task_text,
            task_type=task_type,
            screen_summary=before_summary,
            screenshot_path=str(before_screenshot),
            recent_actions=reasoning_context.get("recent_actions"),
            relevant_memories=reasoning_context.get("relevant_memories"),
            normalized_context=reasoning_context,
        )
        _print_coach_round(round_index, before_summary, reasoning)

        response = input(
            "Manually operate on the emulator now. Press Enter after your action, type 'done' when finished, or 'fail' to stop: "
        )
        response_text = str(response or "").strip()
        if response_text.lower() in {"fail", "abort", "q", "quit"}:
            rounds.append(
                {
                    "round": round_index,
                    "status": "aborted",
                    "reasoning": reasoning,
                    "before_screenshot_path": str(before_screenshot),
                }
            )
            break

        after_screenshot = screenshot_manager.capture(
            adb,
            task_name=task_text,
            prefix="coach_after_{0:02d}".format(round_index),
        )
        after_summary = read_screen_summary(
            adb,
            "data/tmp/coach_after_{0:02d}.xml".format(round_index),
            runtime_config=runtime_config,
        )
        state.update_screen_summary(after_summary)
        next_action = reasoning.get("next_action") if isinstance(reasoning.get("next_action"), dict) else {}
        next_args = next_action.get("args") if isinstance(next_action.get("args"), dict) else {}
        next_skill = str(next_action.get("skill") or "").strip()
        resolution_label = _coach_resolution_label(before_summary, after_summary, task_text, response_text)
        agent_actions = list(state.recent_actions or [])
        reflection = {
            "goal": task_text,
            "agent_suggestion": {
                "skill": next_skill,
                "args": next_args,
                "reason_summary": reasoning.get("reason_summary") or reasoning.get("summary") or "",
                "confidence": reasoning.get("confidence"),
            },
            "human_observed_transition": {
                "label": resolution_label,
                "before_page": before_summary.get("page"),
                "after_page": after_summary.get("page"),
                "before_url": before_summary.get("current_url"),
                "after_url": after_summary.get("current_url"),
                "before_domain": before_summary.get("current_domain"),
                "after_domain": after_summary.get("current_domain"),
                "before_visible_text": before_summary.get("visible_text", [])[:8],
                "after_visible_text": after_summary.get("visible_text", [])[:8],
                "user_note": response_text,
            },
            "corrected_strategy": (
                "Compare the suggested action with the human-caused screen transition before turning it into memory."
            ),
            "should_auto_execute": False,
        }
        if memory:
            memory.add_manual_reflection(
                task_type=task_type,
                app=state.current_app or str(before_summary.get("app") or ""),
                page=str(before_summary.get("page") or ""),
                intent=task_text,
                trigger_reason="coach_mode_human_demonstration",
                resolution_label=resolution_label,
                failed_skill=next_skill,
                failed_args=next_args,
                agent_actions=agent_actions,
                before_summary=before_summary,
                after_summary=after_summary,
                reflection=reflection,
                confidence=0.85,
            )
        state.recent_actions.append(
            {
                "action": "coach_observe",
                "success": True,
                "detail": "Human completed coach round {0}: {1}".format(round_index, resolution_label),
                "data": {
                    "agent_suggestion": reflection["agent_suggestion"],
                    "screen_summary": _compact_screen_summary(after_summary),
                },
            }
        )
        state.recent_actions = state.recent_actions[-5:]
        rounds.append(
            {
                "round": round_index,
                "status": "done" if response_text.lower() == "done" else "continued",
                "resolution_label": resolution_label,
                "agent_suggestion": reflection["agent_suggestion"],
                "before_screenshot_path": str(before_screenshot),
                "after_screenshot_path": str(after_screenshot),
                "before_ui_dump_path": str(before_summary.get("ui_dump_path") or ""),
                "after_ui_dump_path": str(after_summary.get("ui_dump_path") or ""),
            }
        )
        if response_text.lower() == "done":
            success = True
            if memory:
                memory.add_successful_trajectory(
                    task_type=task_type,
                    app=state.current_app or str(after_summary.get("app") or ""),
                    intent=task_text,
                    steps_summary="coach_mode: human demonstration with agent suggestions",
                    confidence=0.85,
                    verified=True,
                )
            break

    return {
        "goal": task_text,
        "task_type": task_type,
        "status": "coach-complete" if success else "coach-stopped",
        "success": success,
        "agent_mode": "coach",
        "rounds": rounds,
        "memory_path": "data/memory.db",
        "readout_command": "python scripts\\read_guided_ui_learning.py 5",
    }
