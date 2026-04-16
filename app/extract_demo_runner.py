from __future__ import annotations

import argparse
import json
import sys

from app.main import run_task
from app.task_types import TASK_EXTRACT_AND_COPY


FIELD_TO_PROMPT = {
    "order_number": "extract the order number and copy it into notes",
    "check_in_time": "extract the hotel check-in time and copy it into notes",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the bounded extract_and_copy demo flow.")
    parser.add_argument(
        "--field",
        default="order_number",
        choices=["order_number", "check_in_time"],
        help="Which bounded value to extract from the visible source screen.",
    )
    parser.add_argument("--device-id", default=None, help="ADB device serial.")
    parser.add_argument(
        "--auto-confirm",
        action="store_true",
        help="Bypass confirmation prompts for non-interactive runs.",
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args()
    result = run_task(
        task_text=FIELD_TO_PROMPT[args.field],
        device_id=args.device_id,
        task_type_override=TASK_EXTRACT_AND_COPY,
        auto_confirm=args.auto_confirm,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
