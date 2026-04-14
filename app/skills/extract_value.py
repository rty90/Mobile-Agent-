from __future__ import annotations

from typing import Any, Dict, Mapping

from app.extraction import extract_key_value
from app.skills.base import BaseSkill, SkillContext
from app.skills.read_screen import read_screen_summary


class ExtractValueSkill(BaseSkill):
    name = "extract_value"

    def execute(self, args: Mapping[str, Any], context: SkillContext) -> Dict[str, Any]:
        field_hint = str(args.get("field_hint", "generic_value"))
        artifact_key = str(args.get("artifact_key", "extracted_value"))

        summary = context.state.screen_summary or read_screen_summary(
            context.adb,
            "data/tmp/extract_value.xml",
            runtime_config=context.runtime_config,
        )
        context.state.update_screen_summary(summary)

        extracted_value = extract_key_value(summary, field_hint=field_hint)
        if not extracted_value:
            return self.result(
                success=False,
                detail="Unable to extract {0} from the current screen.".format(field_hint),
                data={"field_hint": field_hint},
            )

        context.state.remember_artifact(artifact_key, extracted_value)
        context.state.remember_artifact("last_extraction_field_hint", field_hint)
        return self.result(
            success=True,
            detail="Extracted {0}: {1}".format(field_hint, extracted_value),
            data={
                "field_hint": field_hint,
                "artifacts": {artifact_key: extracted_value},
                "extracted_value": extracted_value,
            },
        )

