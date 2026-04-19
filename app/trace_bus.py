from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class TraceBus(object):
    def __init__(
        self,
        trace_path: str = "data/logs/reasoning_trace.jsonl",
        console_enabled: bool = False,
    ) -> None:
        self.trace_path = Path(trace_path)
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        self.console_enabled = console_enabled

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def emit(
        self,
        stage: str,
        backend: str,
        success: bool,
        confidence: Optional[float] = None,
        reason_summary: str = "",
        fallback_triggered: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event = {
            "timestamp": self._now_iso(),
            "stage": stage,
            "backend": backend,
            "success": bool(success),
            "confidence": confidence,
            "reason_summary": reason_summary,
            "fallback_triggered": bool(fallback_triggered),
        }
        if extra:
            event.update(extra)

        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

        if self.console_enabled:
            rendered_confidence = "-"
            if confidence is not None:
                rendered_confidence = "{0:.2f}".format(float(confidence))
            line = "[trace] {0} | {1} | {2} | conf={3} | {4}".format(
                stage,
                backend,
                "ok" if success else "fail",
                rendered_confidence,
                reason_summary or "",
            )
            print(line, file=sys.stdout)

        return event
