from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.context_builder import ContextBuilder
from app.demo_config import DemoMessageConfig, build_demo_message_config
from app.reminder_parser import parse_reminder_task
from app.state import AgentState
from app.task_types import (
    TASK_CREATE_REMINDER,
    TASK_EXTRACT_AND_COPY,
    TASK_GUIDED_UI_TASK,
    TASK_READ_CURRENT_SCREEN,
    TASK_SEND_MESSAGE,
    TASK_UNSUPPORTED,
    detect_task_type,
    extract_contact_query,
    extract_message_body,
    parse_extract_task,
    parse_guided_ui_task,
    parse_screen_read_task,
)


class PlannerError(RuntimeError):
    pass


@dataclass
class PlanStep(object):
    skill: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan(object):
    goal: str
    steps: List[PlanStep]
    task_type: str = TASK_UNSUPPORTED
    status: str = "ready"
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "goal": self.goal,
            "task_type": self.task_type,
            "status": self.status,
            "steps": [asdict(step) for step in self.steps],
        }
        if self.message:
            payload["message"] = self.message
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class RuleBasedPlanner(object):
    """Deterministic planner for the supported v0.2 task flows."""

    APP_ALIASES = {
        "messages": "com.google.android.apps.messaging",
        "message": "com.google.android.apps.messaging",
        "sms": "com.google.android.apps.messaging",
        "notes": "com.google.android.keep",
        "keep": "com.google.android.keep",
        "calendar": "com.google.android.calendar",
        "reminder": "com.google.android.calendar",
        "settings": "com.android.settings",
        "chrome": "com.android.chrome",
    }

    def __init__(self, demo_config: Optional[DemoMessageConfig] = None) -> None:
        self.demo_config = demo_config or build_demo_message_config()

    def plan(
        self,
        task_text: str,
        context: Dict[str, Any],
        task_type_override: Optional[str] = None,
    ) -> ExecutionPlan:
        task_type = detect_task_type(task_text, override=task_type_override)
        if task_type == TASK_SEND_MESSAGE:
            return self._plan_send_message(task_text, context)
        if task_type == TASK_EXTRACT_AND_COPY:
            return self._plan_extract_and_copy(task_text, context)
        if task_type == TASK_CREATE_REMINDER:
            return self._plan_create_reminder(task_text, context)
        if task_type == TASK_READ_CURRENT_SCREEN:
            return self._plan_read_current_screen(task_text)
        if task_type == TASK_GUIDED_UI_TASK:
            return self._plan_guided_ui_task(task_text)
        return ExecutionPlan(
            goal=task_text,
            task_type=TASK_UNSUPPORTED,
            status="unsupported",
            message="This repo currently supports send_message, extract_and_copy, and create_reminder only.",
            steps=[],
        )

    def create_demo_message_plan(self) -> ExecutionPlan:
        return self._build_message_plan(
            goal="Send a template message to {0}".format(self.demo_config.contact_name),
            contact=self.demo_config.contact_name,
            message=self.demo_config.message_text,
            phone_number=self.demo_config.phone_number,
        )

    def _plan_send_message(self, task_text: str, context: Dict[str, Any]) -> ExecutionPlan:
        contact_query = extract_contact_query(task_text)
        remembered_contacts = context.get("remembered_contacts") or []
        known_contact = context.get("known_contact") or (remembered_contacts[0] if remembered_contacts else {})
        contact_name = contact_query or known_contact.get("contact_name") or self.demo_config.contact_name
        message_text = extract_message_body(task_text) or self.demo_config.message_text
        phone_number = known_contact.get("phone_number") or self.demo_config.phone_number
        return self._build_message_plan(
            goal=task_text,
            contact=contact_name,
            message=message_text,
            phone_number=phone_number,
        )

    def _build_message_plan(
        self,
        goal: str,
        contact: str,
        message: str,
        phone_number: Optional[str] = None,
    ) -> ExecutionPlan:
        if phone_number:
            steps = [
                PlanStep(
                    "open_message_thread",
                    {
                        "phone_number": phone_number,
                        "message_text": message,
                        "expect_page": "message_thread",
                        "expect_target": "send",
                    },
                ),
                PlanStep("read_screen", {"prefix": "message_thread_open"}),
                PlanStep("confirm_action", {"prompt": "Confirm before sending the template message?"}),
                PlanStep(
                    "tap",
                    {
                        "target": "send",
                        "target_key": "send",
                        "expect_page": "message_thread",
                    },
                ),
                PlanStep("read_screen", {"prefix": "message_sent"}),
            ]
        else:
            steps = [
                PlanStep(
                    "open_app",
                    {
                        "package_name": self.demo_config.package_name,
                        "activity_name": self.demo_config.activity_name,
                        "expect_page": "messages_home",
                        "expect_target": "search",
                    },
                ),
                PlanStep("read_screen", {"prefix": "messages_home"}),
                PlanStep(
                    "search_in_app",
                    {
                        "query": contact,
                        "target_key": "search",
                        "expect_target": contact,
                    },
                ),
                PlanStep(
                    "tap",
                    {
                        "target": contact,
                        "target_key": "contact_result",
                        "expect_page": "message_thread",
                        "expect_target": "send",
                    },
                ),
                PlanStep("tap", {"target": "message", "target_key": "message_input"}),
                PlanStep(
                    "type_text",
                    {
                        "text": message,
                        "expect_page": "message_thread",
                        "expect_target": "send",
                    },
                ),
                PlanStep("confirm_action", {"prompt": "Confirm before sending the template message?"}),
                PlanStep(
                    "tap",
                    {
                        "target": "send",
                        "target_key": "send",
                        "expect_page": "message_thread",
                    },
                ),
                PlanStep("read_screen", {"prefix": "message_sent"}),
            ]

        return ExecutionPlan(goal=goal, task_type=TASK_SEND_MESSAGE, steps=steps)

    def _plan_extract_and_copy(self, task_text: str, context: Dict[str, Any]) -> ExecutionPlan:
        parse_result = parse_extract_task(task_text)
        package_name = parse_result["target_package"]
        return ExecutionPlan(
            goal=task_text,
            task_type=TASK_EXTRACT_AND_COPY,
            steps=[
                PlanStep("read_screen", {"prefix": "extract_source"}),
                PlanStep(
                    "extract_value",
                    {
                        "field_hint": parse_result["field_hint"],
                        "artifact_key": "extracted_value",
                    },
                ),
                PlanStep(
                    "open_app",
                    {
                        "package_name": package_name,
                        "expect_page": parse_result["target_home_page"],
                        "expect_target": parse_result["target_entry_target"],
                    },
                ),
                PlanStep("read_screen", {"prefix": parse_result["target_home_page"]}),
                PlanStep(
                    "tap",
                    {
                        "target": parse_result["target_entry_target"],
                        "target_key": parse_result["target_entry_key"],
                        "prefer_fallback": True,
                    },
                ),
                PlanStep(
                    "tap",
                    {
                        "target": "text",
                        "target_key": "new_text_note",
                        "skip_if_page": parse_result["target_editor_page"],
                        "expect_page": parse_result["target_editor_page"],
                        "prefer_fallback": True,
                    },
                ),
                PlanStep(
                    "type_text",
                    {
                        "text": "{extracted_value}",
                        "expect_page": parse_result["target_editor_page"],
                    },
                ),
                PlanStep("read_screen", {"prefix": parse_result["target_editor_page"]}),
            ],
        )

    def _plan_create_reminder(self, task_text: str, context: Dict[str, Any]) -> ExecutionPlan:
        parsed = parse_reminder_task(task_text)
        return ExecutionPlan(
            goal=task_text,
            task_type=TASK_CREATE_REMINDER,
            steps=[
                PlanStep(
                    "open_calendar_event",
                    {
                        "title": parsed["title"],
                        "time_text": parsed["time_text"],
                        "begin_time_ms": parsed["begin_time_ms"],
                        "package_name": self.demo_config.calendar_package_name,
                        "expect_page": "reminder_editor",
                        "expect_target": "save",
                    },
                ),
                PlanStep("read_screen", {"prefix": "reminder_editor"}),
                PlanStep(
                    "confirm_action",
                    {
                        "prompt": "Confirm before saving the reminder?",
                        "skip_if_page": "reminder_saved",
                    },
                ),
                PlanStep(
                    "tap",
                    {
                        "target": "save",
                        "target_key": "save",
                        "skip_if_page": "reminder_saved",
                    },
                ),
                PlanStep("read_screen", {"prefix": "reminder_saved"}),
            ],
        )

    def _plan_read_current_screen(self, task_text: str) -> ExecutionPlan:
        read_task = parse_screen_read_task(task_text)
        return ExecutionPlan(
            goal=task_text,
            task_type=TASK_READ_CURRENT_SCREEN,
            steps=[
                PlanStep("read_screen", {"prefix": "read_current_screen"}),
                PlanStep(
                    "reason_about_page",
                    {
                        "goal": task_text,
                        "task_type": TASK_READ_CURRENT_SCREEN,
                        "field_hint": read_task.get("field_hint"),
                    },
                ),
            ],
        )

    def _plan_guided_ui_task(self, task_text: str) -> ExecutionPlan:
        guided_task = parse_guided_ui_task(task_text)
        steps = []
        if guided_task.get("target_package"):
            steps.append(
                PlanStep(
                    "open_app",
                    {
                        "package_name": guided_task["target_package"],
                    },
                )
            )
        steps.extend(
            [
                PlanStep("read_screen", {"prefix": "guided_ui_task"}),
                PlanStep(
                    "reason_about_page",
                    {
                        "goal": task_text,
                        "task_type": TASK_GUIDED_UI_TASK,
                    },
                ),
            ]
        )
        return ExecutionPlan(
            goal=task_text,
            task_type=TASK_GUIDED_UI_TASK,
            steps=steps,
        )


