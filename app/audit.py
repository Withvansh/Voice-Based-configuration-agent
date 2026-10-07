"""SQLite audit logging for dialogue steps and device operations."""

from datetime import datetime, timezone
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional


DEFAULT_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "audit.db")
)


def init_audit_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize audit database table if not present."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                session_id TEXT NOT NULL,
                step TEXT NOT NULL,
                detail_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def log_audit(
    session_id: str,
    step: str,
    detail: Any,
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    """Insert an audit entry and return the row id."""
    init_audit_db(db_path)
    ts = datetime.now(timezone.utc).isoformat()
    if isinstance(detail, str):
        detail_json = detail
    else:
        detail_json = json.dumps(detail, default=str)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit (ts, session_id, step, detail_json)
            VALUES (?, ?, ?, ?)
            """,
            (ts, session_id, step, detail_json),
        )
        conn.commit()
        return cursor.lastrowid or 0


def get_audit_logs(
    session_id: Optional[str] = None,
    limit: int = 50,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    """Retrieve audit logs ordered newest first."""
    init_audit_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        if session_id:
            cursor.execute(
                """
                SELECT id, ts, session_id, step, detail_json
                FROM audit
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT id, ts, session_id, step, detail_json
                FROM audit
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
        rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "ts": row[1],
            "session_id": row[2],
            "step": row[3],
            "detail_json": row[4],
        }
        for row in rows
    ]
