from __future__ import annotations

from typing import Any, Dict, Optional

from app.demo_config import DemoMessageConfig, scale_ratio_point


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def candidate_match_score(candidate: Dict[str, Any], target: str) -> int:
    target_normalized = normalize_text(target)
    if not target_normalized:
        return 0

    label = normalize_text(candidate.get("label", ""))
    resource_id = normalize_text(candidate.get("resource_id", ""))
    content_desc = normalize_text(candidate.get("content_desc", ""))

    if label == target_normalized:
        return 100
    if target_normalized and label.startswith(target_normalized):
        return 90
    if target_normalized and target_normalized in label:
        return 80
    if resource_id.endswith(target_normalized):
        return 70
    if target_normalized and target_normalized in resource_id:
        return 60
    if content_desc == target_normalized:
        return 55
    if target_normalized and target_normalized in content_desc:
        return 50
    return 0


def find_semantic_target(summary: Dict[str, Any], target: str) -> Optional[Dict[str, Any]]:
    best_candidate = None
    best_score = 0
    for candidate in summary.get("possible_targets", []):
        score = candidate_match_score(candidate, target)
        if score > best_score:
            best_candidate = candidate
            best_score = score
    return best_candidate


def find_fallback_target(
    runtime_config: Optional[DemoMessageConfig],
    page_name: str,
    target_key: str,
    screen_size,
) -> Optional[Dict[str, Any]]:
    if not runtime_config or not page_name or not target_key:
        return None

    profile = runtime_config.page_profiles.get(page_name)
    if not profile:
        return None

    ratio_point = profile.fallback_targets.get(target_key)
    if not ratio_point:
        return None

    x, y = scale_ratio_point(ratio_point, screen_size)
    return {
        "label": target_key,
        "resource_id": "",
        "content_desc": "",
        "bounds": {
            "left": x,
            "top": y,
            "right": x,
            "bottom": y,
            "center_x": x,
            "center_y": y,
        },
        "clickable": True,
        "confidence": 0.35,
        "fallback_used": True,
    }
