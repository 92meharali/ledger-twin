from __future__ import annotations

import logging
import re
import secrets
import string
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class TempMailError(RuntimeError):
    pass


def _base() -> str:
    return get_settings().temp_mail_api_base.rstrip("/")


def _client() -> httpx.Client:
    return httpx.Client(timeout=30.0)


def list_domains() -> List[str]:
    with _client() as client:
        r = client.get(f"{_base()}/domains")
        r.raise_for_status()
        data = r.json()
        members = data.get("hydra:member") or data.get("member") or []
        return [m.get("domain") for m in members if m.get("domain")]


def create_account(address: Optional[str] = None, password: Optional[str] = None) -> Dict[str, str]:
    domains = list_domains()
    if not domains:
        raise TempMailError("No mail.tm domains available")
    if not address:
        local = "ledger" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        address = f"{local}@{domains[0]}"
    if not password:
        password = "Lt!" + secrets.token_urlsafe(12)

    with _client() as client:
        r = client.post(
            f"{_base()}/accounts",
            json={"address": address, "password": password},
        )
        if r.status_code not in (200, 201):
            raise TempMailError(f"create account failed: {r.status_code} {r.text}")
        token = fetch_token(address, password)
        return {"address": address, "password": password, "token": token}


def fetch_token(address: str, password: str) -> str:
    with _client() as client:
        r = client.post(
            f"{_base()}/token",
            json={"address": address, "password": password},
        )
        if r.status_code != 200:
            raise TempMailError(f"token failed: {r.status_code} {r.text}")
        return r.json()["token"]


def ensure_token() -> str:
    settings = get_settings()
    if settings.temp_mail_token:
        return settings.temp_mail_token
    if settings.temp_mail_address and settings.temp_mail_password:
        token = fetch_token(settings.temp_mail_address, settings.temp_mail_password)
        return token
    raise TempMailError("TEMP_MAIL_ADDRESS/PASSWORD/TOKEN not configured")


def list_messages(token: Optional[str] = None) -> List[Dict[str, Any]]:
    token = token or ensure_token()
    with _client() as client:
        r = client.get(
            f"{_base()}/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code == 401:
            # refresh once
            settings = get_settings()
            token = fetch_token(settings.temp_mail_address, settings.temp_mail_password)
            r = client.get(
                f"{_base()}/messages",
                headers={"Authorization": f"Bearer {token}"},
            )
        r.raise_for_status()
        data = r.json()
        return data.get("hydra:member") or data.get("member") or []


def get_message(message_id: str, token: Optional[str] = None) -> Dict[str, Any]:
    token = token or ensure_token()
    with _client() as client:
        r = client.get(
            f"{_base()}/messages/{message_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json()


_AMOUNT_RE = re.compile(
    r"(?:\$|usd\s*)([\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_PAYMENT_HINT_RE = re.compile(
    r"(paid|payment|e-?transfer|wire|sent|transfer|invoice)",
    re.IGNORECASE,
)


def looks_like_payment_email(subject: str, body: str) -> bool:
    text = f"{subject}\n{body}"
    return bool(_PAYMENT_HINT_RE.search(text)) and bool(_AMOUNT_RE.search(text))


def parse_amount_cents(text: str) -> Optional[int]:
    m = _AMOUNT_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        dollars = float(raw)
    except ValueError:
        return None
    return int(round(dollars * 100))


def extract_name_hints(from_addr: str, subject: str, body: str) -> List[str]:
    hints: List[str] = []
    # Prefer explicit client line in body first (most reliable for demos)
    m2 = re.search(r"client[:\s]+([A-Za-z0-9 .'-]{2,60})", body or "", re.IGNORECASE)
    if m2:
        hints.append(m2.group(1).strip())
    m = re.search(r"from\s+([A-Z][A-Za-z .'-]{1,60})", body or "", re.IGNORECASE)
    if m:
        hints.append(m.group(1).strip())
    # display name in From header "Name <email>"
    if from_addr and "<" in from_addr:
        hints.append(from_addr.split("<", 1)[0].strip().strip('"'))
    # dedupe
    seen = set()
    out = []
    for h in hints:
        key = h.lower()
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out


def message_to_event_fields(msg: Dict[str, Any]) -> Dict[str, Any]:
    subject = msg.get("subject") or ""
    body = msg.get("text") or msg.get("intro") or ""
    if isinstance(msg.get("html"), list):
        # sometimes html is list of strings
        pass
    from_obj = msg.get("from") or {}
    if isinstance(from_obj, dict):
        from_addr = from_obj.get("address") or ""
        from_name = from_obj.get("name") or ""
    else:
        from_addr = str(from_obj)
        from_name = ""
    text = f"{subject}\n{body}"
    amount = parse_amount_cents(text)
    names = extract_name_hints(from_addr, subject, body)
    # Append From display name last (lowest priority) — body Client: wins
    if from_name and from_name.lower() not in {n.lower() for n in names}:
        names.append(from_name)
    emails = [from_addr] if from_addr else []
    return {
        "message_id": msg.get("id") or msg.get("@id") or "",
        "subject": subject,
        "body": body,
        "from_address": from_addr,
        "amount_cents": amount,
        "name_hints": names,
        "email_hints": emails,
        "is_payment": looks_like_payment_email(subject, body),
    }
