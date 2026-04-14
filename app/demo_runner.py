from __future__ import annotations

import argparse
import json
import os
import sys

from app.contact_discovery import discover_contacts
from app.demo_config import build_demo_message_config
from app.main import build_runtime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the remembered-contact SMS demo flow.")
    parser.add_argument("--device-id", default=None, help="ADB device serial.")
    parser.add_argument("--contact", default=None, help="Preferred contact name from remembered contacts.")
    parser.add_argument(
        "--message-text",
        default="hello from emulator",
        help="Template message text. ASCII is recommended on emulator.",
    )
    parser.add_argument(
        "--auto-confirm",
        action="store_true",
        help="Bypass the manual confirmation step for non-interactive runs.",
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    if args.auto_confirm:
        os.environ["AGENT_AUTO_CONFIRM"] = "1"

    runtime = build_runtime(device_id=args.device_id)
    adb = runtime["adb"]
    memory = runtime["memory"]
    planner = runtime["planner"]
    executor = runtime["executor"]

    adb.ensure_device()
    discovered_contacts = discover_contacts(adb, memory)

    selected = None
    if args.contact:
        selected = memory.get_contact_by_name(args.contact)
    if not selected:
        selected = memory.get_best_contact(prefer_ascii=True)

    if not selected:
        payload = {
            "success": False,
            "detail": "No remembered contacts were found on the emulator.",
            "discovered_contacts": discovered_contacts,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    demo_config = build_demo_message_config(
        contact_name=selected["contact_name"],
        phone_number=selected["phone_number"],
        message_text=args.message_text,
    )
    planner.rule_planner.demo_config = demo_config
    executor.runtime_config = demo_config

    plan = planner.rule_planner.create_demo_message_plan()
    result = executor.execute_plan(plan)
    result["selected_contact"] = selected
    result["discovered_contacts"] = discovered_contacts
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
