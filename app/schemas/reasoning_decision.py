from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ReasoningDecision(object):
    decision: str = "unsupported"
    task_type: str = "unsupported"
    skill: Optional[str] = None
    args: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    requires_confirmation: bool = False
    reason_summary: str = ""
    validation_errors: List[str] = field(default_factory=list)
    selected_backend: str = "rule"
    fallback_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_legacy_reasoning_payload(
        self,
        screen_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        screen_summary = screen_summary or {}
        visible_text = [
            str(item).strip()
            for item in screen_summary.get("visible_text", [])
            if str(item).strip()
        ]
        facts = [{"type": "visible_text", "value": item} for item in visible_text[:3]]
        targets = []
        seen = set()
        for candidate in screen_summary.get("possible_targets", []):
            if isinstance(candidate, dict):
                label = str(candidate.get("label", "")).strip()
                resource_id = candidate.get("resource_id")
                clickable = bool(candidate.get("clickable"))
                confidence = float(candidate.get("confidence", 0.0))
            else:
                label = str(candidate).strip()
                resource_id = None
                clickable = False
                confidence = 0.0
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            targets.append(
                {
                    "label": label,
                    "resource_id": resource_id,
                    "clickable": clickable,
                    "confidence": confidence,
                }
            )
            if len(targets) >= 5:
                break

        next_action = None
        if self.skill:
            next_action = {
                "skill": self.skill,
                "args": dict(self.args or {}),
            }

        summary = self.reason_summary.strip()
        if not summary:
            if visible_text:
                summary = " | ".join(visible_text[:4])
            else:
                summary = "No visible text detected on the current page."

        payload = {
            "page_type": screen_summary.get("page") or "unknown_page",
            "summary": summary,
            "facts": facts,
            "targets": targets,
            "next_action": next_action,
            "confidence": float(self.confidence),
            "requires_confirmation": bool(self.requires_confirmation),
            "selected_backend": self.selected_backend,
            "fallback_used": bool(self.fallback_used),
            "validation_errors": list(self.validation_errors),
        }
        return payload
