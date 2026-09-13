from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.config import get_settings
from app.models import NormalizedEvent
from app.services import airtable_client
from app.services.entity_resolve import EntityResolution


@dataclass
class MatchOutcome:
    action: str  # auto_closed | pending_partial | pending_entity | pending_no_invoice | pending_amount
    invoice: Optional[Dict[str, Any]] = None
    payment_id: Optional[str] = None
    delta_cents: Optional[int] = None
    message: str = ""
    who_acts: str = "human"
    confidence: float = 0.0


def match_payment_to_invoice(
    event: NormalizedEvent,
    entity: EntityResolution,
) -> MatchOutcome:
    settings = get_settings()
    client = entity.client
    if not client:
        return MatchOutcome(
            action="pending_entity",
            message="No client resolved",
            who_acts="human",
            confidence=0.1,
        )

    # Strict: only auto-close when RapidFuzz auto band (>=90) AND exact amount
    can_auto_entity = entity.band == "auto" and entity.same_entity == "yes"

    if entity.who_acts == "human" or not can_auto_entity:
        return MatchOutcome(
            action="pending_entity",
            message=entity.notes or "Entity confidence too low for auto-close",
            who_acts="human",
            confidence=entity.confidence,
            invoice=None,
        )

    if event.amount_cents is None:
        return MatchOutcome(
            action="pending_amount",
            message="Payment missing amount",
            who_acts="human",
            confidence=0.2,
        )

    invoices = airtable_client.list_open_invoices(client["id"])
    if not invoices:
        return MatchOutcome(
            action="pending_no_invoice",
            message=f"No open invoices for client {client.get('name')}",
            who_acts="human",
            confidence=entity.confidence,
        )

    tol = settings.amount_tolerance_cents
    exact = [
        inv
        for inv in invoices
        if abs(int(inv["remaining_cents"]) - int(event.amount_cents)) <= tol
    ]

    if exact:
        inv = exact[0]
        airtable_client.mark_invoice_paid(inv["id"], remaining_cents=0)
        payment_id = airtable_client.create_payment(
            client_record_id=client["id"],
            invoice_record_id=inv["id"],
            amount_cents=int(event.amount_cents),
            external_id=event.external_id,
            source=event.source,
            status="posted",
        )
        return MatchOutcome(
            action="auto_closed",
            invoice=inv,
            payment_id=payment_id,
            delta_cents=0,
            message=f"Auto-closed invoice {inv.get('name')} (exact amount + entity score>={settings.entity_auto_match_threshold})",
            who_acts="agent",
            confidence=entity.confidence,
        )

    # Near-miss: closest open invoice by remaining
    nearest = min(
        invoices,
        key=lambda inv: abs(int(inv["remaining_cents"]) - int(event.amount_cents)),
    )
    delta = int(event.amount_cents) - int(nearest["remaining_cents"])
    # Do NOT mark fully paid
    remaining = max(0, int(nearest["remaining_cents"]) - int(event.amount_cents))
    # Record as pending; optionally mark partial only if payment shorter and we still need human
    # Strict: leave status open/partial note via pending — mark partial for visibility without closing
    if int(event.amount_cents) < int(nearest["remaining_cents"]):
        airtable_client.mark_invoice_partial(nearest["id"], remaining_cents=remaining)
        airtable_client.create_payment(
            client_record_id=client["id"],
            invoice_record_id=nearest["id"],
            amount_cents=int(event.amount_cents),
            external_id=event.external_id,
            source=event.source,
            status="pending_review",
        )

    return MatchOutcome(
        action="pending_partial",
        invoice=nearest,
        delta_cents=delta,
        message=(
            f"Amount mismatch vs {nearest.get('name')}: "
            f"payment={event.amount_cents} remaining={nearest.get('remaining_cents')} delta={delta}. "
            "Not marked fully paid."
        ),
        who_acts="human",
        confidence=0.55,
    )
