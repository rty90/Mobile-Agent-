from __future__ import annotations

from typing import Dict

from app.skills.back import BackSkill
from app.skills.confirm_action import ConfirmActionSkill
from app.skills.extract_value import ExtractValueSkill
from app.skills.manual_intervention import ManualInterventionSkill
from app.skills.open_calendar_event import OpenCalendarEventSkill
from app.skills.open_app import OpenAppSkill
from app.skills.open_message_thread import OpenMessageThreadSkill
from app.skills.read_screen import ReadScreenSkill
from app.skills.reason_about_page import ReasonAboutPageSkill
from app.skills.search_in_app import SearchInAppSkill
from app.skills.swipe import SwipeSkill
from app.skills.tap import TapSkill
from app.skills.type_text import TypeTextSkill
from app.skills.wait import WaitSkill


def build_skill_registry() -> Dict[str, object]:
    skills = [
        OpenAppSkill(),
        OpenMessageThreadSkill(),
        OpenCalendarEventSkill(),
        TapSkill(),
        SwipeSkill(),
        TypeTextSkill(),
        BackSkill(),
        WaitSkill(),
        ReadScreenSkill(),
        ReasonAboutPageSkill(),
        ExtractValueSkill(),
        ConfirmActionSkill(),
        ManualInterventionSkill(),
        SearchInAppSkill(),
    ]
    return dict((skill.name, skill) for skill in skills)
