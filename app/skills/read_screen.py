from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from app.demo_config import DemoMessageConfig
from app.skills.base import BaseSkill, SkillContext
from app.skills.targeting import normalize_text


def _parse_bounds(bounds: str) -> Optional[Dict[str, int]]:
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not match:
        return None
    left, top, right, bottom = [int(value) for value in match.groups()]
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "center_x": (left + right) // 2,
        "center_y": (top + bottom) // 2,
    }


def _build_candidate(node: ET.Element) -> Optional[Dict[str, Any]]:
    text_value = (node.attrib.get("text") or "").strip()
    content_desc = (node.attrib.get("content-desc") or "").strip()
    resource_id = (node.attrib.get("resource-id") or "").strip()
    label = text_value or content_desc or resource_id
    if not label:
        return None

    source = "text"
    confidence = 0.95
    if not text_value and content_desc:
        source = "content_desc"
        confidence = 0.85
    elif not text_value and not content_desc and resource_id:
        source = "resource_id"
        confidence = 0.70

    return {
        "label": label,
        "bounds": _parse_bounds(node.attrib.get("bounds", "")),
        "resource_id": resource_id,
        "content_desc": content_desc,
        "class_name": node.attrib.get("class", ""),
        "clickable": node.attrib.get("clickable", "false") == "true",
        "confidence": confidence,
        "source": source,
    }


def detect_page_name(
    visible_text, focus: str, runtime_config: Optional[DemoMessageConfig]
) -> Optional[str]:
    if not runtime_config:
        return None

    corpus = normalize_text(" ".join(visible_text) + " " + (focus or ""))
    best_name = None
    best_score = 0
    for page_name, profile in runtime_config.page_profiles.items():
        score = 0
        for keyword in profile.keywords:
            if normalize_text(keyword) in corpus:
                score += 1
        if score > best_score:
            best_name = page_name
            best_score = score

    if best_score <= 0:
        return None
    return best_name


def read_screen_summary(
    adb,
    xml_path: str,
    runtime_config: Optional[DemoMessageConfig] = None,
) -> Dict[str, Any]:
    dump_path = adb.dump_ui_xml(xml_path)
    tree = ET.parse(str(dump_path))
    root = tree.getroot()

    visible_text = []
    possible_targets = []
    for node in root.iter("node"):
        candidate = _build_candidate(node)
        if not candidate:
            continue
        visible_text.append(candidate["label"])
        possible_targets.append(candidate)

    focus = adb.get_current_focus()
    app_name = "unknown"
    if "/" in focus:
        app_name = focus.split()[0].split("/")[-1]

    detected_page = detect_page_name(visible_text, focus, runtime_config)
    return {
        "app": app_name,
        "page": detected_page or Path(str(dump_path)).stem,
        "visible_text": visible_text[:50],
        "possible_targets": possible_targets[:50],
        "focus": focus,
        "ui_dump_path": str(dump_path),
    }


class ReadScreenSkill(BaseSkill):
    name = "read_screen"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        prefix = args.get("prefix", "read_screen")
        dump_path = Path("data/tmp")
        dump_path.mkdir(parents=True, exist_ok=True)
        xml_path = dump_path / "{0}.xml".format(prefix)
        summary = read_screen_summary(
            context.adb,
            str(xml_path),
            runtime_config=context.runtime_config,
        )
        context.state.update_screen_summary(summary)
        return self.result(success=True, detail="Screen summary refreshed.", data=summary)
