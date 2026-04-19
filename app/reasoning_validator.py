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
            parsed["_context_screen_summary"] = context.get("screen_summary")
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

        validation_errors = self._validate_decision(decision, expected_task_type, goal)
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

        if decision.confidence < 0.0 or decision.confidence > 1.0:
            errors.append("confidence must be in range 0.0..1.0.")

        if not decision.reason_summary:
            errors.append("reason_summary is required.")

        if contains_high_risk_keyword(goal) and not decision.requires_confirmation:
            errors.append("high-risk tasks must require confirmation.")

        return errors
