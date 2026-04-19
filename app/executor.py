from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from app.memory import SQLiteMemory
from app.planner import ExecutionPlan, PlanStep
from app.skills.base import SkillContext
from app.skills.read_screen import read_screen_summary
from app.skills.targeting import find_semantic_target
from app.state import AgentState
from app.task_types import TASK_GUIDED_UI_TASK
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
        context_builder: Any = None,
        page_reasoner: Any = None,
        runtime_config: Any = None,
        trace_bus: Any = None,
    ) -> None:
        self.adb = adb
        self.state = state
        self.logger = logger
        self.screenshot_manager = screenshot_manager
        self.skill_registry = dict(skill_registry)
        self.memory = memory
        self.context_builder = context_builder
        self.page_reasoner = page_reasoner
        self.runtime_config = runtime_config
        self.trace_bus = trace_bus
        self._interactive_allowed_skills = {
            "open_app",
            "tap",
            "swipe",
            "type_text",
            "back",
            "wait",
            "search_in_app",
        }

    def _context(self) -> SkillContext:
        return SkillContext(
            adb=self.adb,
            state=self.state,
            logger=self.logger,
            screenshot_manager=self.screenshot_manager,
            registry=self.skill_registry,
            memory=self.memory,
            context_builder=self.context_builder,
            page_reasoner=self.page_reasoner,
            runtime_config=self.runtime_config,
        )

    def execute_plan(
        self,
        plan: ExecutionPlan,
        agent_mode: str = "bounded",
        max_steps: int = 3,
    ) -> Dict[str, Any]:
        if self.trace_bus:
            self.trace_bus.emit(
                stage="executor.start",
                backend="executor",
                success=True,
                reason_summary="Starting bounded execution.",
                extra={
                    "goal": plan.goal,
                    "task_type": plan.task_type,
                    "agent_mode": agent_mode,
                },
            )
        self.state.start_task(
            plan.goal,
            task_type=plan.task_type,
            risk_flag=self.state.risk_flag,
        )
        context = self._context()
        step_results = []

        for index, step in enumerate(plan.steps, start=1):
            result = self._execute_step(step, context, index)
            step_results.append(result)
            if not result["success"]:
                break

        if (
            all(item["success"] for item in step_results)
            and agent_mode == "interactive"
            and plan.task_type == TASK_GUIDED_UI_TASK
        ):
            interactive_results = self._run_interactive_loop(
                plan=plan,
                context=context,
                start_index=len(step_results) + 1,
                max_steps=max_steps,
            )
            step_results.extend(interactive_results)

        final_result = {
            "goal": plan.goal,
            "task_type": plan.task_type,
            "status": plan.status,
            "success": all(item["success"] for item in step_results) if step_results else False,
            "steps": step_results,
            "needs_replan": self.state.needs_replan,
            "state": self.state.to_dict(),
            "agent_mode": agent_mode,
        }
        if plan.message:
            final_result["message"] = plan.message
        self._record_trajectory(final_result)
        if self.trace_bus:
            self.trace_bus.emit(
                stage="executor.done",
                backend="executor",
                success=final_result["success"],
                confidence=1.0 if final_result["success"] else 0.0,
                reason_summary="Execution completed.",
                extra={
                    "goal": plan.goal,
                    "task_type": plan.task_type,
                    "step_count": len(step_results),
                },
            )
        return final_result

    def _execute_step(
        self, step: PlanStep, context: SkillContext, step_index: int
    ) -> Dict[str, Any]:
        resolved_step = PlanStep(step.skill, self._resolve_args(step.args))
        skip_if_page = resolved_step.args.get("skip_if_page")
        if skip_if_page and self.state.current_page == skip_if_page:
            skipped = {
                "success": True,
                "action": resolved_step.skill,
                "detail": "Skipped because page is already {0}.".format(skip_if_page),
                "screenshot_path": None,
                "data": {"skipped": True},
            }
            return self._finalize_result(resolved_step, skipped, step_index)
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
        if self.trace_bus:
            self.trace_bus.emit(
                stage="executor.step",
                backend="executor",
                success=bool(result.get("success")),
                confidence=1.0 if result.get("success") else 0.0,
                reason_summary=str(result.get("detail", ""))[:160],
                fallback_triggered=bool(data.get("fallback_used", False)),
                extra={
                    "action": step.skill,
                    "page": page_name,
                    "target": target_name,
                },
            )
        return result

    def _should_attempt_recovery(self, step: PlanStep, result: Dict[str, Any]) -> bool:
        if step.skill not in ("tap", "search_in_app", "open_app"):
            return False
        detail = str(result.get("detail", "")).lower()
        return "unable to find" in detail or "expected" in detail

    def _run_interactive_loop(
        self,
        plan: ExecutionPlan,
        context: SkillContext,
        start_index: int,
        max_steps: int,
    ) -> list:
        results = []
        next_step_index = start_index
        rounds_completed = 0

        while rounds_completed < max_steps:
            reasoning = self.state.artifacts.get("last_page_reasoning") or {}
            next_action = reasoning.get("next_action")
            if not next_action:
                break
            validation_error = self._validate_interactive_action(next_action, reasoning)
            if validation_error:
                failure = {
                    "success": False,
                    "action": "interactive_action",
                    "detail": validation_error,
                    "screenshot_path": None,
                    "data": {"page_reasoning": reasoning},
                }
                results.append(
                    self._finalize_result(
                        PlanStep("interactive_action", {}),
                        failure,
                        next_step_index,
                    )
                )
                break

            action_step = PlanStep(str(next_action["skill"]), dict(next_action.get("args") or {}))
            page_before_action = self.state.current_page or (self.state.screen_summary or {}).get("page") or ""
            app_before_action = self.state.current_app or (self.state.screen_summary or {}).get("app") or ""
            action_result = self._execute_step(action_step, context, next_step_index)
            results.append(action_result)
            next_step_index += 1
            self._remember_verified_shortcut(
                plan=plan,
                reasoning=reasoning,
                action_step=action_step,
                action_result=action_result,
                page_before_action=page_before_action,
                app_before_action=app_before_action,
            )
            if not action_result["success"]:
                break

            read_step = PlanStep("read_screen", {"prefix": "interactive_round_{0}".format(rounds_completed + 1)})
            read_result = self._execute_step(read_step, context, next_step_index)
            results.append(read_result)
            next_step_index += 1
            if not read_result["success"]:
                break

            reason_step = PlanStep(
                "reason_about_page",
                {
                    "goal": plan.goal,
                    "task_type": plan.task_type,
                },
            )
            reason_result = self._execute_step(reason_step, context, next_step_index)
            results.append(reason_result)
            next_step_index += 1
            if not reason_result["success"]:
                break

            rounds_completed += 1

        return results

    def _remember_verified_shortcut(
        self,
        plan: ExecutionPlan,
        reasoning: Dict[str, Any],
        action_step: PlanStep,
        action_result: Dict[str, Any],
        page_before_action: str,
        app_before_action: str,
    ) -> None:
        if not self.memory:
            return
        if plan.task_type != TASK_GUIDED_UI_TASK:
            return
        if not action_result.get("success"):
            return
        if reasoning.get("requires_confirmation"):
            return
        if action_step.skill not in self._interactive_allowed_skills:
            return
        args = dict(action_step.args or {})
        if not args:
            return
        self.memory.remember_ui_shortcut(
            task_type=plan.task_type,
            app=app_before_action,
            page=page_before_action,
            intent=plan.goal,
            skill=action_step.skill,
            args=args,
            confidence=float(reasoning.get("confidence", 0.9)),
        )

    def _validate_interactive_action(
        self,
        next_action: Dict[str, Any],
        reasoning: Dict[str, Any],
    ) -> Optional[str]:
        skill_name = str(next_action.get("skill") or "").strip()
        if not skill_name:
            return "Interactive next_action is missing a skill."
        if skill_name not in self._interactive_allowed_skills:
            return "Interactive action is not allowed: {0}".format(skill_name)
        if not isinstance(next_action.get("args") or {}, dict):
            return "Interactive action args must be an object."
        if reasoning.get("requires_confirmation"):
            return "Interactive action requires manual confirmation."
        return None

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
