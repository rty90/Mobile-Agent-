from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from app.extraction import extract_key_value
from app.page_reader import build_page_bundle
from app.reasoning_orchestrator import ReasoningOrchestrator
from app.reasoning_validator import ReasoningValidator
from app.task_types import (
    TASK_CREATE_REMINDER,
    TASK_EXTRACT_AND_COPY,
    TASK_GUIDED_UI_TASK,
    TASK_READ_CURRENT_SCREEN,
    TASK_SEND_MESSAGE,
    contains_high_risk_keyword,
    extract_message_body,
    parse_extract_task,
    parse_guided_ui_task,
    parse_screen_read_task,
)


class PageReasonerError(RuntimeError):
    pass


def _top_targets(screen_summary: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    targets = []
    seen = set()
    for candidate in screen_summary.get("possible_targets", []):
        if isinstance(candidate, dict):
            label = (candidate.get("label") or "").strip()
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
        if len(targets) >= limit:
            break
    return targets


def _summary_text(screen_summary: Dict[str, Any], limit: int = 4) -> str:
    visible_text = [str(item).strip() for item in screen_summary.get("visible_text", []) if str(item).strip()]
    if not visible_text:
        return "No visible text detected on the current page."
    return " | ".join(visible_text[:limit])


def _first_target_label(screen_summary: Dict[str, Any], keywords: List[str]) -> Optional[str]:
    for candidate in screen_summary.get("possible_targets", []):
        if isinstance(candidate, dict):
            label = str(candidate.get("label", "")).strip()
        else:
            label = str(candidate).strip()
        lowered = label.lower()
        if label and any(keyword in lowered for keyword in keywords):
            return label
    return None


def _keep_create_note_target(screen_summary: Dict[str, Any]) -> Optional[str]:
    preferred_matches = []
    fallback_matches = []
    for candidate in screen_summary.get("possible_targets", []):
        if not isinstance(candidate, dict) or not bool(candidate.get("clickable")):
            continue
        label = str(candidate.get("label") or "").strip()
        content_desc = str(candidate.get("content_desc") or "").strip()
        resource_id = str(candidate.get("resource_id") or "").strip()
        combined = " ".join([label, content_desc, resource_id]).lower()
        if not label and not content_desc:
            continue
        if "sort note" in combined or "browse_text_note" in combined or "browse_list_note" in combined:
            continue
        display_label = label or content_desc
        if "new_note_button" in combined or "new text note" in combined:
            preferred_matches.append(display_label)
            continue
        if "take a note" in combined or "create a note" in combined:
            fallback_matches.append(display_label)
    return (preferred_matches or fallback_matches or [None])[0]


def _is_read_only_guided_request(goal: str) -> bool:
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


class RuleBasedPageReasoner(object):
    def reason(
        self,
        goal: str,
        task_type: str,
        screen_summary: Dict[str, Any],
        screenshot_path: Optional[str] = None,
        recent_actions: Optional[List[Dict[str, Any]]] = None,
        relevant_memories: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        page_bundle = build_page_bundle(screen_summary, screenshot_path)
        summary = page_bundle["screen_summary"]
        reasoning = {
            "page_type": summary.get("page") or "unknown_page",
            "summary": _summary_text(summary),
            "facts": self._build_facts(goal, task_type, summary),
            "targets": _top_targets(summary),
            "next_action": None,
            "confidence": 0.65,
            "requires_confirmation": False,
        }

        if task_type == TASK_GUIDED_UI_TASK:
            reasoning["next_action"] = self._suggest_next_action(goal, summary)
            reasoning["confidence"] = 0.75 if reasoning["next_action"] else 0.60

        if task_type == TASK_SEND_MESSAGE and contains_high_risk_keyword(goal):
            reasoning["requires_confirmation"] = True
        return reasoning

    def _build_facts(
        self,
        goal: str,
        task_type: str,
        screen_summary: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        facts: List[Dict[str, str]] = []
        visible_text = [str(item).strip() for item in screen_summary.get("visible_text", []) if str(item).strip()]

        if task_type in (TASK_EXTRACT_AND_COPY, TASK_READ_CURRENT_SCREEN):
            field_hint = parse_extract_task(goal).get("field_hint")
            if task_type == TASK_READ_CURRENT_SCREEN:
                read_request = parse_screen_read_task(goal)
                field_hint = read_request.get("field_hint") or field_hint
            if field_hint:
                extracted = extract_key_value(screen_summary, field_hint=field_hint)
                if extracted:
                    facts.append(
                        {
                            "type": "extracted_value",
                            "field": field_hint,
                            "value": extracted,
                        }
                    )

        for item in visible_text[:3]:
            facts.append({"type": "visible_text", "value": item})

        return facts[:5]

    def _suggest_next_action(self, goal: str, screen_summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        page = screen_summary.get("page")
        labels = []
        for item in screen_summary.get("possible_targets", []):
            if isinstance(item, dict):
                labels.append(str(item.get("label", "")).lower())
            else:
                labels.append(str(item).lower())
        labels.extend(str(item).lower() for item in screen_summary.get("visible_text", []))
        guided_request = parse_guided_ui_task(goal)

        if _is_read_only_guided_request(goal):
            return None

        if page == "keep_home" and any("get started" in label for label in labels):
            return {
                "skill": "tap",
                "args": {
                    "target": "Get started",
                },
            }

        if page == "keep_home" and any("needs permission to send notifications" in label for label in labels):
            return {
                "skill": "tap",
                "args": {
                    "target": "Cancel",
                },
            }

        if page == "keep_home":
            note_label = _keep_create_note_target(screen_summary)
            if not note_label and not any("note" in label for label in labels):
                note_label = None
            if not note_label:
                return None
            return {
                "skill": "tap",
                "args": {
                    "target": note_label,
                    "target_key": "new_note",
                    "prefer_fallback": True,
                },
            }

        if page == "messages_home" and any("search" in label for label in labels):
            return {
                "skill": "tap",
                "args": {
                    "target": "search",
                    "target_key": "search",
                },
            }

        if page == "keep_editor":
            text = extract_message_body(goal)
            if text and not any(text.lower() in label for label in labels):
                for target in screen_summary.get("possible_targets", []):
                    if not isinstance(target, dict):
                        continue
                    combined = " ".join(
                        str(target.get(key) or "").lower()
                        for key in ("label", "resource_id", "content_desc", "class_name")
                    )
                    if "edit_note_text" in combined or combined.strip() == "note":
                        args = {
                            "target": target.get("label") or "Note",
                            "text": text,
                        }
                        if target.get("target_id"):
                            args["target_id"] = target["target_id"]
                            args["action_id"] = "type:{0}".format(target["target_id"])
                        return {
                            "skill": "type_text",
                            "args": args,
                        }
            return None

        if guided_request.get("target_package") and not screen_summary.get("app"):
            return {
                "skill": "open_app",
                "args": {"package_name": guided_request["target_package"]},
            }

        return None


class LocalPageReasoner(object):
    SYSTEM_PROMPT = (
        "You are a compact Android page reasoner. "
        "Return strict JSON with page_type, summary, facts, targets, next_action, confidence, requires_confirmation. "
        "next_action must be null or use one registered skill only."
    )

    def __init__(self, fallback_reasoner: Optional[RuleBasedPageReasoner] = None) -> None:
        self.fallback_reasoner = fallback_reasoner or RuleBasedPageReasoner()

    def reason(
        self,
        goal: str,
        task_type: str,
        screen_summary: Dict[str, Any],
        screenshot_path: Optional[str] = None,
        recent_actions: Optional[List[Dict[str, Any]]] = None,
        relevant_memories: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        base_url = os.environ.get("LOCAL_REASONER_BASE_URL")
        model_name = os.environ.get("LOCAL_REASONER_MODEL")
        if not base_url or not model_name:
            return self.fallback_reasoner.reason(
                goal=goal,
                task_type=task_type,
                screen_summary=screen_summary,
                screenshot_path=screenshot_path,
                recent_actions=recent_actions,
                relevant_memories=relevant_memories,
            )

        try:
            from openai import OpenAI
        except ImportError:
            return self.fallback_reasoner.reason(
                goal=goal,
                task_type=task_type,
                screen_summary=screen_summary,
                screenshot_path=screenshot_path,
                recent_actions=recent_actions,
                relevant_memories=relevant_memories,
            )

        client = OpenAI(base_url=base_url, api_key=os.environ.get("LOCAL_REASONER_API_KEY", "local"))
        response = client.chat.completions.create(
            model=model_name,
            temperature=0,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": goal,
                            "task_type": task_type,
                            "screen_summary": screen_summary,
                            "recent_actions": recent_actions or [],
                            "relevant_memories": relevant_memories or [],
                            "screenshot_path": screenshot_path,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise PageReasonerError("Local page reasoner returned empty content.")
        payload = json.loads(content)
        return payload


class OpenAIPageReasoner(LocalPageReasoner):
    def reason(
        self,
        goal: str,
        task_type: str,
        screen_summary: Dict[str, Any],
        screenshot_path: Optional[str] = None,
        recent_actions: Optional[List[Dict[str, Any]]] = None,
        relevant_memories: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        api_key = os.environ.get("OPENAI_API_KEY")
        model_name = os.environ.get("OPENAI_REASONER_MODEL", "gpt-4.1-mini")
        if not api_key:
            return self.fallback_reasoner.reason(
                goal=goal,
                task_type=task_type,
                screen_summary=screen_summary,
                screenshot_path=screenshot_path,
                recent_actions=recent_actions,
                relevant_memories=relevant_memories,
            )

        try:
            from openai import OpenAI
        except ImportError:
            return self.fallback_reasoner.reason(
                goal=goal,
                task_type=task_type,
                screen_summary=screen_summary,
                screenshot_path=screenshot_path,
                recent_actions=recent_actions,
                relevant_memories=relevant_memories,
            )

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model_name,
            temperature=0,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": goal,
                            "task_type": task_type,
                            "screen_summary": screen_summary,
                            "recent_actions": recent_actions or [],
                            "relevant_memories": relevant_memories or [],
                            "screenshot_path": screenshot_path,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise PageReasonerError("OpenAI page reasoner returned empty content.")
        payload = json.loads(content)
        return payload


class PageReasoner(object):
    def __init__(
        self,
        backend: str = "rule",
        orchestrator: Optional[ReasoningOrchestrator] = None,
    ) -> None:
        self.backend = backend
        self.rule_reasoner = RuleBasedPageReasoner()
        self.local_reasoner = LocalPageReasoner(fallback_reasoner=self.rule_reasoner)
        self.openai_reasoner = OpenAIPageReasoner(fallback_reasoner=self.rule_reasoner)
        self.orchestrator = orchestrator
        if self.orchestrator is None and backend == "stack":
            self.orchestrator = self._build_default_orchestrator()

    def reason(
        self,
        goal: str,
        task_type: str,
        screen_summary: Dict[str, Any],
        screenshot_path: Optional[str] = None,
        recent_actions: Optional[List[Dict[str, Any]]] = None,
        relevant_memories: Optional[List[Dict[str, Any]]] = None,
        normalized_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self.backend == "stack":
            if not self.orchestrator:
                raise PageReasonerError("Stack reasoner requires a reasoning orchestrator.")
            result = self.orchestrator.resolve(
                goal=goal,
                task_type=task_type,
                screen_summary=screen_summary,
                screenshot_path=screenshot_path,
                recent_actions=recent_actions,
                relevant_memories=relevant_memories,
                normalized_context=normalized_context,
            )
            legacy = dict(result["legacy_reasoning"])
            legacy["trace_path"] = result["trace_path"]
            return legacy
        if self.backend == "local":
            return self.local_reasoner.reason(
                goal=goal,
                task_type=task_type,
                screen_summary=screen_summary,
                screenshot_path=screenshot_path,
                recent_actions=recent_actions,
                relevant_memories=relevant_memories,
            )
        if self.backend == "openai":
            return self.openai_reasoner.reason(
                goal=goal,
                task_type=task_type,
                screen_summary=screen_summary,
                screenshot_path=screenshot_path,
                recent_actions=recent_actions,
                relevant_memories=relevant_memories,
            )
        return self.rule_reasoner.reason(
            goal=goal,
            task_type=task_type,
            screen_summary=screen_summary,
            screenshot_path=screenshot_path,
            recent_actions=recent_actions,
            relevant_memories=relevant_memories,
        )

    def _build_default_orchestrator(self) -> ReasoningOrchestrator:
        from app.model_runtime import ModelRuntime
        from app.trace_bus import TraceBus

        validator = ReasoningValidator(min_confidence=float(os.environ.get("REASONING_MIN_CONFIDENCE", "0.70")))
        runtime = ModelRuntime()
        trace_bus = TraceBus(console_enabled=False)
        return ReasoningOrchestrator(
            validator=validator,
            model_runtime=runtime,
            trace_bus=trace_bus,
            rule_fallback=self.rule_reasoner.reason,
        )
