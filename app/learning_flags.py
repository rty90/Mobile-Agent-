from __future__ import annotations

import os


def guided_ui_memory_expansion_enabled() -> bool:
    """Return true when guided-UI experimental memory expansion is opt-in enabled."""
    value = os.environ.get("AGENT_ENABLE_GUIDED_UI_MEMORY_EXPANSION", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def guided_ui_raw_memory_enabled() -> bool:
    """Return true when raw guided-UI memories should be included in planning context."""
    value = os.environ.get("AGENT_INCLUDE_RAW_GUIDED_UI_MEMORY", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}
