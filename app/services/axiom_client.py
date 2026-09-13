from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.models import NormalizedEvent


def _ingest_url() -> str:
    settings = get_settings()
    edge = settings.axiom_edge.strip() or "api.axiom.co"
    edge = edge.replace("https://", "").replace("http://", "")
    return f"https://{edge}/v1/ingest/{settings.axiom_dataset}"


def ingest_event(
    *,
    event: NormalizedEvent,
    status: str,
    idempotency_key: str,
    message: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> bool:
    settings = get_settings()
    if not settings.axiom_token:
        return False

    payload = [
        {
            "_time": datetime.now(timezone.utc).isoformat(),
            "service": "ledger-twin",
            "status": status,
            "source": event.source,
            "type": event.type,
            "external_id": event.external_id,
            "idempotency_key": idempotency_key,
            "amount_cents": event.amount_cents,
            "currency": event.currency,
            "event_day": event.event_day(),
            "name_hints": event.name_hints,
            "email_hints": event.email_hints,
            "message": message,
            **(extra or {}),
        }
    ]

    headers = {
        "Authorization": f"Bearer {settings.axiom_token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(_ingest_url(), headers=headers, json=payload)
        resp.raise_for_status()
    return True
