from __future__ import annotations

import re
from typing import Dict, Iterable, Optional


PATTERN_LIBRARY = {
    "order_number": (
        re.compile(r"(?:order(?:\s+number)?|reservation(?:\s+number)?|confirmation(?:\s+code)?)[^\w]{0,3}([A-Z0-9-]{4,})", re.IGNORECASE),
        re.compile(r"\b([A-Z]{2,}\d{3,}|\d{6,})\b"),
    ),
    "check_in_time": (
        re.compile(r"(?:check[- ]in(?:\s+time)?|arrival(?:\s+time)?)[^\d]{0,8}(\d{1,2}(?::\d{2})?\s?(?:am|pm))", re.IGNORECASE),
        re.compile(r"\b(\d{1,2}(?::\d{2})?\s?(?:am|pm))\b", re.IGNORECASE),
    ),
    "generic_value": (
        re.compile(r":\s*([A-Za-z0-9][A-Za-z0-9\-: ]{2,})"),
    ),
}


def _iter_lines(summary: Dict[str, object]) -> Iterable[str]:
    visible_text = summary.get("visible_text", [])
    if isinstance(visible_text, list):
        for item in visible_text:
            if item:
                yield str(item)


def extract_key_value(summary: Dict[str, object], field_hint: str = "generic_value") -> Optional[str]:
    lines = list(_iter_lines(summary))
    patterns = PATTERN_LIBRARY.get(field_hint) or PATTERN_LIBRARY["generic_value"]

    for line in lines:
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                value = match.group(1).strip()
                if value:
                    return value

    joined = " | ".join(lines)
    for pattern in patterns:
        match = pattern.search(joined)
        if match:
            value = match.group(1).strip()
            if value:
                return value

    return None

