from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentState(object):
    current_task: Optional[str] = None
    task_type: Optional[str] = None
    current_app: Optional[str] = None
    current_page: Optional[str] = None
    last_action: Optional[str] = None
    last_action_success: Optional[bool] = None
    current_step_index: int = 0
    screen_summary: Dict[str, Any] = field(default_factory=dict)
    recent_screenshots: List[str] = field(default_factory=list)
    recent_actions: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    needs_replan: bool = False
    risk_flag: bool = False
    last_failure_reason: Optional[str] = None

    def start_task(
        self,
        task_name: str,
        task_type: Optional[str] = None,
        risk_flag: bool = False,
    ) -> None:
        self.current_task = task_name
        self.task_type = task_type
        self.current_step_index = 0
        self.last_action = None
        self.last_action_success = None
        self.screen_summary = {}
        self.recent_actions = []
        self.recent_screenshots = []
        self.artifacts = {}
        self.needs_replan = False
        self.risk_flag = risk_flag
        self.last_failure_reason = None

    def update_screen_summary(self, summary: Dict[str, Any]) -> None:
        self.screen_summary = summary or {}
        self.current_app = self.screen_summary.get("app") or self.current_app
        self.current_page = self.screen_summary.get("page") or self.current_page

    def record_step(
        self,
        action: str,
        success: bool,
        detail: str = "",
        screenshot_path: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.last_action = action
        self.last_action_success = success
        self.current_step_index += 1
        event = {
            "action": action,
            "success": success,
            "detail": detail,
        }
        if screenshot_path:
            self.add_screenshot(screenshot_path)
            event["screenshot_path"] = screenshot_path
        if data:
            event["data"] = data
        self.recent_actions.append(event)
        self.recent_actions = self.recent_actions[-5:]
        self.needs_replan = not success
        self.last_failure_reason = detail if not success else None

    def remember_artifact(self, key: str, value: Any) -> None:
        self.artifacts[key] = value

    def recent_failure_count(self, limit: int = 3) -> int:
        recent = self.recent_actions[-limit:]
        return len([item for item in recent if not item.get("success")])

    def add_screenshot(self, screenshot_path: str) -> None:
        self.recent_screenshots.append(screenshot_path)
        self.recent_screenshots = self.recent_screenshots[-10:]

    def recent_action_context(self, limit: int = 2) -> List[Dict[str, Any]]:
        return self.recent_actions[-limit:]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
