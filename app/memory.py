from __future__ import annotations

import sqlite3
from datetime import datetime
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

    def _initialize(self) -> None:
        with self._connect() as conn:
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
            conn.commit()

    def save_user_preference(
        self, preference_key: str, preference_value: str, confidence: float = 1.0
    ) -> None:
        timestamp = datetime.utcnow().isoformat()
        with self._connect() as conn:
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

    def add_successful_trajectory(
        self,
        app: str,
        intent: str,
        steps_summary: str,
        confidence: float,
        verified: bool,
    ) -> bool:
        if not verified:
            return False
        timestamp = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO successful_trajectories
                (app, intent, steps_summary, success, timestamp, confidence, verified)
                VALUES (?, ?, ?, 1, ?, ?, 1)
                """,
                (app, intent, steps_summary, timestamp, confidence),
            )
            conn.commit()
        return True

    def add_failure_pattern(
        self, app: str, intent: str, steps_summary: str, confidence: float
    ) -> None:
        timestamp = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO failure_patterns
                (app, intent, steps_summary, success, timestamp, confidence)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (app, intent, steps_summary, timestamp, confidence),
            )
            conn.commit()

    def upsert_contact(
        self,
        contact_name: str,
        phone_number: str,
        source_app: str = "contacts_provider",
        confidence: float = 1.0,
    ) -> None:
        timestamp = datetime.utcnow().isoformat()
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
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

    def get_best_contact(self, prefer_ascii: bool = True) -> Optional[Dict[str, Any]]:
        contacts = self.list_contacts(limit=20)
        if prefer_ascii:
            for contact in contacts:
                if all(ord(char) < 128 for char in contact["contact_name"]):
                    return contact
        return contacts[0] if contacts else None

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
            SELECT app, intent, steps_summary, success, timestamp, confidence, 'success' AS source
            FROM successful_trajectories
            WHERE verified = 1 AND (intent LIKE ? {0})
            UNION ALL
            SELECT app, intent, steps_summary, success, timestamp, confidence, 'failure' AS source
            FROM failure_patterns
            WHERE intent LIKE ? {0}
            ORDER BY confidence DESC, timestamp DESC
            LIMIT ?
        """.format(app_clause)
        union_params = params + params + [limit]

        with self._connect() as conn:
            cursor = conn.execute(query, union_params)
            rows = cursor.fetchall()

        memories = []
        for row in rows:
            memories.append(
                {
                    "app": row[0],
                    "intent": row[1],
                    "steps_summary": row[2],
                    "success": bool(row[3]),
                    "timestamp": row[4],
                    "confidence": row[5],
                    "source": row[6],
                }
            )
        return memories
