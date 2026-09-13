from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from app.config import get_settings


def _path() -> Path:
    return Path(get_settings().sqlite_path)


def init_eval_db() -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eval_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                pass_count INTEGER NOT NULL,
                total INTEGER NOT NULL,
                results_json TEXT NOT NULL
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


def save_eval_run(run_id: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    import json

    init_eval_db()
    pass_count = sum(1 for r in results if r.get("pass"))
    total = len(results)
    now = datetime.now(timezone.utc).isoformat()
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO eval_runs (run_id, created_at, pass_count, total, results_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, now, pass_count, total, json.dumps(results)),
        )
    return {
        "run_id": run_id,
        "created_at": now,
        "pass_count": pass_count,
        "total": total,
        "results": results,
    }


def latest_eval() -> Optional[Dict[str, Any]]:
    import json

    init_eval_db()
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM eval_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "created_at": row["created_at"],
        "pass_count": row["pass_count"],
        "total": row["total"],
        "results": json.loads(row["results_json"]),
    }
