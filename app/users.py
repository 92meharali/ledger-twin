from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from passlib.context import CryptContext

from app.config import get_settings

# pbkdf2_sha256 avoids the broken passlib↔bcrypt 4.x interaction that rejects
# short passwords with "password cannot be longer than 72 bytes".
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

DEMO_EMAIL = "demo@ledgertwin.dev"
DEMO_PASSWORD = "demo1234"


def _path() -> Path:
    return Path(get_settings().sqlite_path)


def init_users_db() -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL DEFAULT '',
                company TEXT NOT NULL DEFAULT '',
                bio TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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


def _row_to_user(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "full_name": row["full_name"] or "",
        "company": row["company"] or "",
        "bio": row["bio"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_user(*, email: str, password: str, full_name: str = "", company: str = "") -> Dict[str, Any]:
    init_users_db()
    email = email.strip().lower()
    now = datetime.now(timezone.utc).isoformat()
    uid = str(uuid.uuid4())
    password_hash = pwd_context.hash(password)
    with _db() as conn:
        try:
            conn.execute(
                """
                INSERT INTO users (id, email, password_hash, full_name, company, bio, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, '', ?, ?)
                """,
                (uid, email, password_hash, full_name.strip(), company.strip(), now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Email already registered") from exc
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return _row_to_user(row)


def authenticate(email: str, password: str) -> Optional[Dict[str, Any]]:
    init_users_db()
    email = email.strip().lower()
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row:
        return None
    try:
        if not pwd_context.verify(password, row["password_hash"]):
            return None
    except Exception:
        return None
    return _row_to_user(row)


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    init_users_db()
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    init_users_db()
    email = email.strip().lower()
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return _row_to_user(row) if row else None


def update_user(user_id: str, **fields: str) -> Dict[str, Any]:
    init_users_db()
    allowed = {"full_name", "company", "bio", "email"}
    updates = {k: v.strip() if isinstance(v, str) else v for k, v in fields.items() if k in allowed and v is not None}
    if "email" in updates:
        updates["email"] = updates["email"].lower()
    if not updates:
        user = get_user(user_id)
        if not user:
            raise KeyError("User not found")
        return user
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    sets = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [user_id]
    with _db() as conn:
        try:
            conn.execute(f"UPDATE users SET {sets} WHERE id = ?", vals)
        except sqlite3.IntegrityError as exc:
            raise ValueError("Email already in use") from exc
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise KeyError("User not found")
    return _row_to_user(row)


def delete_user(user_id: str) -> None:
    init_users_db()
    with _db() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        if cur.rowcount == 0:
            raise KeyError("User not found")


def list_users() -> List[Dict[str, Any]]:
    init_users_db()
    with _db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    return [_row_to_user(r) for r in rows]


def ensure_demo_user() -> Dict[str, Any]:
    """
    Create or reset the hackathon demo account so login always works on
    ephemeral serverless storage (/tmp SQLite on Vercel).
    """
    init_users_db()
    email = DEMO_EMAIL
    password_hash = pwd_context.hash(DEMO_PASSWORD)
    now = datetime.now(timezone.utc).isoformat()
    with _db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?, full_name = ?, company = ?, updated_at = ?
                WHERE email = ?
                """,
                (password_hash, "Demo User", "Cursor", now, email),
            )
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            return _row_to_user(row)
        uid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO users (id, email, password_hash, full_name, company, bio, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, '', ?, ?)
            """,
            (uid, email, password_hash, "Demo User", "Cursor", now, now),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return _row_to_user(row)
