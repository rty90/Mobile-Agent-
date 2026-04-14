from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.context_builder import ContextBuilder
from app.demo_config import DemoMessageConfig, build_demo_message_config
from app.state import AgentState


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [asdict(step) for step in self.steps],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class RuleBasedPlanner(object):
    """Small fallback planner for MVP demo tasks."""

    APP_ALIASES = {
        "messages": "com.google.android.apps.messaging",
        "message": "com.google.android.apps.messaging",
        "sms": "com.google.android.apps.messaging",
        "chrome": "com.android.chrome",
        "settings": "com.android.settings",
        "gmail": "com.google.android.gm",
        "notes": "com.google.android.keep",
        "keep": "com.google.android.keep",
        "calendar": "com.google.android.calendar",
    }

    def __init__(self, demo_config: Optional[DemoMessageConfig] = None) -> None:
        self.demo_config = demo_config or build_demo_message_config()

    def plan(self, task_text: str, context: Dict[str, Any]) -> ExecutionPlan:
        normalized = task_text.strip()
        lower = normalized.lower()

        if self._is_message_task(normalized, lower):
            return self._plan_send_message(normalized)
        if "copy" in lower or "extract" in lower or "复制" in normalized or "提取" in normalized:
            return self._plan_copy_info(normalized)
        if "reminder" in lower or "todo" in lower or "待办" in normalized or "提醒" in normalized:
            return self._plan_create_reminder(normalized)
        if "open" in lower or "打开" in normalized:
            return self._plan_open_app(normalized)

        raise PlannerError(
            "RuleBasedPlanner could not map the task. Configure an API planner or rephrase the task."
        )

    def create_demo_message_plan(self) -> ExecutionPlan:
        return self._build_message_plan(
            goal="Send a template message to {0}".format(self.demo_config.contact_name),
            contact=self.demo_config.contact_name,
            message=self.demo_config.message_text,
            phone_number=self.demo_config.phone_number,
        )

    def _is_message_task(self, normalized: str, lower: str) -> bool:
        return (
            "发消息" in normalized
            or "发短信" in normalized
            or "send message" in lower
            or "text " in lower
        )

    def _plan_send_message(self, task_text: str) -> ExecutionPlan:
        contact = self._extract_contact(task_text) or self.demo_config.contact_name
        message = self._extract_quoted_content(task_text) or self.demo_config.message_text
        return self._build_message_plan(
            goal=task_text,
            contact=contact,
            message=message,
            phone_number=self.demo_config.phone_number,
        )

    def _build_message_plan(
        self,
        goal: str,
        contact: str,
        message: str,
        phone_number: Optional[str] = None,
    ) -> ExecutionPlan:
        if phone_number:
            return ExecutionPlan(
                goal=goal,
                steps=[
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
                ],
            )

        package_name = self.demo_config.package_name
        return ExecutionPlan(
            goal=goal,
            steps=[
                PlanStep(
                    "open_app",
                    {
                        "package_name": package_name,
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
            ],
        )

    def _plan_copy_info(self, task_text: str) -> ExecutionPlan:
        extracted = self._extract_quoted_content(task_text) or "captured text"
        return ExecutionPlan(
            goal=task_text,
            steps=[
                PlanStep("read_screen", {}),
                PlanStep("open_app", {"package_name": "com.google.android.keep"}),
                PlanStep("tap", {"target": "new", "target_key": "new_chat"}),
                PlanStep("type_text", {"text": extracted}),
            ],
        )

    def _plan_create_reminder(self, task_text: str) -> ExecutionPlan:
        content = self._extract_quoted_content(task_text) or task_text
        return ExecutionPlan(
            goal=task_text,
            steps=[
                PlanStep("open_app", {"package_name": "com.google.android.calendar"}),
                PlanStep("tap", {"target": "create"}),
                PlanStep("type_text", {"text": content}),
                PlanStep("confirm_action", {"prompt": "Confirm reminder content before saving?"}),
            ],
        )

    def _plan_open_app(self, task_text: str) -> ExecutionPlan:
        lower = task_text.lower()
        package_name = None
        for alias, candidate in self.APP_ALIASES.items():
            if alias in lower:
                package_name = candidate
                break
        if not package_name:
            raise PlannerError("Could not infer app package from task: {0}".format(task_text))
        return ExecutionPlan(goal=task_text, steps=[PlanStep("open_app", {"package_name": package_name})])

    @staticmethod
    def _extract_contact(task_text: str) -> Optional[str]:
        patterns = [
            r"给(.+?)发(?:消息|短信)",
            r"to\s+(.+?)\s+(?:send|text)",
        ]
        for pattern in patterns:
            match = re.search(pattern, task_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _extract_quoted_content(task_text: str) -> Optional[str]:
        for pattern in (r'"([^"]+)"', r"“([^”]+)”", r"'([^']+)'"):
            match = re.search(pattern, task_text)
            if match:
                return match.group(1).strip()
        return None


class OpenAIPlanner(object):
    """
    Optional planner path. It uses the OpenAI SDK only when available.
    The rule-based planner remains the default fallback so the MVP can run today.
    """

    SYSTEM_PROMPT = (
        "You are planning actions for an Android GUI agent. "
        "Return strict JSON only with keys goal and steps. "
        "Each step must use one allowed skill from: "
        "open_app, open_message_thread, tap, swipe, type_text, back, wait, read_screen, confirm_action, search_in_app."
    )

    def __init__(self, model: Optional[str] = None) -> None:
        self.model = model or os.environ.get("AGENT_MODEL", "gpt-4.1-mini")

    def plan(self, task_text: str, context: Dict[str, Any]) -> ExecutionPlan:
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
            steps=[PlanStep(**step) for step in payload["steps"]],
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

    def create_plan(self, task_text: str, state: AgentState) -> ExecutionPlan:
        context = self.context_builder.build(goal=task_text, state=state)
        if self.backend == "openai":
            try:
                return self.api_planner.plan(task_text, context)
            except PlannerError:
                return self.rule_planner.plan(task_text, context)
        return self.rule_planner.plan(task_text, context)
