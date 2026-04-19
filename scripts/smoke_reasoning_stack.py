from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.model_runtime import ModelRuntime
from app.page_reasoner import RuleBasedPageReasoner
from app.reasoning_orchestrator import ReasoningOrchestrator
from app.reasoning_validator import ReasoningValidator
from app.trace_bus import TraceBus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke test the bounded reasoning stack.")
    parser.add_argument("--goal", required=True, help="Natural-language goal.")
    parser.add_argument("--task-type", required=True, help="Bounded task type.")
    parser.add_argument("--screen-summary-json", required=True, help="Path to a JSON file with screen_summary.")
    parser.add_argument("--screenshot-path", default=None, help="Optional screenshot path for VL fallback.")
    parser.add_argument("--dry-run", action="store_true", help="Run orchestration only and print the final decision.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    screen_summary = json.loads(Path(args.screen_summary_json).read_text(encoding="utf-8"))
    trace_bus = TraceBus(console_enabled=True)
    validator = ReasoningValidator(
        min_confidence=float(__import__("os").environ.get("REASONING_MIN_CONFIDENCE", "0.70"))
    )
    model_runtime = ModelRuntime()
    orchestrator = ReasoningOrchestrator(
        validator=validator,
        model_runtime=model_runtime,
        trace_bus=trace_bus,
        rule_fallback=RuleBasedPageReasoner().reason,
    )
    try:
        result = orchestrator.resolve(
            goal=args.goal,
            task_type=args.task_type,
            screen_summary=screen_summary,
            screenshot_path=args.screenshot_path,
            recent_actions=[],
            relevant_memories=[],
            normalized_context={
                "goal": args.goal,
                "task_type": args.task_type,
                "screen_summary": screen_summary,
                "recent_actions": [],
                "relevant_memories": [],
                "risk_flag": False,
            },
        )
        print(json.dumps(result["decision"].to_dict(), ensure_ascii=False, indent=2))
        print("Trace:", result["trace_path"])
        return 0
    finally:
        model_runtime.shutdown_owned_processes()


if __name__ == "__main__":
    raise SystemExit(main())
