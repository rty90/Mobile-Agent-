from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Optional

from app.state import AgentState
from app.utils.adb import ADBClient
from app.utils.screenshot import ScreenshotManager


SkillResult = Dict[str, Any]


@dataclass
class SkillContext(object):
    adb: ADBClient
    state: AgentState
    logger: Any
    screenshot_manager: ScreenshotManager
    registry: MutableMapping[str, "BaseSkill"]
    runtime_config: Any = None


class BaseSkill(ABC):
    name = ""

    @abstractmethod
    def execute(self, args: Mapping[str, Any], context: SkillContext) -> SkillResult:
        raise NotImplementedError

    def result(
        self,
        success: bool,
        detail: str,
        screenshot_path: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        payload = {
            "success": success,
            "action": self.name,
            "detail": detail,
            "screenshot_path": screenshot_path,
        }
        if data is not None:
            payload["data"] = data
        return payload
