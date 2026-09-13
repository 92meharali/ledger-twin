from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from app.config import get_settings
from app.models import NormalizedEvent


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    Path(settings.idempotency_db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.idempotency_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_idempotency_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                hash TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                amount_cents INTEGER,
                event_day TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blocked_duplicates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT NOT NULL,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                amount_cents INTEGER,
                event_day TEXT NOT NULL,
                blocked_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def compute_idempotency_key(event: NormalizedEvent) -> str:
    amount = "" if event.amount_cents is None else str(event.amount_cents)
    material = "|".join(
        [
            event.source,
            event.external_id,
            amount,
            event.event_day(),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def try_claim(event: NormalizedEvent) -> tuple[bool, str]:
    """
    Returns (claimed, key).
    claimed=True means first time (proceed).
    claimed=False means duplicate (block).
    """
    key = compute_idempotency_key(event)
    now = datetime.now(timezone.utc).isoformat()
    with db() as conn:
        try:
            conn.execute(
                """
                INSERT INTO idempotency_keys
                    (hash, source, external_id, amount_cents, event_day, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    event.source,
                    event.external_id,
                    event.amount_cents,
                    event.event_day(),
                    now,
                ),
            )
            return True, key
        except sqlite3.IntegrityError:
            conn.execute(
                """
                INSERT INTO blocked_duplicates
                    (hash, source, external_id, amount_cents, event_day, blocked_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    event.source,
                    event.external_id,
                    event.amount_cents,
                    event.event_day(),
                    now,
                ),
            )
            return False, key


def blocked_count() -> int:
    with db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM blocked_duplicates").fetchone()
        return int(row["c"] if row else 0)


def claimed_count() -> int:
    with db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM idempotency_keys").fetchone()
        return int(row["c"] if row else 0)


def lookup_key(key: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM idempotency_keys WHERE hash = ?", (key,)
        ).fetchone()
        return dict(row) if row else None
