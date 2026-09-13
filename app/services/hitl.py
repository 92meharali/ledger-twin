from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app import pending_actions
from app.models import NormalizedEvent
from app.services import airtable_client, axiom_client

logger = logging.getLogger(__name__)


def set_pending_status(pending_id: str, status: str) -> None:
    pending_actions.init_pending_db()
    with pending_actions._db() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE pending_actions SET status = ? WHERE id = ?",
            (status, pending_id),
        )


def resolve_pending(pending_id: str, decision: str) -> Dict[str, Any]:
    """
    Local HITL (Slack substitute): approve | reject a pending action.
    """
    decision = decision.lower().strip()
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")

    item = pending_actions.get_pending(pending_id)
    if not item:
        raise KeyError(f"pending action not found: {pending_id}")
    if item["status"] != "pending":
        return {"status": item["status"], "message": "already resolved", "pending_id": pending_id}

    payload = item["payload"]
    event_data = payload.get("event") or {}
    entity = payload.get("entity") or {}
    match = payload.get("match") or {}
    client = entity.get("client") or {}
    triad = payload.get("triad") or {}

    if decision == "reject":
        set_pending_status(pending_id, "rejected")
        _log_decision(event_data, triad, "rejected", pending_id, "Human rejected; no ledger mutation")
        return {
            "status": "rejected",
            "pending_id": pending_id,
            "message": "Rejected — ledger unchanged",
        }

    # APPROVE
    amount = event_data.get("amount_cents")
    client_id = client.get("id")
    invoice = match.get("invoice")
    payment_id = None
    invoice_id = None

    if not client_id:
        set_pending_status(pending_id, "approved")
        return {"status": "approved", "pending_id": pending_id, "message": "Approved but no client on payload"}

    # Prefer existing invoice on payload; else open invoice with matching amount; else create one
    if invoice and invoice.get("id"):
        invoice_id = invoice["id"]
        airtable_client.mark_invoice_paid(invoice_id, remaining_cents=0)
    else:
        opens = airtable_client.list_open_invoices(client_id)
        exact = [
            i
            for i in opens
            if amount is not None and abs(int(i["remaining_cents"]) - int(amount)) <= 1
        ]
        if exact:
            invoice_id = exact[0]["id"]
            airtable_client.mark_invoice_paid(invoice_id, remaining_cents=0)
        else:
            # create invoice then close — so approve always has a concrete effect
            rec = airtable_client.invoices_table().create(
                {
                    "Name": f"INV-HITL-{event_data.get('external_id', 'x')[:18]}",
                    "ClientRecordId": client_id,
                    "ClientName": client.get("name") or "",
                    "AmountCents": int(amount or 0),
                    "RemainingCents": 0,
                    "Status": "paid",
                    "Currency": event_data.get("currency") or "usd",
                }
            )
            invoice_id = rec["id"]

    if amount is not None and invoice_id:
        payment_id = airtable_client.create_payment(
            client_record_id=client_id,
            invoice_record_id=invoice_id,
            amount_cents=int(amount),
            external_id=str(event_data.get("external_id") or pending_id),
            source=str(event_data.get("source") or "hitl"),
            status="posted",
        )

    set_pending_status(pending_id, "approved")
    _log_decision(
        event_data,
        {**triad, "who_acts": "human", "already_happened": "no"},
        "approved",
        pending_id,
        f"Human approved; invoice={invoice_id} payment={payment_id}",
    )
    return {
        "status": "approved",
        "pending_id": pending_id,
        "invoice_record_id": invoice_id,
        "payment_record_id": payment_id,
        "message": "Approved — ledger updated",
    }


def _log_decision(
    event_data: Dict[str, Any],
    triad: Dict[str, Any],
    status: str,
    pending_id: str,
    message: str,
) -> None:
    try:
        event = NormalizedEvent(
            source=str(event_data.get("source") or "hitl"),
            type="hitl.decision",
            external_id=f"hitl_{pending_id}",
            amount_cents=event_data.get("amount_cents"),
            currency=event_data.get("currency"),
            name_hints=event_data.get("name_hints") or [],
            email_hints=event_data.get("email_hints") or [],
            timestamp=datetime.now(timezone.utc),
            raw={"pending_id": pending_id, "event": event_data},
        )
        airtable_client.write_event_log(
            event=event,
            status=status,
            idempotency_key=f"hitl_{pending_id}_{status}",
            message=message,
            triad=triad,
        )
        axiom_client.ingest_event(
            event=event,
            status=status,
            idempotency_key=f"hitl_{pending_id}_{status}",
            message=message,
            extra={"triad": triad, "pending_id": pending_id},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("HITL log failed: %s", exc)
