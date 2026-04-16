from __future__ import annotations

import argparse
import json
import os
import sys

from app.context_builder import ContextBuilder
from app.demo_config import build_demo_message_config
from app.executor import Executor
from app.memory import SQLiteMemory
from app.page_reasoner import PageReasoner
from app.planner import PlanStep, TaskPlanner
from app.router import TaskRouter
from app.skills import build_skill_registry
from app.state import AgentState
from app.task_types import (
    TASK_CREATE_REMINDER,
    TASK_EXTRACT_AND_COPY,
    TASK_GUIDED_UI_TASK,
    TASK_READ_CURRENT_SCREEN,
    TASK_SEND_MESSAGE,
    TASK_UNSUPPORTED,
)
from app.utils.adb import ADBClient, ADBError
from app.utils.logger import setup_logger
from app.utils.screenshot import ScreenshotManager


LOG_PATH = "data/logs/agent.log"
SCREENSHOT_ROOT = "data/screenshots"
MEMORY_PATH = "data/memory.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Android GUI Agent v0.3")
    parser.add_argument("--task", required=True, help="Natural language task to execute.")
    parser.add_argument("--device-id", default=None, help="ADB device serial.")
    parser.add_argument(
        "--planner-backend",
        default="rule",
        choices=["rule", "openai"],
        help="Planner backend to use.",
    )
    parser.add_argument(
        "--task-type",
        default=None,
        choices=[
            TASK_SEND_MESSAGE,
            TASK_EXTRACT_AND_COPY,
            TASK_CREATE_REMINDER,
            TASK_READ_CURRENT_SCREEN,
            TASK_GUIDED_UI_TASK,
            TASK_UNSUPPORTED,
        ],
        help="Optional override for the supported task flow type.",
    )
    parser.add_argument(
        "--agent-mode",
        default=None,
        choices=["bounded", "interactive"],
        help="Execution mode. Interactive is recommended for read_current_screen and guided_ui_task.",
    )
    parser.add_argument(
        "--reasoner-backend",
        default="rule",
        choices=["rule", "local", "openai"],
        help="Page reasoner backend.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=3,
        help="Maximum interactive action rounds for guided UI tasks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the route decision and execution plan without touching the emulator.",
    )
    parser.add_argument(
        "--auto-confirm",
        action="store_true",
        help="Bypass confirmation prompts for non-interactive runs.",
    )
    return parser


def build_runtime(device_id=None, planner_backend="rule", reasoner_backend="rule", demo_config=None):
    logger = setup_logger()
    adb = ADBClient(device_id=device_id)
    state = AgentState()
    memory = SQLiteMemory(db_path=MEMORY_PATH)
    demo_config = demo_config or build_demo_message_config()
    context_builder = ContextBuilder(memory=memory)
    page_reasoner = PageReasoner(backend=reasoner_backend)
    planner = TaskPlanner(
        context_builder=context_builder,
        backend=planner_backend,
        demo_config=demo_config,
    )
    router = TaskRouter()
    screenshot_manager = ScreenshotManager(base_dir=SCREENSHOT_ROOT)
    executor = Executor(
        adb=adb,
        state=state,
        logger=logger,
        screenshot_manager=screenshot_manager,
        skill_registry=build_skill_registry(),
        memory=memory,
        context_builder=context_builder,
        page_reasoner=page_reasoner,
        runtime_config=demo_config,
    )
    return {
        "logger": logger,
        "adb": adb,
        "state": state,
        "memory": memory,
        "context_builder": context_builder,
        "page_reasoner": page_reasoner,
        "planner": planner,
        "router": router,
        "executor": executor,
        "runtime_config": demo_config,
    }


def run_task(
    task_text,
    device_id=None,
    planner_backend="rule",
    demo_config=None,
    task_type_override=None,
    agent_mode=None,
    reasoner_backend="rule",
    max_steps=3,
    dry_run=False,
    auto_confirm=False,
):
    if auto_confirm:
        os.environ["AGENT_AUTO_CONFIRM"] = "1"

    runtime = build_runtime(
        device_id=device_id,
        planner_backend=planner_backend,
        reasoner_backend=reasoner_backend,
        demo_config=demo_config,
    )
    logger = runtime["logger"]
    adb = runtime["adb"]
    state = runtime["state"]
    planner = runtime["planner"]
    router = runtime["router"]
    executor = runtime["executor"]

    decision = router.route(task_text, state=state, task_type_override=task_type_override)
    state.risk_flag = decision.requires_confirmation
    state.task_type = decision.task_type
    resolved_agent_mode = agent_mode
    if not resolved_agent_mode:
        if decision.task_type in (TASK_READ_CURRENT_SCREEN, TASK_GUIDED_UI_TASK):
            resolved_agent_mode = "interactive"
        else:
            resolved_agent_mode = "bounded"

    plan = planner.create_plan(task_text, state=state, task_type_override=decision.task_type)

    if not decision.supported or decision.mode == "unsupported-task" or plan.status == "unsupported":
        return {
            "goal": task_text,
            "task_type": decision.task_type,
            "status": "unsupported",
            "success": False,
            "route_mode": decision.mode,
            "reason": decision.reason,
            "message": plan.message,
            "agent_mode": resolved_agent_mode,
            "logs_path": LOG_PATH,
            "screenshots_root": SCREENSHOT_ROOT,
            "memory_path": MEMORY_PATH,
        }

    if decision.requires_confirmation:
        plan.steps.insert(
            0,
            PlanStep(
                "confirm_action",
                {"prompt": "High-risk task detected. Continue execution?"},
            ),
        )

    if dry_run:
        return {
            "goal": task_text,
            "task_type": plan.task_type,
            "status": "dry-run",
            "success": True,
            "route_mode": decision.mode,
            "reason": decision.reason,
            "risk_level": decision.risk_level,
            "agent_mode": resolved_agent_mode,
            "plan": plan.to_dict(),
            "logs_path": LOG_PATH,
            "screenshots_root": SCREENSHOT_ROOT,
            "memory_path": MEMORY_PATH,
        }

    adb.ensure_device()
    result = executor.execute_plan(plan, agent_mode=resolved_agent_mode, max_steps=max_steps)
    result["route_mode"] = decision.mode
    result["reason"] = decision.reason
    result["risk_level"] = decision.risk_level
    result["logs_path"] = LOG_PATH
    result["screenshots_root"] = SCREENSHOT_ROOT
    result["memory_path"] = MEMORY_PATH
    logger.info("Task completed with success=%s", result["success"])
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    try:
        result = run_task(
            task_text=args.task,
            device_id=args.device_id,
            planner_backend=args.planner_backend,
            task_type_override=args.task_type,
            agent_mode=args.agent_mode,
            reasoner_backend=args.reasoner_backend,
            max_steps=args.max_steps,
            dry_run=args.dry_run,
            auto_confirm=args.auto_confirm,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("success") else 1
    except ADBError as exc:
        print("ADB error:", exc)
        print("Logs:", LOG_PATH)
        return 2
    except Exception as exc:
        print("Execution error:", exc)
        print("Logs:", LOG_PATH)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
