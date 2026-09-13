from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.models import NormalizedEvent
from app.pipeline import process_normalized_event
from app.services import tempmail

logger = logging.getLogger(__name__)


def ingest_tempmail_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    fields = tempmail.message_to_event_fields(msg)
    mid = str(fields["message_id"]).split("/")[-1] or fields["message_id"]
    if not fields["is_payment"]:
        return {
            "status": "ignored",
            "message_id": mid,
            "reason": "not a payment-like email",
            "subject": fields["subject"],
        }
    if fields["amount_cents"] is None:
        return {
            "status": "ignored",
            "message_id": mid,
            "reason": "no amount found",
            "subject": fields["subject"],
        }

    event = NormalizedEvent(
        source="temp_mail",
        type="email.payment_signal",
        external_id=f"mail_{mid}",
        amount_cents=fields["amount_cents"],
        currency="usd",
        name_hints=fields["name_hints"] or ["Unknown payer"],
        email_hints=fields["email_hints"],
        timestamp=datetime.now(timezone.utc),
        raw={"mail": msg, "parsed": fields},
    )
    # Prefer body "Client:" hint over From display name for entity resolve
    if fields["name_hints"]:
        event.name_hints = fields["name_hints"]

    result = process_normalized_event(event)
    out = result.model_dump(mode="json")
    out["temp_mail"] = {
        "message_id": mid,
        "subject": fields["subject"],
        "from": fields["from_address"],
    }
    return out


def poll_and_ingest(limit: int = 20) -> Dict[str, Any]:
    from app.services import axiom_client

    try:
        axiom_client.ingest_raw(
            kind="temp_mail_poll",
            status="started",
            message="Temp-mail inbox poll started",
            fields={"limit": limit},
        )
    except Exception:  # noqa: BLE001
        pass

    messages = tempmail.list_messages()
    results: List[Dict[str, Any]] = []
    for summary in messages[:limit]:
        mid = summary.get("id")
        if not mid:
            continue
        try:
            full = tempmail.get_message(mid)
            results.append(ingest_tempmail_message(full))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed ingesting temp-mail %s: %s", mid, exc)
            results.append({"status": "error", "message_id": mid, "error": str(exc)})

    payment_hits = sum(1 for r in results if r.get("status") not in {"ignored", "error", None})
    try:
        axiom_client.ingest_raw(
            kind="temp_mail_poll",
            status="completed",
            message=f"Temp-mail poll finished — {len(results)} processed, {payment_hits} payment signals",
            fields={
                "fetched": len(messages),
                "processed": len(results),
                "payment_hits": payment_hits,
            },
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "inbox": True,
        "fetched": len(messages),
        "processed": len(results),
        "results": results,
    }
