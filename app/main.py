from __future__ import annotations

import argparse
import json
import sys

from app.context_builder import ContextBuilder
from app.demo_config import build_demo_message_config
from app.executor import Executor
from app.memory import SQLiteMemory
from app.planner import PlanStep, TaskPlanner
from app.router import TaskRouter
from app.skills import build_skill_registry
from app.state import AgentState
from app.utils.adb import ADBClient, ADBError
from app.utils.logger import setup_logger
from app.utils.screenshot import ScreenshotManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Android GUI Agent MVP")
    parser.add_argument("--task", required=True, help="Natural language task to execute.")
    parser.add_argument("--device-id", default=None, help="ADB device serial.")
    parser.add_argument(
        "--planner-backend",
        default="rule",
        choices=["rule", "openai"],
        help="Planner backend to use.",
    )
    return parser


def build_runtime(device_id=None, planner_backend="rule", demo_config=None):
    logger = setup_logger()
    adb = ADBClient(device_id=device_id)
    state = AgentState()
    memory = SQLiteMemory()
    demo_config = demo_config or build_demo_message_config()
    context_builder = ContextBuilder(memory=memory)
    planner = TaskPlanner(
        context_builder=context_builder,
        backend=planner_backend,
        demo_config=demo_config,
    )
    router = TaskRouter()
    screenshot_manager = ScreenshotManager()
    executor = Executor(
        adb=adb,
        state=state,
        logger=logger,
        screenshot_manager=screenshot_manager,
        skill_registry=build_skill_registry(),
        memory=memory,
        runtime_config=demo_config,
    )
    return {
        "logger": logger,
        "adb": adb,
        "state": state,
        "memory": memory,
        "planner": planner,
        "router": router,
        "executor": executor,
        "runtime_config": demo_config,
    }


def run_task(task_text, device_id=None, planner_backend="rule", demo_config=None):
    runtime = build_runtime(
        device_id=device_id,
        planner_backend=planner_backend,
        demo_config=demo_config,
    )
    logger = runtime["logger"]
    adb = runtime["adb"]
    state = runtime["state"]
    planner = runtime["planner"]
    router = runtime["router"]
    executor = runtime["executor"]

    adb.ensure_device()
    decision = router.route(task_text, state=state)
    state.risk_flag = decision.requires_confirmation

    plan = planner.create_plan(task_text, state=state)
    if decision.requires_confirmation:
        plan.steps.insert(
            0,
            PlanStep(
                "confirm_action",
                {"prompt": "High-risk task detected. Continue execution?"},
            ),
        )

    result = executor.execute_plan(plan)
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
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["success"] else 1
    except ADBError as exc:
        print("ADB error:", exc)
        return 2
    except Exception as exc:
        print("Execution error:", exc)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