class OpenAIPlanner(object):
    """Optional planner path that still produces the same plan structure."""

    SYSTEM_PROMPT = (
        "You are planning bounded Android GUI tasks. "
        "Return strict JSON only with keys goal, task_type, status, message, and steps. "
        "Allowed task_type values: send_message, extract_and_copy, create_reminder, read_current_screen, guided_ui_task, unsupported. "
        "Each step must use one allowed skill from: "
        "open_app, open_message_thread, open_calendar_event, tap, swipe, type_text, back, wait, "
        "read_screen, extract_value, confirm_action, search_in_app, reason_about_page."
    )

    def __init__(self, model: Optional[str] = None) -> None:
        self.model = model or os.environ.get("AGENT_MODEL", "gpt-4.1-mini")

    def plan(
        self,
        task_text: str,
        context: Dict[str, Any],
        task_type_override: Optional[str] = None,
    ) -> ExecutionPlan:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise PlannerError("OPENAI_API_KEY is not set.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise PlannerError("openai package is not installed.") from exc

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": task_text,
                            "task_type_override": task_type_override,
                            "context": context,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise PlannerError("Model returned empty planning content.")
        try:
            payload = json.loads(content)
        except ValueError as exc:
            raise PlannerError("Planner returned non-JSON content.") from exc
        return ExecutionPlan(
            goal=payload["goal"],
            task_type=payload.get("task_type", detect_task_type(task_text, task_type_override)),
            status=payload.get("status", "ready"),
            message=payload.get("message"),
            steps=[PlanStep(**step) for step in payload.get("steps", [])],
        )


class TaskPlanner(object):
    def __init__(
        self,
        context_builder: ContextBuilder,
        backend: str = "rule",
        model: Optional[str] = None,
        demo_config: Optional[DemoMessageConfig] = None,
    ) -> None:
        self.context_builder = context_builder
        self.backend = backend
        self.rule_planner = RuleBasedPlanner(demo_config=demo_config)
        self.api_planner = OpenAIPlanner(model=model)

    def create_plan(
        self,
        task_text: str,
        state: AgentState,
        task_type_override: Optional[str] = None,
    ) -> ExecutionPlan:
        task_type = detect_task_type(task_text, override=task_type_override)
        context = self.context_builder.build(goal=task_text, state=state, task_type=task_type)
        if self.backend == "openai":
            try:
                return self.api_planner.plan(task_text, context, task_type_override=task_type)
            except PlannerError:
                return self.rule_planner.plan(task_text, context, task_type_override=task_type)
        return self.rule_planner.plan(task_text, context, task_type_override=task_type)
