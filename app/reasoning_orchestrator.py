from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.model_runtime import ModelRuntime
from app.reasoning_validator import ReasoningValidator
from app.schemas.reasoning_decision import ReasoningDecision
from app.trace_bus import TraceBus
from app.task_types import TASK_GUIDED_UI_TASK


class ReasoningOrchestrator(object):
    SYSTEM_PROMPT = (
        "You are a bounded Android GUI reasoning model. "
        "Return strict JSON only. "
        "Allowed decisions: execute, cloud_review, vl_review, unsupported. "
        "Allowed skills: open_app, tap, swipe, type_text, back, wait, search_in_app. "
        "Never output shell commands, adb commands, or raw chain-of-thought. "
        "Use skill=null only when the task is read-only and no action is needed. "
        "Output exactly one JSON object with these top-level keys only: "
        "decision, task_type, skill, args, confidence, requires_confirmation, reason_summary. "
        "args must always be an object, even when empty. "
        "reason_summary must always be a short string. "
        "Do not use top-level keys such as action, target, resource_id, bounds, step, or explanation. "
        "For a tap action, use skill='tap' and put target details inside args. "
        "For a read-only task, return decision='execute', skill=null, args={}. "
        "Example action output: "
        "{\"decision\":\"execute\",\"task_type\":\"guided_ui_task\",\"skill\":\"tap\",\"args\":{\"target\":\"Create a note\",\"target_key\":\"new_note\"},\"confidence\":0.90,\"requires_confirmation\":false,\"reason_summary\":\"The Create a note target is visible.\"} "
        "Example read-only output: "
        "{\"decision\":\"execute\",\"task_type\":\"guided_ui_task\",\"skill\":null,\"args\":{},\"confidence\":0.82,\"requires_confirmation\":false,\"reason_summary\":\"The current page is a Keep home screen with visible notes.\"}"
    )

    def __init__(
        self,
        validator: ReasoningValidator,
        model_runtime: ModelRuntime,
        trace_bus: TraceBus,
        rule_fallback: Callable[..., Dict[str, Any]],
    ) -> None:
        self.validator = validator
        self.model_runtime = model_runtime
        self.trace_bus = trace_bus
        self.rule_fallback = rule_fallback
        self.request_timeout_seconds = float(os.environ.get("REASONING_REQUEST_TIMEOUT_SECONDS", "20"))
        self.disable_local_text_after_failure = str(
            os.environ.get("REASONING_DISABLE_LOCAL_TEXT_AFTER_FAILURE", "1")
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._local_text_degraded = False

    def resolve(
        self,
        goal: str,
        task_type: str,
        screen_summary: Dict[str, Any],
        screenshot_path: Optional[str] = None,
        recent_actions: Optional[List[Dict[str, Any]]] = None,
        relevant_memories: Optional[List[Dict[str, Any]]] = None,
        normalized_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context_payload = normalized_context or self._build_request_payload(
            goal=goal,
            task_type=task_type,
            screen_summary=screen_summary,
            screenshot_path=screenshot_path,
            recent_actions=recent_actions,
            relevant_memories=relevant_memories,
        )

        shortcut_result = self._resolve_memory_shortcut(
            goal=goal,
            task_type=task_type,
            context_payload=context_payload,
        )
        if self._is_resolved(shortcut_result["decision"], goal, task_type):
            return self._finish(shortcut_result["decision"], screen_summary)

        local_text_result = self._resolve_local_text(goal, task_type, context_payload)
        if self._is_resolved(local_text_result["decision"], goal, task_type):
            return self._finish(local_text_result["decision"], screen_summary)

        cloud_result = self._resolve_cloud_review(goal, task_type, context_payload, screenshot_path)
        if self._is_resolved(cloud_result["decision"], goal, task_type):
            return self._finish(cloud_result["decision"], screen_summary)

        local_vl_result = self._resolve_local_vl(goal, task_type, context_payload, screenshot_path)
        if self._is_resolved(local_vl_result["decision"], goal, task_type):
            return self._finish(local_vl_result["decision"], screen_summary)

        rule_decision = self._build_rule_fallback_decision(
            goal=goal,
            task_type=task_type,
            screen_summary=screen_summary,
            screenshot_path=screenshot_path,
            recent_actions=recent_actions,
            relevant_memories=relevant_memories,
        )
        return self._finish(rule_decision, screen_summary)

    def _resolve_local_text(
        self,
        goal: str,
        task_type: str,
        context_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self._local_text_degraded:
            decision = ReasoningDecision(
                decision="unsupported",
                task_type=task_type,
                confidence=0.0,
                reason_summary="Local text reasoning is skipped after an earlier failure in this run.",
                validation_errors=["local text skipped after failure"],
                selected_backend="local_text",
                fallback_used=False,
            )
            self.trace_bus.emit(
                stage="local_text.result",
                backend="local_text",
                success=False,
                confidence=decision.confidence,
                reason_summary=decision.reason_summary,
                fallback_triggered=True,
            )
            self.trace_bus.emit(
                stage="validation.failed",
                backend="local_text",
                success=False,
                confidence=decision.confidence,
                reason_summary="; ".join(decision.validation_errors),
                fallback_triggered=True,
            )
            return {"decision": decision}

        self.trace_bus.emit(
            stage="local_text.start",
            backend="local_text",
            success=True,
            reason_summary="Starting local text reasoning.",
            fallback_triggered=False,
        )
        runtime_state = self.model_runtime.ensure_local_text_service()
        if not runtime_state.get("available"):
            decision = ReasoningDecision(
                decision="unsupported",
                task_type=task_type,
                confidence=0.0,
                reason_summary=str(runtime_state.get("reason") or "Local text service is unavailable."),
                validation_errors=["local text service unavailable"],
                selected_backend="local_text",
                fallback_used=False,
            )
            self.trace_bus.emit(
                stage="local_text.result",
                backend="local_text",
                success=False,
                confidence=decision.confidence,
                reason_summary=decision.reason_summary,
                fallback_triggered=True,
            )
            self.trace_bus.emit(
                stage="validation.failed",
                backend="local_text",
                success=False,
                confidence=decision.confidence,
                reason_summary="; ".join(decision.validation_errors),
                fallback_triggered=True,
            )
            return {"decision": decision}

        try:
            raw_payload = self._call_openai_compatible_text(
                base_url=str(runtime_state["base_url"]),
                api_key=os.environ.get("LOCAL_TEXT_REASONER_API_KEY", "local"),
                model_name=os.environ.get("LOCAL_TEXT_REASONER_MODEL", ModelRuntime.DEFAULT_LOCAL_TEXT_MODEL),
                payload=context_payload,
            )
        except Exception as exc:
            self._maybe_degrade_local_text(exc)
            decision = ReasoningDecision(
                decision="unsupported",
                task_type=task_type,
                confidence=0.0,
                reason_summary="Local text reasoning failed.",
                validation_errors=[str(exc)],
                selected_backend="local_text",
                fallback_used=False,
            )
            self.trace_bus.emit(
                stage="local_text.result",
                backend="local_text",
                success=False,
                confidence=decision.confidence,
                reason_summary=decision.reason_summary,
                fallback_triggered=True,
            )
            self.trace_bus.emit(
                stage="validation.failed",
                backend="local_text",
                success=False,
                confidence=decision.confidence,
                reason_summary="; ".join(decision.validation_errors),
                fallback_triggered=True,
            )
            return {"decision": decision}
        decision = self.validator.validate_payload(
            payload=raw_payload,
            expected_task_type=task_type,
            goal=goal,
            selected_backend="local_text",
            fallback_used=False,
            context=context_payload,
        )
        self.trace_bus.emit(
            stage="local_text.result",
            backend="local_text",
            success=not decision.validation_errors,
            confidence=decision.confidence,
            reason_summary=decision.reason_summary or "Local text reasoning completed.",
            fallback_triggered=not self._is_resolved(decision, goal, task_type),
        )
        if not self._is_resolved(decision, goal, task_type):
            self.trace_bus.emit(
                stage="validation.failed",
                backend="local_text",
                success=False,
                confidence=decision.confidence,
                reason_summary=self._weak_reason(decision, goal, task_type),
                fallback_triggered=True,
            )
        return {"decision": decision}

    def _resolve_memory_shortcut(
        self,
        goal: str,
        task_type: str,
        context_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        shortcut = context_payload.get("ui_shortcut")
        if not isinstance(shortcut, dict) or not shortcut.get("skill"):
            return {
                "decision": ReasoningDecision(
                    decision="unsupported",
                    task_type=task_type,
                    confidence=0.0,
                    reason_summary="No memory shortcut matched the current page.",
                    validation_errors=["memory shortcut unavailable"],
                    selected_backend="memory_rule",
                    fallback_used=False,
                )
            }

        decision = self.validator.validate_payload(
            payload={
                "decision": "execute",
                "task_type": task_type,
                "skill": shortcut.get("skill"),
                "args": dict(shortcut.get("args") or {}),
                "confidence": float(shortcut.get("confidence", 0.98)),
                "requires_confirmation": False,
                "reason_summary": "Verified shortcut matched the current page.",
            },
            expected_task_type=task_type,
            goal=goal,
            selected_backend="memory_rule",
            fallback_used=False,
            context=context_payload,
        )
        self.trace_bus.emit(
            stage="memory_rule.result",
            backend="memory_rule",
            success=not decision.validation_errors,
            confidence=decision.confidence,
            reason_summary=decision.reason_summary or "Memory shortcut resolved the current page.",
            fallback_triggered=not self._is_resolved(decision, goal, task_type),
        )
        return {"decision": decision}

    def _maybe_degrade_local_text(self, exc: Exception) -> None:
        if not self.disable_local_text_after_failure:
            return
        lowered = str(exc).strip().lower()
        if isinstance(exc, TimeoutError) or "timed out" in lowered or "timeout" in lowered:
            self._local_text_degraded = True

    def _resolve_cloud_review(
        self,
        goal: str,
        task_type: str,
        context_payload: Dict[str, Any],
        screenshot_path: Optional[str],
    ) -> Dict[str, Any]:
        self.trace_bus.emit(
            stage="cloud_review.start",
            backend="cloud_reviewer",
            success=True,
            reason_summary="Starting cloud review stage.",
            fallback_triggered=True,
        )
        if not self.model_runtime.cloud_reviewer_configured():
            skipped = ReasoningDecision(
                decision="cloud_review",
                task_type=task_type,
                confidence=0.0,
                reason_summary="Cloud reviewer skipped because it is not configured.",
                validation_errors=["cloud reviewer skipped"],
                selected_backend="cloud_reviewer",
                fallback_used=True,
            )
            self.trace_bus.emit(
                stage="cloud_review.result",
                backend="cloud_reviewer",
                success=False,
                confidence=skipped.confidence,
                reason_summary=skipped.reason_summary,
                fallback_triggered=True,
                extra={"skipped": True},
            )
            return {"decision": skipped}

        try:
            raw_payload = self._call_openai_compatible_review(
                base_url=self.model_runtime.cloud_reviewer_base_url(),
                api_key=self.model_runtime.cloud_reviewer_api_key(),
                model_name=self.model_runtime.cloud_reviewer_model(),
                payload=context_payload,
                screenshot_path=screenshot_path,
            )
        except Exception as exc:
            decision = ReasoningDecision(
                decision="cloud_review",
                task_type=task_type,
                confidence=0.0,
                reason_summary="Cloud reviewer failed.",
                validation_errors=[str(exc)],
                selected_backend="cloud_reviewer",
                fallback_used=True,
            )
            self.trace_bus.emit(
                stage="cloud_review.result",
                backend="cloud_reviewer",
                success=False,
                confidence=decision.confidence,
                reason_summary=decision.reason_summary,
                fallback_triggered=True,
            )
            return {"decision": decision}
        decision = self.validator.validate_payload(
            payload=raw_payload,
            expected_task_type=task_type,
            goal=goal,
            selected_backend="cloud_reviewer",
            fallback_used=True,
            context=context_payload,
        )
        self.trace_bus.emit(
            stage="cloud_review.result",
            backend="cloud_reviewer",
            success=not decision.validation_errors,
            confidence=decision.confidence,
            reason_summary=decision.reason_summary or "Cloud review completed.",
            fallback_triggered=not self._is_resolved(decision, goal, task_type),
        )
        if not self._is_resolved(decision, goal, task_type):
            self.trace_bus.emit(
                stage="validation.failed",
                backend="cloud_reviewer",
                success=False,
                confidence=decision.confidence,
                reason_summary=self._weak_reason(decision, goal, task_type),
                fallback_triggered=True,
            )
        return {"decision": decision}

    def _resolve_local_vl(
        self,
        goal: str,
        task_type: str,
        context_payload: Dict[str, Any],
        screenshot_path: Optional[str],
    ) -> Dict[str, Any]:
        if not self.model_runtime.local_vl_enabled():
            decision = ReasoningDecision(
                decision="vl_review",
                task_type=task_type,
                confidence=0.0,
                reason_summary="Local VL skipped because it is disabled.",
                validation_errors=["local vl disabled"],
                selected_backend="local_vl",
                fallback_used=True,
            )
            return {"decision": decision}

        screenshot_file = Path(str(screenshot_path)) if screenshot_path else None
        if not screenshot_file or not screenshot_file.exists():
            decision = ReasoningDecision(
                decision="vl_review",
                task_type=task_type,
                confidence=0.0,
                reason_summary="Local VL skipped because no screenshot was available.",
                validation_errors=["local vl skipped"],
                selected_backend="local_vl",
                fallback_used=True,
            )
            return {"decision": decision}

        self.trace_bus.emit(
            stage="local_vl.start",
            backend="local_vl",
            success=True,
            reason_summary="Starting local VL fallback.",
            fallback_triggered=True,
        )
        runtime_state = self.model_runtime.ensure_local_vl_service()
        if not runtime_state.get("available"):
            decision = ReasoningDecision(
                decision="vl_review",
                task_type=task_type,
                confidence=0.0,
                reason_summary=str(runtime_state.get("reason") or "Local VL service is unavailable."),
                validation_errors=["local vl service unavailable"],
                selected_backend="local_vl",
                fallback_used=True,
            )
            self.trace_bus.emit(
                stage="local_vl.result",
                backend="local_vl",
                success=False,
                confidence=decision.confidence,
                reason_summary=decision.reason_summary,
                fallback_triggered=True,
            )
            return {"decision": decision}

        try:
            raw_payload = self._call_openai_compatible_vl(
                base_url=str(runtime_state["base_url"]),
                api_key=os.environ.get("LOCAL_VL_REASONER_API_KEY", "local"),
                model_name=os.environ.get("LOCAL_VL_REASONER_MODEL", ModelRuntime.DEFAULT_LOCAL_VL_MODEL),
                payload=context_payload,
                screenshot_path=str(screenshot_file),
            )
        except Exception as exc:
            decision = ReasoningDecision(
                decision="vl_review",
                task_type=task_type,
                confidence=0.0,
                reason_summary="Local VL fallback failed.",
                validation_errors=[str(exc)],
                selected_backend="local_vl",
                fallback_used=True,
            )
            self.trace_bus.emit(
                stage="local_vl.result",
                backend="local_vl",
                success=False,
                confidence=decision.confidence,
                reason_summary=decision.reason_summary,
                fallback_triggered=True,
            )
            return {"decision": decision}
        decision = self.validator.validate_payload(
            payload=raw_payload,
            expected_task_type=task_type,
            goal=goal,
            selected_backend="local_vl",
            fallback_used=True,
            context=context_payload,
        )
        self.trace_bus.emit(
            stage="local_vl.result",
            backend="local_vl",
            success=not decision.validation_errors,
            confidence=decision.confidence,
            reason_summary=decision.reason_summary or "Local VL fallback completed.",
            fallback_triggered=not self._is_resolved(decision, goal, task_type),
        )
        if not self._is_resolved(decision, goal, task_type):
            self.trace_bus.emit(
                stage="validation.failed",
                backend="local_vl",
                success=False,
                confidence=decision.confidence,
                reason_summary=self._weak_reason(decision, goal, task_type),
                fallback_triggered=True,
            )
        return {"decision": decision}

    def _finish(
        self,
        decision: ReasoningDecision,
        screen_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.trace_bus.emit(
            stage="final_decision.selected",
            backend=decision.selected_backend,
            success=decision.decision == "execute" and not decision.validation_errors,
            confidence=decision.confidence,
            reason_summary=decision.reason_summary,
            fallback_triggered=decision.fallback_used,
        )
        return {
            "decision": decision,
            "trace_path": str(self.trace_bus.trace_path),
            "legacy_reasoning": decision.to_legacy_reasoning_payload(screen_summary=screen_summary),
        }

    def _build_rule_fallback_decision(
        self,
        goal: str,
        task_type: str,
        screen_summary: Dict[str, Any],
        screenshot_path: Optional[str],
        recent_actions: Optional[List[Dict[str, Any]]],
        relevant_memories: Optional[List[Dict[str, Any]]],
    ) -> ReasoningDecision:
        rule_reasoning = self.rule_fallback(
            goal=goal,
            task_type=task_type,
            screen_summary=screen_summary,
            screenshot_path=screenshot_path,
            recent_actions=recent_actions,
            relevant_memories=relevant_memories,
        )
        next_action = rule_reasoning.get("next_action") or {}
        return ReasoningDecision(
            decision="execute",
            task_type=task_type,
            skill=next_action.get("skill"),
            args=dict(next_action.get("args") or {}),
            confidence=float(rule_reasoning.get("confidence", 0.6)),
            requires_confirmation=bool(rule_reasoning.get("requires_confirmation", False)),
            reason_summary=str(rule_reasoning.get("summary") or "Rule fallback selected."),
            validation_errors=[],
            selected_backend="rule",
            fallback_used=True,
        )

    def _build_request_payload(
        self,
        goal: str,
        task_type: str,
        screen_summary: Dict[str, Any],
        screenshot_path: Optional[str],
        recent_actions: Optional[List[Dict[str, Any]]],
        relevant_memories: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        return {
            "goal": goal,
            "task_type": task_type,
            "screen_summary": screen_summary,
            "screenshot_path": screenshot_path,
            "recent_actions": recent_actions or [],
            "relevant_memories": relevant_memories or [],
            "ui_shortcut": None,
            "required_output_schema": {
                "decision": "execute | cloud_review | vl_review | unsupported",
                "task_type": task_type,
                "skill": "open_app | tap | swipe | type_text | back | wait | search_in_app | null",
                "args": "object",
                "confidence": "float between 0.0 and 1.0",
                "requires_confirmation": "boolean",
                "reason_summary": "short string",
            },
            "forbidden_top_level_keys": [
                "action",
                "target",
                "resource_id",
                "bounds",
                "step",
                "explanation",
            ],
        }

    def _is_resolved(
        self,
        decision: ReasoningDecision,
        goal: str,
        task_type: str,
    ) -> bool:
        require_action = task_type == TASK_GUIDED_UI_TASK and not self._is_read_only_guided_request(goal)
        return self.validator.is_strong_decision(decision, require_action=require_action)

    @staticmethod
    def _is_read_only_guided_request(goal: str) -> bool:
        normalized = (goal or "").strip().lower()
        return any(
            marker in normalized
            for marker in (
                "tell me what is on",
                "what is on the current page",
                "inspect the current screen",
                "inspect the current page",
                "summarize the current screen",
                "summarize the current page",
                "read the current screen",
                "read the current page",
            )
        )

    def _weak_reason(
        self,
        decision: ReasoningDecision,
        goal: str,
        task_type: str,
    ) -> str:
        if decision.validation_errors:
            return "; ".join(decision.validation_errors)
        if decision.decision != "execute":
            return "Decision requested escalation or unsupported outcome."
        if decision.confidence < self.validator.min_confidence:
            return "Confidence below threshold."
        if task_type == TASK_GUIDED_UI_TASK and not self._is_read_only_guided_request(goal) and not decision.skill:
            return "Action-oriented guided task is missing a bounded skill."
        return "Decision was not strong enough to use directly."

    def _call_openai_compatible_text(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        payload: Dict[str, Any],
    ) -> Any:
        from openai import OpenAI

        client = OpenAI(
            base_url=base_url,
            api_key=api_key or "local",
            timeout=self.request_timeout_seconds,
        )
        response = client.chat.completions.create(
            model=model_name,
            temperature=0,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    def _call_openai_compatible_vl(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        payload: Dict[str, Any],
        screenshot_path: str,
    ) -> Any:
        from openai import OpenAI

        image_url = self._build_data_url(screenshot_path)
        client = OpenAI(
            base_url=base_url,
            api_key=api_key or "local",
            timeout=self.request_timeout_seconds,
        )
        response = client.chat.completions.create(
            model=model_name,
            temperature=0,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": json.dumps(payload, ensure_ascii=False)},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    def _call_openai_compatible_review(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        payload: Dict[str, Any],
        screenshot_path: Optional[str],
    ) -> Any:
        screenshot_file = Path(str(screenshot_path)) if screenshot_path else None
        if screenshot_file and screenshot_file.exists():
            return self._call_openai_compatible_vl(
                base_url=base_url,
                api_key=api_key,
                model_name=model_name,
                payload=payload,
                screenshot_path=str(screenshot_file),
            )
        return self._call_openai_compatible_text(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            payload=payload,
        )

    @staticmethod
    def _build_data_url(screenshot_path: str) -> str:
        file_path = Path(screenshot_path)
        mime_type, _encoding = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "image/png"
        encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
        return "data:{0};base64,{1}".format(mime_type, encoded)
