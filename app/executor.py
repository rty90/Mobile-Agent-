from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from app.memory import SQLiteMemory
from app.planner import ExecutionPlan, PlanStep
from app.skills.base import SkillContext
from app.skills.read_screen import read_screen_summary
from app.skills.targeting import find_semantic_target
from app.state import AgentState
from app.utils.logger import log_action
from app.utils.screenshot import ScreenshotManager


class Executor(object):
    """Executes planner steps with state updates, logging, screenshots, and minimal recovery."""

    def __init__(
        self,
        adb,
        state: AgentState,
        logger,
        screenshot_manager: ScreenshotManager,
        skill_registry: Mapping[str, Any],
        memory: Optional[SQLiteMemory] = None,
        runtime_config: Any = None,
    ) -> None:
        self.adb = adb
        self.state = state
        self.logger = logger
        self.screenshot_manager = screenshot_manager
        self.skill_registry = dict(skill_registry)
        self.memory = memory
        self.runtime_config = runtime_config

    def _context(self) -> SkillContext:
        return SkillContext(
            adb=self.adb,
            state=self.state,
            logger=self.logger,
            screenshot_manager=self.screenshot_manager,
            registry=self.skill_registry,
            runtime_config=self.runtime_config,
        )

    def execute_plan(self, plan: ExecutionPlan) -> Dict[str, Any]:
        self.state.start_task(plan.goal, task_type=plan.task_type)
        context = self._context()
        step_results = []

        for index, step in enumerate(plan.steps, start=1):
            result = self._execute_step(step, context, index)
            step_results.append(result)
            if not result["success"]:
                break

        final_result = {
            "goal": plan.goal,
            "task_type": plan.task_type,
            "status": plan.status,
            "success": all(item["success"] for item in step_results) if step_results else False,
            "steps": step_results,
            "needs_replan": self.state.needs_replan,
            "state": self.state.to_dict(),
        }
        if plan.message:
            final_result["message"] = plan.message
        self._record_trajectory(final_result)
        return final_result

    def _execute_step(
        self, step: PlanStep, context: SkillContext, step_index: int
    ) -> Dict[str, Any]:
        resolved_step = PlanStep(step.skill, self._resolve_args(step.args))
        result = self._run_skill(resolved_step, context)
        result = self._finalize_result(resolved_step, result, step_index)
        if result["success"]:
            return result

        if self._should_attempt_recovery(resolved_step, result):
            recovered = self._attempt_recovery(resolved_step, context, step_index)
            if recovered["success"]:
                return recovered

        return result

    def _run_skill(self, step: PlanStep, context: SkillContext) -> Dict[str, Any]:
        skill = self.skill_registry.get(step.skill)
        if not skill:
            return {
                "success": False,
                "action": step.skill,
                "detail": "Unknown skill: {0}".format(step.skill),
                "screenshot_path": None,
                "data": {},
            }
        return skill.execute(step.args, context)

    def _resolve_args(self, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return value.format(**self.state.artifacts)
            except KeyError:
                return value
        if isinstance(value, dict):
            return dict((key, self._resolve_args(item)) for key, item in value.items())
        if isinstance(value, list):
            return [self._resolve_args(item) for item in value]
        return value

    def _refresh_screen(self, prefix: str) -> Dict[str, Any]:
        summary = read_screen_summary(
            self.adb,
            "data/tmp/{0}.xml".format(prefix),
            runtime_config=self.runtime_config,
        )
        self.state.update_screen_summary(summary)
        return summary

    def _evaluate_expectations(self, step: PlanStep, summary: Dict[str, Any]) -> Optional[str]:
        expected_page = step.args.get("expect_page")
        if expected_page and summary.get("page") != expected_page:
            return "Expected page '{0}', got '{1}'.".format(expected_page, summary.get("page"))

        expected_target = step.args.get("expect_target")
        if expected_target and not find_semantic_target(summary, str(expected_target)):
            return "Expected target '{0}' is not visible.".format(expected_target)

        return None

    def _finalize_result(self, step: PlanStep, result: Dict[str, Any], step_index: int) -> Dict[str, Any]:
        if result.get("success") and step.skill in ("open_app", "tap", "search_in_app", "type_text", "back", "read_screen"):
            summary = self._refresh_screen("post_step_{0:02d}".format(step_index))
            result.setdefault("data", {})
            result["data"]["screen_summary"] = summary

            expectation_error = self._evaluate_expectations(step, summary)
            if expectation_error:
                result["success"] = False
                result["detail"] = expectation_error

        screenshot_path = result.get("screenshot_path")
        if not screenshot_path:
            screenshot = self.screenshot_manager.capture(
                self.adb,
                task_name=self.state.current_task or "default_task",
                prefix="step_{0:02d}_{1}".format(step_index, step.skill),
            )
            screenshot_path = str(screenshot)
            result["screenshot_path"] = screenshot_path

        data = result.get("data") or {}
        artifacts = data.get("artifacts")
        if isinstance(artifacts, dict):
            for key, value in artifacts.items():
                self.state.remember_artifact(key, value)
        page_name = self.state.current_page
        target_name = step.args.get("target") or step.args.get("expect_target")
        if isinstance(data.get("screen_summary"), dict):
            page_name = data["screen_summary"].get("page", page_name)

        self.state.record_step(
            action=step.skill,
            success=bool(result.get("success")),
            detail=str(result.get("detail", "")),
            screenshot_path=screenshot_path,
            data=data,
        )
        log_action(
            self.logger,
            action=step.skill,
            success=bool(result.get("success")),
            detail=str(result.get("detail", "")),
            screenshot_path=screenshot_path,
            extra={
                "step_index": step_index,
                "page": page_name,
                "target": target_name,
                "fallback_used": bool(data.get("fallback_used", False)),
            },
        )
        return result

    def _should_attempt_recovery(self, step: PlanStep, result: Dict[str, Any]) -> bool:
        if step.skill not in ("tap", "search_in_app", "open_app"):
            return False
        detail = str(result.get("detail", "")).lower()
        return "unable to find" in detail or "expected" in detail

    def _attempt_recovery(
        self,
        step: PlanStep,
        context: SkillContext,
        step_index: int,
    ) -> Dict[str, Any]:
        self.adb.back()
        self._refresh_screen("recovery_{0:02d}".format(step_index))
        retried = self._run_skill(step, context)
        retried.setdefault("data", {})
        retried["data"]["recovery_attempted"] = True
        if retried.get("success") and step.skill in ("open_app", "tap", "search_in_app"):
            summary = self._refresh_screen("recovery_post_{0:02d}".format(step_index))
            retried["data"]["screen_summary"] = summary
            expectation_error = self._evaluate_expectations(step, summary)
            if expectation_error:
                retried["success"] = False
                retried["detail"] = expectation_error

        screenshot = self.screenshot_manager.capture(
            self.adb,
            task_name=self.state.current_task or "default_task",
            prefix="step_{0:02d}_{1}_recovery".format(step_index, step.skill),
        )
        retried["screenshot_path"] = str(screenshot)
        self.state.record_step(
            action="{0}_recovery".format(step.skill),
            success=bool(retried.get("success")),
            detail=str(retried.get("detail", "")),
            screenshot_path=str(screenshot),
            data=retried.get("data"),
        )
        log_action(
            self.logger,
            action="{0}_recovery".format(step.skill),
            success=bool(retried.get("success")),
            detail=str(retried.get("detail", "")),
            screenshot_path=str(screenshot),
            extra={
                "step_index": step_index,
                "page": self.state.current_page,
                "target": step.args.get("target") or step.args.get("expect_target"),
                "fallback_used": bool((retried.get("data") or {}).get("fallback_used", False)),
            },
        )
        return retried

    def _record_trajectory(self, final_result: Dict[str, Any]) -> None:
        if not self.memory:
            return

        app_name = self.state.current_app or "unknown"
        intent = self.state.current_task or final_result["goal"]
        steps_summary = " > ".join(step.get("action", "") for step in final_result.get("steps", []))
        confidence = 1.0 if final_result["success"] else 0.7
        task_type = self.state.task_type or final_result.get("task_type", "unsupported")

        if final_result["success"]:
            self.memory.add_successful_trajectory(
                task_type=task_type,
                app=app_name,
                intent=intent,
                steps_summary=steps_summary,
                confidence=confidence,
                verified=True,
            )
        else:
            self.memory.add_failure_pattern(
                task_type=task_type,
                app=app_name,
                intent=intent,
                steps_summary=steps_summary,
                confidence=confidence,
            )
