from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional

from app.reasoning_normalizer import normalize_reasoning_payload
from app.schemas.reasoning_decision import ReasoningDecision
from app.task_types import contains_high_risk_keyword, is_supported_task_type


ALLOWED_REASONING_DECISIONS = {
    "execute",
    "cloud_review",
    "vl_review",
    "unsupported",
}

ALLOWED_REASONING_SKILLS = {
    "open_app",
    "tap",
    "swipe",
    "type_text",
    "back",
    "wait",
    "search_in_app",
}


class ReasoningValidator(object):
    def __init__(
        self,
        allowed_task_types: Optional[Iterable[str]] = None,
        allowed_skills: Optional[Iterable[str]] = None,
        min_confidence: float = 0.70,
    ) -> None:
        self.allowed_task_types = set(allowed_task_types or [])
        self.allowed_skills = set(allowed_skills or ALLOWED_REASONING_SKILLS)
        self.min_confidence = float(min_confidence)

    def validate_payload(
        self,
        payload: Any,
        expected_task_type: str,
        goal: str,
        selected_backend: str,
        fallback_used: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> ReasoningDecision:
        parsed, parse_errors = self._parse_payload(payload)
        decision = ReasoningDecision(
            task_type=expected_task_type,
            selected_backend=selected_backend,
            fallback_used=fallback_used,
            validation_errors=list(parse_errors),
        )
        if parsed is None:
            decision.reason_summary = "Reasoner returned invalid JSON."
            return decision
        if context:
            parsed = dict(parsed)
            parsed["_context_screen_summary"] = self._context_screen_targets(context)
        parsed = normalize_reasoning_payload(
            payload=parsed,
            expected_task_type=expected_task_type,
            goal=goal,
        )

        decision.decision = str(parsed.get("decision") or "unsupported")
        decision.task_type = str(parsed.get("task_type") or expected_task_type)
        decision.skill = parsed.get("skill")
        if decision.skill is not None:
            decision.skill = str(decision.skill)
        decision.args = parsed.get("args") if isinstance(parsed.get("args"), dict) else parsed.get("args")
        decision.requires_confirmation = bool(parsed.get("requires_confirmation", False))
        decision.reason_summary = str(parsed.get("reason_summary") or "").strip()
        decision.selected_backend = selected_backend
        decision.fallback_used = bool(fallback_used)

        confidence_value = parsed.get("confidence", 0.0)
        try:
            decision.confidence = float(confidence_value)
        except (TypeError, ValueError):
            decision.validation_errors.append("confidence must be a number.")
            decision.confidence = 0.0

        validation_errors = self._validate_decision(
            decision,
            expected_task_type,
            goal,
            screen_summary=parsed.get("_context_screen_summary"),
        )
        decision.validation_errors.extend(validation_errors)
        return decision

    def is_strong_decision(
        self,
        decision: ReasoningDecision,
        require_action: bool = False,
    ) -> bool:
        if decision.validation_errors:
            return False
        if decision.decision != "execute":
            return False
        if decision.confidence < self.min_confidence:
            return False
        if require_action and not decision.skill:
            return False
        return True

    def is_allowed_skill(self, skill_name: Optional[str]) -> bool:
        return skill_name is None or skill_name in self.allowed_skills

    @staticmethod
    def _parse_payload(payload: Any) -> (Optional[Dict[str, Any]], list):
        if isinstance(payload, ReasoningDecision):
            return payload.to_dict(), []
        if isinstance(payload, dict):
            return payload, []
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                return None, ["payload is not valid JSON."]
            if not isinstance(parsed, dict):
                return None, ["payload must be a JSON object."]
            return parsed, []
        return None, ["payload must be a dict or JSON object string."]

    def _validate_decision(
        self,
        decision: ReasoningDecision,
        expected_task_type: str,
        goal: str,
        screen_summary: Optional[Dict[str, Any]] = None,
    ) -> list:
        errors = []
        if decision.decision not in ALLOWED_REASONING_DECISIONS:
            errors.append("decision is not allowed.")

        if not decision.task_type:
            errors.append("task_type is required.")
        elif decision.task_type != expected_task_type:
            errors.append("task_type does not match the routed task.")
        elif self.allowed_task_types and decision.task_type not in self.allowed_task_types:
            errors.append("task_type is not supported.")
        elif not self.allowed_task_types and not is_supported_task_type(decision.task_type):
            errors.append("task_type is not supported.")

        if not isinstance(decision.args, dict):
            errors.append("args must be an object.")
            decision.args = {}

        if decision.skill is not None and decision.skill not in self.allowed_skills:
            errors.append("skill is not allowed.")
        if decision.skill == "tap" and self._looks_like_container_tap_target(decision.args):
            errors.append("tap target appears to be a non-actionable container.")
        if decision.skill == "tap" and not self._tap_target_is_clickable(decision.args, screen_summary):
            errors.append("tap target is not a clickable target on the current screen.")
        if decision.skill == "type_text" and not self._type_target_is_valid(decision.args, screen_summary):
            errors.append("type_text target is not an input target on the current screen.")

        if decision.confidence < 0.0 or decision.confidence > 1.0:
            errors.append("confidence must be in range 0.0..1.0.")

        if not decision.reason_summary:
            errors.append("reason_summary is required.")

        if contains_high_risk_keyword(goal) and not decision.requires_confirmation:
            errors.append("high-risk tasks must require confirmation.")

        return errors

    @staticmethod
    def _looks_like_container_tap_target(args: Dict[str, Any]) -> bool:
        target = str((args or {}).get("target") or "").strip().lower()
        target_key = str((args or {}).get("target_key") or "").strip().lower()
        combined = "{0} {1}".format(target, target_key)
        container_markers = (
            "drawer_layout",
            "recycler_view",
            "scrollview",
            "scroll_view",
            "coordinator_layout",
            "fragment_container",
            "buttonpanel",
            "button_panel",
            ":id/pages",
        )
        return any(marker in combined for marker in container_markers)

    @staticmethod
    def _candidate_matches(candidate: Dict[str, Any], target: str) -> bool:
        lowered = (target or "").strip().lower()
        if not lowered:
            return False
        for key in ("label", "resource_id", "content_desc"):
            value = str((candidate or {}).get(key) or "").strip().lower()
            if not value:
                continue
            if value == lowered:
                return True
            if len(lowered) <= 4:
                continue
            if lowered in value or value in lowered:
                return True
        return False

    @staticmethod
    def _target_key_alias_matches(candidate: Dict[str, Any], target_key: str) -> bool:
        alias = (target_key or "").strip().lower()
        if alias != "new_note":
            return True
        combined = " ".join(
            str((candidate or {}).get(key) or "").strip().lower()
            for key in ("label", "resource_id", "content_desc")
        )
        if "sort note" in combined or "browse_text_note" in combined or "browse_list_note" in combined:
            return False
        return any(
            marker in combined
            for marker in (
                "create a note",
                "take a note",
                "new text note",
                "new_note_button",
            )
        )

    @classmethod
    def _tap_target_is_clickable(
        cls,
        args: Dict[str, Any],
        screen_summary: Optional[Dict[str, Any]],
    ) -> bool:
        if not isinstance(screen_summary, dict):
            return True
        if not screen_summary.get("possible_targets"):
            return True
        target_id = str((args or {}).get("target_id") or "").strip()
        action_id = str((args or {}).get("action_id") or "").strip()
        if not target_id and action_id.startswith("tap:"):
            target_id = action_id.split(":", 1)[1]
        if target_id:
            for candidate in screen_summary.get("possible_targets", []):
                if (
                    isinstance(candidate, dict)
                    and str(candidate.get("target_id") or "").strip() == target_id
                    and bool(candidate.get("clickable"))
                ):
                    return True
            return False

        targets = [
            str((args or {}).get("target") or "").strip(),
            str((args or {}).get("target_key") or "").strip(),
        ]
        if not any(targets):
            return False
        target_key = str((args or {}).get("target_key") or "").strip()
        for candidate in screen_summary.get("possible_targets", []):
            if not bool((candidate or {}).get("clickable")):
                continue
            if target_key and not cls._target_key_alias_matches(candidate or {}, target_key):
                continue
            for target in targets:
                if cls._candidate_matches(candidate or {}, target):
                    return True
        return False

    @staticmethod
    def _type_target_is_valid(
        args: Dict[str, Any],
        screen_summary: Optional[Dict[str, Any]],
    ) -> bool:
        if not isinstance(screen_summary, dict):
            return True
        if not screen_summary.get("possible_targets"):
            return True
        target_id = str((args or {}).get("target_id") or "").strip()
        action_id = str((args or {}).get("action_id") or "").strip()
        if not target_id and action_id.startswith("type:"):
            target_id = action_id.split(":", 1)[1]
        if not target_id:
            return True
        for candidate in screen_summary.get("possible_targets", []):
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("target_id") or "").strip() != target_id:
                continue
            return "edittext" in str(candidate.get("class_name") or "").lower()
        return False

    @staticmethod
    def _context_screen_targets(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        validation_summary = context.get("_validation_screen_summary")
        if isinstance(validation_summary, dict) and validation_summary.get("possible_targets"):
            return validation_summary
        screen_summary = context.get("screen_summary")
        if not isinstance(screen_summary, dict):
            return None
        if screen_summary.get("possible_targets"):
            return screen_summary
        top_targets = context.get("top_targets")
        if isinstance(top_targets, list) and top_targets:
            enriched = dict(screen_summary)
            enriched["possible_targets"] = top_targets
            return enriched
        return screen_summary
