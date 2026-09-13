from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from app.config import get_settings


def _path() -> Path:
    return Path(get_settings().sqlite_path)


def init_pending_db() -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_actions (
                id TEXT PRIMARY KEY,
                external_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_pending(
    *,
    external_id: str,
    reason: str,
    payload: Dict[str, Any],
) -> str:
    init_pending_db()
    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO pending_actions (id, external_id, reason, payload_json, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (pid, external_id, reason, json.dumps(payload), now),
        )
    return pid


def list_pending(limit: int = 50) -> List[Dict[str, Any]]:
    init_pending_db()
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM pending_actions
            WHERE status = 'pending'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "external_id": r["external_id"],
                "reason": r["reason"],
                "payload": json.loads(r["payload_json"]),
                "status": r["status"],
                "created_at": r["created_at"],
            }
        )
    return out


def get_pending(pending_id: str) -> Optional[Dict[str, Any]]:
    init_pending_db()
    with _db() as conn:
        r = conn.execute(
            "SELECT * FROM pending_actions WHERE id = ?", (pending_id,)
        ).fetchone()
    if not r:
        return None
    return {
        "id": r["id"],
        "external_id": r["external_id"],
        "reason": r["reason"],
        "payload": json.loads(r["payload_json"]),
        "status": r["status"],
        "created_at": r["created_at"],
    }
