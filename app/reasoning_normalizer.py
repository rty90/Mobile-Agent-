from __future__ import annotations

from typing import Any, Dict, Optional


ACTION_TO_SKILL = {
    "click": "tap",
    "tap": "tap",
    "press": "tap",
    "open": "open_app",
    "launch": "open_app",
    "open_app": "open_app",
    "type": "type_text",
    "input": "type_text",
    "type_text": "type_text",
    "search": "search_in_app",
    "search_in_app": "search_in_app",
    "swipe": "swipe",
    "back": "back",
    "wait": "wait",
}

APP_ALIASES = {
    "keep": {"keep", "google keep", "com.google.android.keep"},
    "messages": {"messages", "google messages", "com.google.android.apps.messaging"},
    "calendar": {"calendar", "google calendar", "com.google.android.calendar"},
}


def normalize_reasoning_payload(
    payload: Dict[str, Any],
    expected_task_type: str,
    goal: str,
) -> Dict[str, Any]:
    normalized = dict(payload or {})

    skill = _normalize_skill(normalized.get("skill"), normalized.get("action"))
    normalized["decision"] = _normalize_decision(normalized.get("decision"), skill)
    normalized["task_type"] = str(normalized.get("task_type") or expected_task_type)
    normalized["skill"] = skill
    normalized["args"] = _normalize_args(normalized, skill)
    normalized["confidence"] = _normalize_confidence(normalized.get("confidence"))
    normalized["requires_confirmation"] = bool(normalized.get("requires_confirmation", False))
    skill, normalized_args = _maybe_reduce_redundant_open_app(
        payload=normalized,
        expected_task_type=expected_task_type,
        goal=goal,
        skill=skill,
        args=normalized["args"],
    )
    normalized["skill"] = skill
    normalized["args"] = normalized_args
    normalized["reason_summary"] = _normalize_reason_summary(normalized, skill, goal)
    return normalized


def _normalize_skill(skill: Any, action: Any) -> Optional[str]:
    if skill is not None:
        text = str(skill).strip()
        if text:
            return text
    if action is None:
        return None
    action_text = str(action).strip().lower()
    return ACTION_TO_SKILL.get(action_text, action_text or None)


def _normalize_decision(decision: Any, skill: Optional[str]) -> str:
    text = str(decision).strip() if decision is not None else ""
    if text:
        return text
    return "execute" if skill is not None else "execute"


def _normalize_args(payload: Dict[str, Any], skill: Optional[str]) -> Dict[str, Any]:
    base_args = payload.get("args")
    if isinstance(base_args, dict):
        normalized = dict(base_args)
    else:
        normalized = {}

    if skill == "tap":
        _copy_if_present(normalized, payload, "target")
        _copy_if_present(normalized, payload, "target_key")
        _copy_if_present(normalized, payload, "target_id")
        _copy_if_present(normalized, payload, "action_id")
        _copy_if_present(normalized, payload, "resource_id")
        _copy_if_present(normalized, payload, "bounds")
        _copy_if_present(normalized, payload, "prefer_fallback")
    elif skill == "open_app":
        if "package_name" not in normalized:
            value = payload.get("package_name") or payload.get("package") or payload.get("target_package")
            if value:
                normalized["package_name"] = value
        if "app_name" not in normalized:
            value = payload.get("app_name") or payload.get("app") or payload.get("target_app")
            if value:
                normalized["app_name"] = value
    elif skill == "type_text":
        _copy_if_present(normalized, payload, "target")
        _copy_if_present(normalized, payload, "target_id")
        _copy_if_present(normalized, payload, "action_id")
        if "text" not in normalized:
            value = payload.get("text") or payload.get("value") or payload.get("input")
            if value is not None:
                normalized["text"] = value
    elif skill == "search_in_app":
        if "query" not in normalized:
            value = payload.get("query") or payload.get("text") or payload.get("target")
            if value is not None:
                normalized["query"] = value
    elif skill == "swipe":
        for key in ("x1", "y1", "x2", "y2", "duration"):
            _copy_if_present(normalized, payload, key)
    return normalized


def _normalize_confidence(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_reason_summary(
    payload: Dict[str, Any],
    skill: Optional[str],
    goal: str,
) -> str:
    for key in ("reason_summary", "summary", "reason", "message", "explanation"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    if skill is None:
        return "Read-only reasoning decision for the current goal."
    return "Normalized {0} action for: {1}".format(skill, (goal or "").strip() or "current task")


def _copy_if_present(target: Dict[str, Any], source: Dict[str, Any], key: str) -> None:
    value = source.get(key)
    if value is not None and key not in target:
        target[key] = value


def _maybe_reduce_redundant_open_app(
    payload: Dict[str, Any],
    expected_task_type: str,
    goal: str,
    skill: Optional[str],
    args: Dict[str, Any],
) -> (Optional[str], Dict[str, Any]):
    if skill != "open_app":
        return skill, args
    if expected_task_type != "guided_ui_task":
        return skill, args
    if not _is_read_only_goal(goal):
        return skill, args

    current_app = _normalize_app_name((payload.get("screen_summary") or {}).get("app"))
    if not current_app:
        current_app = _normalize_app_name((payload.get("_context_screen_summary") or {}).get("app"))
    requested_app = _normalize_app_name(
        args.get("app_name")
        or args.get("package_name")
        or payload.get("app")
        or payload.get("package")
        or payload.get("target_app")
        or payload.get("target_package")
    )
    if current_app and requested_app and current_app == requested_app:
        return None, {}
    return skill, args


def _is_read_only_goal(goal: str) -> bool:
    normalized = (goal or "").strip().lower()
    read_only_markers = (
        "tell me what is on",
        "what is on the current page",
        "inspect the current screen",
        "inspect the current page",
        "summarize the current screen",
        "summarize the current page",
        "read the current screen",
        "read the current page",
    )
    return any(marker in normalized for marker in read_only_markers)


def _normalize_app_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    for canonical, variants in APP_ALIASES.items():
        if text in variants:
            return canonical
    return text
