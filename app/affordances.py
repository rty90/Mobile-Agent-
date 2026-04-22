from __future__ import annotations

from typing import Any, Dict, List


def _compact_bounds(bounds: Dict[str, Any]) -> Dict[str, int]:
    return {
        "left": int(bounds.get("left", 0)),
        "top": int(bounds.get("top", 0)),
        "right": int(bounds.get("right", 0)),
        "bottom": int(bounds.get("bottom", 0)),
        "center_x": int(bounds.get("center_x", 0)),
        "center_y": int(bounds.get("center_y", 0)),
    }


def _role_from_class(class_name: str) -> str:
    lowered = (class_name or "").strip().lower()
    if "edittext" in lowered:
        return "input"
    if "button" in lowered or "floatingactionbutton" in lowered:
        return "button"
    if "checkbox" in lowered or "switch" in lowered:
        return "toggle"
    if "cardview" in lowered:
        return "card"
    return class_name.rsplit(".", 1)[-1] if class_name else "unknown"


def _candidate_summary(candidate: Dict[str, Any]) -> Dict[str, Any]:
    bounds = candidate.get("bounds") or {}
    return {
        "target_id": candidate.get("target_id"),
        "label": candidate.get("label") or candidate.get("content_desc") or candidate.get("resource_id"),
        "resource_id": candidate.get("resource_id") or "",
        "content_desc": candidate.get("content_desc") or "",
        "role": _role_from_class(str(candidate.get("class_name") or "")),
        "bounds": _compact_bounds(bounds) if isinstance(bounds, dict) else None,
    }


def build_affordance_graph(screen_summary: Dict[str, Any], limit: int = 30) -> Dict[str, Any]:
    """Build a bounded action space from Android UI nodes.

    The model should choose from these action ids instead of inventing labels or
    coordinates. Rules then become a safety rail rather than the primary driver.
    """

    actions: List[Dict[str, Any]] = []
    seen = set()
    for candidate in screen_summary.get("possible_targets", []):
        if not isinstance(candidate, dict):
            continue
        target_id = str(candidate.get("target_id") or "").strip()
        bounds = candidate.get("bounds")
        if not target_id or not isinstance(bounds, dict):
            continue

        summary = _candidate_summary(candidate)
        class_name = str(candidate.get("class_name") or "")
        clickable = bool(candidate.get("clickable"))
        is_input = "edittext" in class_name.lower()

        if clickable:
            action_id = "tap:{0}".format(target_id)
            if action_id not in seen:
                seen.add(action_id)
                actions.append(
                    {
                        "action_id": action_id,
                        "skill": "tap",
                        "args": {
                            "target_id": target_id,
                            "target": summary["label"],
                        },
                        "target": summary,
                    }
                )
        if is_input:
            action_id = "type:{0}".format(target_id)
            if action_id not in seen:
                seen.add(action_id)
                actions.append(
                    {
                        "action_id": action_id,
                        "skill": "type_text",
                        "args": {
                            "target_id": target_id,
                            "target": summary["label"],
                            "text": "<text>",
                        },
                        "target": summary,
                    }
                )

        if len(actions) >= limit:
            break

    actions.extend(
        [
            {
                "action_id": "system:back",
                "skill": "back",
                "args": {},
                "target": {"label": "Android Back", "role": "system"},
            },
            {
                "action_id": "system:wait",
                "skill": "wait",
                "args": {"seconds": 1},
                "target": {"label": "Wait briefly", "role": "system"},
            },
        ]
    )
    return {
        "app": screen_summary.get("app"),
        "page": screen_summary.get("page"),
        "actions": actions[:limit],
    }


def find_candidate_by_target_id(
    screen_summary: Dict[str, Any],
    target_id: str,
) -> Dict[str, Any] | None:
    wanted = str(target_id or "").strip()
    if not wanted:
        return None
    for candidate in screen_summary.get("possible_targets", []):
        if isinstance(candidate, dict) and str(candidate.get("target_id") or "").strip() == wanted:
            return candidate
    return None
