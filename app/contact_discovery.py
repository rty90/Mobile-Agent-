from __future__ import annotations

import re
from typing import Dict, List

from app.memory import SQLiteMemory


def _parse_content_rows(output: str) -> List[Dict[str, str]]:
    rows = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line.startswith("Row:"):
            continue
        row = {}
        for key, value in re.findall(r"([A-Za-z0-9_]+)=(.*?)(?=,\s+[A-Za-z0-9_]+=|$)", line):
            row[key] = value.strip()
        rows.append(row)
    return rows


def discover_contacts(adb, memory: SQLiteMemory) -> List[Dict[str, str]]:
    output = adb.shell(
        "content query --uri content://com.android.contacts/data/phones "
        "--projection display_name:data1"
    )
    rows = _parse_content_rows(output)
    discovered = []
    for row in rows:
        contact_name = row.get("display_name", "").strip()
        phone_number = row.get("data1", "").strip()
        if not contact_name or not phone_number:
            continue
        memory.upsert_contact(
            contact_name=contact_name,
            phone_number=phone_number,
            source_app="contacts_provider",
            confidence=1.0,
        )
        discovered.append(
            {
                "contact_name": contact_name,
                "phone_number": phone_number,
            }
        )
    return discovered
