from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.memory import SQLiteMemory


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _summarize_actions(actions: list[Any]) -> dict[str, Any]:
    samples: list[Any] = []
    for action in actions[:3]:
        if not isinstance(action, dict):
            samples.append(_compact_value(action))
            continue
        data = action.get("data") if isinstance(action.get("data"), dict) else {}
        suggestion = data.get("agent_suggestion") if isinstance(data.get("agent_suggestion"), dict) else {}
        screen = data.get("screen_summary") if isinstance(data.get("screen_summary"), dict) else {}
        samples.append(
            {
                "action": action.get("action"),
                "detail": action.get("detail"),
                "success": action.get("success"),
                "suggested_skill": suggestion.get("skill"),
                "suggested_args": suggestion.get("args"),
                "page": screen.get("page"),
                "app": screen.get("app"),
                "visible_text": _compact_value(screen.get("visible_text", []), max_items=5),
            }
        )
    return {
        "count": len(actions),
        "samples": samples,
    }


def _compact_value(value: Any, *, max_string: int = 700, max_items: int = 8) -> Any:
    if isinstance(value, str):
        if len(value) <= max_string:
            return value
        return f"{value[:max_string]}...<truncated {len(value) - max_string} chars>"
    if isinstance(value, list):
        compacted = [_compact_value(item, max_string=max_string, max_items=max_items) for item in value[:max_items]]
        if len(value) > max_items:
            compacted.append(f"...<{len(value) - max_items} more>")
        return compacted
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, item in value.items():
            if key == "agent_actions" and isinstance(item, list):
                compacted[key] = _summarize_actions(item)
                continue
            compacted[key] = _compact_value(item, max_string=max_string, max_items=max_items)
        return compacted
    return value


def _print_rows(title: str, rows: Iterable[dict[str, Any]]) -> None:
    print(title)
    printed = False
    for row in rows:
        printed = True
        print(json.dumps(_compact_value(row), ensure_ascii=False, indent=2, sort_keys=True))
    if not printed:
        print("(none)")


def main() -> int:
    _configure_stdout()
    db_path = Path("data/memory.db")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    memory = SQLiteMemory(db_path=str(db_path))

    _print_rows("learned_procedures", memory.list_learned_procedures(limit=limit))
    _print_rows("manual_interventions", memory.list_manual_interventions(limit=limit))
    _print_rows("manual_reflections", memory.list_manual_reflections(limit=limit))

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        interaction_rows = conn.execute(
            """
            SELECT task_type, app, page, state_tags_json, action_skill,
                   action_template_json, confidence, use_count, last_seen_timestamp
            FROM interaction_patterns
            ORDER BY last_seen_timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        _print_rows("interaction_patterns", (dict(row) for row in interaction_rows))

        trajectory_rows = conn.execute(
            """
            SELECT task_type, app, intent, steps_summary, confidence, verified, timestamp
            FROM successful_trajectories
            WHERE task_type = 'guided_ui_task'
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        _print_rows("guided_ui_trajectories", (dict(row) for row in trajectory_rows))
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
