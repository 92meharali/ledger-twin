from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.models import NormalizedEvent


def _ts(value: Optional[int]) -> datetime:
    if value:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _name_hints_from_charge_or_pi(obj: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    billing = obj.get("billing_details") or {}
    if isinstance(billing, dict) and billing.get("name"):
        hints.append(str(billing["name"]))
    metadata = obj.get("metadata") or {}
    if isinstance(metadata, dict):
        for key in ("customer_name", "name", "client_name", "company"):
            if metadata.get(key):
                hints.append(str(metadata[key]))
    shipping = obj.get("shipping") or {}
    if isinstance(shipping, dict) and shipping.get("name"):
        hints.append(str(shipping["name"]))
    # dedupe preserve order
    seen = set()
    out = []
    for h in hints:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def _email_hints(obj: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    billing = obj.get("billing_details") or {}
    if isinstance(billing, dict) and billing.get("email"):
        hints.append(str(billing["email"]))
    receipt = obj.get("receipt_email")
    if receipt:
        hints.append(str(receipt))
    metadata = obj.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("email"):
        hints.append(str(metadata["email"]))
    customer_email = obj.get("customer_email")
    if customer_email:
        hints.append(str(customer_email))
    seen = set()
    out = []
    for h in hints:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def normalize_stripe_event(stripe_event: dict[str, Any]) -> NormalizedEvent:
    event_type = stripe_event.get("type") or "unknown"
    data_object = (stripe_event.get("data") or {}).get("object") or {}
    if not isinstance(data_object, dict):
        data_object = {}

    external_id = (
        data_object.get("id")
        or stripe_event.get("id")
        or f"missing-{stripe_event.get('created', 'x')}"
    )

    amount_cents = data_object.get("amount_received")
    if amount_cents is None:
        amount_cents = data_object.get("amount_paid")
    if amount_cents is None:
        amount_cents = data_object.get("amount")
    if amount_cents is not None:
        amount_cents = int(amount_cents)

    currency = data_object.get("currency")
    created = stripe_event.get("created") or data_object.get("created")

    return NormalizedEvent(
        source="stripe",
        type=event_type,
        external_id=str(external_id),
        amount_cents=amount_cents,
        currency=currency,
        name_hints=_name_hints_from_charge_or_pi(data_object),
        email_hints=_email_hints(data_object),
        timestamp=_ts(created if isinstance(created, int) else None),
        raw=stripe_event,
    )
