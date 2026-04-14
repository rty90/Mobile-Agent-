from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional


def setup_logger(
    name: str = "agent",
    log_dir: str = "data/logs",
    log_file: str = "agent.log",
    level: int = logging.INFO,
) -> logging.Logger:
    """Configure a project logger that writes to console and file."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(str(log_path / log_file), encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


def log_action(
    logger: logging.Logger,
    action: str,
    success: bool,
    detail: Optional[str] = None,
    screenshot_path: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Write one normalized action record."""
    payload = {
        "action": action,
        "status": "success" if success else "fail",
        "detail": detail or "",
        "screenshot_path": screenshot_path or "",
    }
    if extra:
        payload.update(extra)

    message = json.dumps(payload, ensure_ascii=False)
    if success:
        logger.info(message)
    else:
        logger.error(message)
