from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class SQLiteMemory(object):
    """Minimal verified-memory storage for the MVP."""

    def __init__(self, db_path: str = "data/memory.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _managed_connect(self):
        return closing(self._connect())

    def _initialize(self) -> None:
        with self._managed_connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    preference_key TEXT NOT NULL UNIQUE,
                    preference_value TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS successful_trajectories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT,
                    app TEXT,
                    intent TEXT NOT NULL,
                    steps_summary TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    verified INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failure_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT,
                    app TEXT,
                    intent TEXT NOT NULL,
                    steps_summary TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    confidence REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS known_contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_name TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    source_app TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    last_seen_timestamp TEXT NOT NULL,
                    UNIQUE(contact_name, phone_number)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ui_shortcuts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT NOT NULL,
                    app TEXT NOT NULL DEFAULT '',
                    page TEXT NOT NULL,
                    intent_key TEXT NOT NULL,
                    skill TEXT NOT NULL,
                    args_json TEXT NOT NULL,
                    target_label TEXT NOT NULL DEFAULT '',
                    target_key TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    use_count INTEGER NOT NULL DEFAULT 1,
                    last_seen_timestamp TEXT NOT NULL,
                    UNIQUE(task_type, app, page, intent_key, skill, target_label, target_key)
                )
                """
            )
            self._ensure_column(conn, "successful_trajectories", "task_type", "TEXT")
            self._ensure_column(conn, "failure_patterns", "task_type", "TEXT")
            conn.commit()

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_type: str,
    ) -> None:
        rows = conn.execute("PRAGMA table_info({0})".format(table_name)).fetchall()
        existing = [row[1] for row in rows]
        if column_name not in existing:
            conn.execute(
                "ALTER TABLE {0} ADD COLUMN {1} {2}".format(
                    table_name, column_name, column_type
                )
            )

    def save_user_preference(
        self, preference_key: str, preference_value: str, confidence: float = 1.0
    ) -> None:
        timestamp = self._utc_now_iso()
        with self._managed_connect() as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (preference_key, preference_value, confidence, timestamp)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(preference_key) DO UPDATE SET
                    preference_value = excluded.preference_value,
                    confidence = excluded.confidence,
                    timestamp = excluded.timestamp
                """,
                (preference_key, preference_value, confidence, timestamp),
            )
            conn.commit()

    @staticmethod
    def _normalize_intent_key(intent: str) -> str:
        normalized = re.sub(r"\s+", " ", (intent or "").strip().lower())
        return normalized[:240]

    @staticmethod
    def _normalize_app_key(app: Optional[str]) -> str:
        candidate = str(app or "").strip()
        if not candidate:
            return ""
        if any(marker in candidate for marker in (" ", "=", "mCurrentFocus", "Window{")):
            return ""
        return candidate

    def remember_ui_shortcut(
        self,
        task_type: str,
        app: str,
        page: str,
        intent: str,
        skill: str,
        args: Dict[str, Any],
        confidence: float = 1.0,
    ) -> bool:
        if not task_type or not page or not intent or not skill:
            return False

        timestamp = self._utc_now_iso()
        safe_args = dict(args or {})
        args_json = json.dumps(safe_args, ensure_ascii=False, sort_keys=True)
        target_label = str(safe_args.get("target") or "").strip()
        target_key = str(safe_args.get("target_key") or "").strip()
        intent_key = self._normalize_intent_key(intent)

        with self._managed_connect() as conn:
            conn.execute(
                """
                INSERT INTO ui_shortcuts
                (task_type, app, page, intent_key, skill, args_json, target_label, target_key, confidence, use_count, last_seen_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(task_type, app, page, intent_key, skill, target_label, target_key) DO UPDATE SET
                    args_json = excluded.args_json,
                    confidence = CASE
                        WHEN excluded.confidence > ui_shortcuts.confidence THEN excluded.confidence
                        ELSE ui_shortcuts.confidence
                    END,
                    use_count = ui_shortcuts.use_count + 1,
                    last_seen_timestamp = excluded.last_seen_timestamp
                """,
                (
                    task_type,
                    self._normalize_app_key(app),
                    page,
                    intent_key,
                    skill,
                    args_json,
                    target_label,
                    target_key,
                    float(confidence),
                    timestamp,
                ),
            )
            conn.commit()
        return True

    @staticmethod
    def _screen_has_target(screen_summary: Dict[str, Any], target_label: str) -> bool:
        lowered = (target_label or "").strip().lower()
        if not lowered:
            return False
        for item in screen_summary.get("possible_targets", []):
            label = str((item or {}).get("label") or "").strip().lower()
            if label and (label == lowered or lowered in label or label in lowered):
                return True
        for item in screen_summary.get("visible_text", []):
            text = str(item).strip().lower()
            if text and (text == lowered or lowered in text or text in lowered):
                return True
        return False

    def find_ui_shortcut(
        self,
        task_type: str,
        app: Optional[str],
        page: str,
        intent: str,
        screen_summary: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not task_type or not page or not intent:
            return None

        intent_key = self._normalize_intent_key(intent)
        app_key = self._normalize_app_key(app)
        with self._managed_connect() as conn:
            rows = conn.execute(
                """
                SELECT app, page, intent_key, skill, args_json, target_label, target_key, confidence, use_count, last_seen_timestamp
                FROM ui_shortcuts
                WHERE task_type = ? AND page = ? AND intent_key = ? AND (app = ? OR app = '')
                ORDER BY CASE WHEN app = ? THEN 0 ELSE 1 END, confidence DESC, use_count DESC, last_seen_timestamp DESC
                LIMIT 5
                """,
                (task_type, page, intent_key, app_key, app_key),
            ).fetchall()

        summary = screen_summary or {}
        for row in rows:
            args = json.loads(row[4]) if row[4] else {}
            target_label = row[5] or str(args.get("target") or "").strip()
            target_key = row[6] or str(args.get("target_key") or "").strip()
            if target_label and not self._screen_has_target(summary, target_label) and not target_key:
                continue
            return {
                "app": row[0],
                "page": row[1],
                "intent_key": row[2],
                "skill": row[3],
                "args": args,
                "target_label": target_label,
                "target_key": target_key,
                "confidence": float(row[7]),
                "use_count": int(row[8]),
                "last_seen_timestamp": row[9],
            }
        return None

    def add_successful_trajectory(
        self,
        task_type: str,
        app: str,
        intent: str,
        steps_summary: str,
        confidence: float,
        verified: bool,
    ) -> bool:
        if not verified:
            return False
        timestamp = self._utc_now_iso()
        with self._managed_connect() as conn:
            conn.execute(
                """
                INSERT INTO successful_trajectories
                (task_type, app, intent, steps_summary, success, timestamp, confidence, verified)
                VALUES (?, ?, ?, ?, 1, ?, ?, 1)
                """,
                (task_type, app, intent, steps_summary, timestamp, confidence),
            )
            conn.commit()
        return True

    def add_failure_pattern(
        self,
        task_type: str,
        app: str,
        intent: str,
        steps_summary: str,
        confidence: float,
    ) -> None:
        timestamp = self._utc_now_iso()
        with self._managed_connect() as conn:
            conn.execute(
                """
                INSERT INTO failure_patterns
                (task_type, app, intent, steps_summary, success, timestamp, confidence)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (task_type, app, intent, steps_summary, timestamp, confidence),
            )
            conn.commit()

    def upsert_contact(
        self,
        contact_name: str,
        phone_number: str,
        source_app: str = "contacts_provider",
        confidence: float = 1.0,
    ) -> None:
        timestamp = self._utc_now_iso()
        with self._managed_connect() as conn:
            conn.execute(
                """
                INSERT INTO known_contacts
                (contact_name, phone_number, source_app, confidence, last_seen_timestamp)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(contact_name, phone_number) DO UPDATE SET
                    source_app = excluded.source_app,
                    confidence = excluded.confidence,
                    last_seen_timestamp = excluded.last_seen_timestamp
                """,
                (contact_name, phone_number, source_app, confidence, timestamp),
            )
            conn.commit()

    def list_contacts(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._managed_connect() as conn:
            cursor = conn.execute(
                """
                SELECT contact_name, phone_number, source_app, confidence, last_seen_timestamp
                FROM known_contacts
                ORDER BY confidence DESC, last_seen_timestamp DESC, contact_name ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return [
            {
                "contact_name": row[0],
                "phone_number": row[1],
                "source_app": row[2],
                "confidence": row[3],
                "last_seen_timestamp": row[4],
            }
            for row in rows
        ]

    def get_contact_by_name(self, contact_name: str) -> Optional[Dict[str, Any]]:
        with self._managed_connect() as conn:
            cursor = conn.execute(
                """
                SELECT contact_name, phone_number, source_app, confidence, last_seen_timestamp
                FROM known_contacts
                WHERE lower(contact_name) = lower(?)
                ORDER BY confidence DESC, last_seen_timestamp DESC
                LIMIT 1
                """,
                (contact_name,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "contact_name": row[0],
            "phone_number": row[1],
            "source_app": row[2],
            "confidence": row[3],
            "last_seen_timestamp": row[4],
        }

    def get_relevant_contacts(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        normalized = (query or "").strip().lower()
        if not normalized:
            return self.list_contacts(limit=limit)

        wildcard = "%{0}%".format(normalized.replace(" ", "%"))
        with self._managed_connect() as conn:
            cursor = conn.execute(
                """
                SELECT contact_name, phone_number, source_app, confidence, last_seen_timestamp
                FROM known_contacts
                WHERE lower(contact_name) LIKE ?
                   OR replace(lower(contact_name), ' ', '') LIKE replace(?, ' ', '')
                   OR lower(phone_number) LIKE ?
                ORDER BY confidence DESC, last_seen_timestamp DESC
                LIMIT ?
                """,
                (wildcard, wildcard, wildcard, limit),
            )
            rows = cursor.fetchall()
        return [
            {
                "contact_name": row[0],
                "phone_number": row[1],
                "source_app": row[2],
                "confidence": row[3],
                "last_seen_timestamp": row[4],
            }
            for row in rows
        ]

    def get_best_contact(self, prefer_ascii: bool = True) -> Optional[Dict[str, Any]]:
        contacts = self.list_contacts(limit=20)
        if prefer_ascii:
            for contact in contacts:
                if all(ord(char) < 128 for char in contact["contact_name"]):
                    return contact
        return contacts[0] if contacts else None

    def get_relevant_successes(
        self,
        task_type: str,
        app: Optional[str] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        return self._get_relevant_rows(
            table_name="successful_trajectories",
            task_type=task_type,
            app=app,
            limit=limit,
            verified_only=True,
        )

    def get_relevant_failures(
        self,
        task_type: str,
        app: Optional[str] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        return self._get_relevant_rows(
            table_name="failure_patterns",
            task_type=task_type,
            app=app,
            limit=limit,
            verified_only=False,
        )

    def _get_relevant_rows(
        self,
        table_name: str,
        task_type: str,
        app: Optional[str],
        limit: int,
        verified_only: bool,
    ) -> List[Dict[str, Any]]:
        clauses = ["task_type = ?"]
        params: List[Any] = [task_type]
        if app:
            clauses.append("(app = ? OR app IS NULL OR app = '')")
            params.append(app)
        if verified_only and table_name == "successful_trajectories":
            clauses.append("verified = 1")
        query = """
            SELECT task_type, app, intent, steps_summary, success, timestamp, confidence
            FROM {0}
            WHERE {1}
            ORDER BY confidence DESC, timestamp DESC
            LIMIT ?
        """.format(table_name, " AND ".join(clauses))
        params.append(limit)

        with self._managed_connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "task_type": row[0],
                "app": row[1],
                "intent": row[2],
                "steps_summary": row[3],
                "success": bool(row[4]),
                "timestamp": row[5],
                "confidence": row[6],
                "source": "success" if table_name == "successful_trajectories" else "failure",
            }
            for row in rows
        ]

    def get_relevant_memories(
        self, intent: str, app: Optional[str] = None, limit: int = 3
    ) -> List[Dict[str, Any]]:
        intent_like = "%{0}%".format(intent)
        params = [intent_like]
        app_clause = ""
        if app:
            app_clause = " OR app = ?"
            params.append(app)

        query = """
            SELECT task_type, app, intent, steps_summary, success, timestamp, confidence, 'success' AS source
            FROM successful_trajectories
            WHERE verified = 1 AND (intent LIKE ? {0})
            UNION ALL
            SELECT task_type, app, intent, steps_summary, success, timestamp, confidence, 'failure' AS source
            FROM failure_patterns
            WHERE intent LIKE ? {0}
            ORDER BY confidence DESC, timestamp DESC
            LIMIT ?
        """.format(app_clause)
        union_params = params + params + [limit]

        with self._managed_connect() as conn:
            cursor = conn.execute(query, union_params)
            rows = cursor.fetchall()

        memories = []
        for row in rows:
            memories.append(
                {
                    "task_type": row[0],
                    "app": row[1],
                    "intent": row[2],
                    "steps_summary": row[3],
                    "success": bool(row[4]),
                    "timestamp": row[5],
                    "confidence": row[6],
                    "source": row[7],
                }
            )
        return memories
