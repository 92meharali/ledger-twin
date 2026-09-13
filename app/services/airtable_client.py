from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pyairtable import Api

from app.config import get_settings
from app.models import NormalizedEvent


def _api() -> Api:
    settings = get_settings()
    if not settings.airtable_api_key or not settings.airtable_base_id:
        raise RuntimeError("Airtable credentials missing")
    return Api(settings.airtable_api_key)


def _table(name: str):
    settings = get_settings()
    return _api().table(settings.airtable_base_id, name)


def event_log_table():
    return _table(get_settings().airtable_table_event_log)


def clients_table():
    return _table(get_settings().airtable_table_clients)


def invoices_table():
    return _table(get_settings().airtable_table_invoices)


def payments_table():
    return _table(get_settings().airtable_table_payments)


def write_event_log(
    *,
    event: NormalizedEvent,
    status: str,
    idempotency_key: str,
    message: str = "",
    triad: Optional[dict[str, Any]] = None,
    extra_fields: Optional[dict[str, Any]] = None,
) -> str:
    fields: dict[str, Any] = {
        "Name": f"{status} | {event.source}/{event.type} | {event.external_id}",
        "Status": status,
        "Source": event.source,
        "Type": event.type,
        "ExternalId": event.external_id,
        "IdempotencyKey": idempotency_key,
        "AmountCents": event.amount_cents,
        "Currency": event.currency,
        "EventDay": event.event_day(),
        "NameHints": ", ".join(event.name_hints) if event.name_hints else "",
        "EmailHints": ", ".join(event.email_hints) if event.email_hints else "",
        "Message": message,
        "Timestamp": event.timestamp.isoformat(),
        "RawJson": json.dumps(event.raw)[:100000],
    }
    if triad:
        fields["SameEntity"] = triad.get("same_entity", "")
        fields["AlreadyHappened"] = triad.get("already_happened", "")
        fields["WhoActs"] = triad.get("who_acts", "")
        fields["Confidence"] = triad.get("confidence")
    if extra_fields:
        # EventLog may not have these columns yet — append into Message safely
        bits = []
        for k, v in extra_fields.items():
            if v is not None and v != "":
                bits.append(f"{k}={v}")
        if bits:
            fields["Message"] = f"{fields.get('Message', '')} | " + "; ".join(bits)
            fields["Message"] = fields["Message"].strip(" |")


    clean = {k: v for k, v in fields.items() if v is not None and v != ""}
    record = event_log_table().create(clean)
    return record["id"]


def list_clients() -> List[Dict[str, Any]]:
    rows = clients_table().all()
    out = []
    for r in rows:
        f = r.get("fields") or {}
        out.append(
            {
                "id": r["id"],
                "name": f.get("Name") or "",
                "email": f.get("Email") or "",
                "aliases": f.get("Aliases") or "",
                "website": f.get("Website") or "",
                "needs_review": bool(f.get("NeedsReview")),
            }
        )
    return out


def create_client(
    *,
    name: str,
    email: str = "",
    aliases: str = "",
    website: str = "",
    needs_review: bool = True,
) -> Dict[str, Any]:
    fields: Dict[str, Any] = {
        "Name": name or "Unknown client",
        "NeedsReview": needs_review,
    }
    if email:
        fields["Email"] = email
    if aliases:
        fields["Aliases"] = aliases
    if website:
        fields["Website"] = website
    try:
        rec = clients_table().create(fields)
    except Exception:
        # Base may not have Website column yet — retry without it
        fields.pop("Website", None)
        rec = clients_table().create(fields)
    f = rec.get("fields") or {}
    return {
        "id": rec["id"],
        "name": f.get("Name") or name,
        "email": f.get("Email") or email,
        "aliases": f.get("Aliases") or aliases,
        "website": f.get("Website") or website,
        "needs_review": bool(f.get("NeedsReview", needs_review)),
    }


def upsert_client(
    *,
    name: str,
    email: str = "",
    aliases: str = "",
    website: str = "",
    needs_review: bool = False,
) -> Dict[str, Any]:
    existing = next((c for c in list_clients() if c.get("name") == name), None)
    if not existing:
        return create_client(
            name=name,
            email=email,
            aliases=aliases,
            website=website,
            needs_review=needs_review,
        )
    fields: Dict[str, Any] = {}
    if email and existing.get("email") != email:
        fields["Email"] = email
    if aliases and existing.get("aliases") != aliases:
        fields["Aliases"] = aliases
    if website and existing.get("website") != website:
        fields["Website"] = website
    if fields:
        try:
            clients_table().update(existing["id"], fields)
        except Exception:
            fields.pop("Website", None)
            if fields:
                clients_table().update(existing["id"], fields)
        return {**existing, "email": email or existing.get("email"), "aliases": aliases or existing.get("aliases"), "website": website or existing.get("website")}
    return existing


def list_open_invoices(client_record_id: str) -> List[Dict[str, Any]]:
    # Filter client-side for hackathon reliability (formula quirks)
    rows = invoices_table().all()
    out = []
    for r in rows:
        f = r.get("fields") or {}
        if f.get("ClientRecordId") != client_record_id:
            continue
        status = (f.get("Status") or "").lower()
        if status in {"paid", "closed", "void"}:
            continue
        out.append(
            {
                "id": r["id"],
                "name": f.get("Name") or "",
                "client_record_id": f.get("ClientRecordId") or "",
                "client_name": f.get("ClientName") or "",
                "amount_cents": int(f.get("AmountCents") or 0),
                "remaining_cents": int(
                    f.get("RemainingCents")
                    if f.get("RemainingCents") is not None
                    else (f.get("AmountCents") or 0)
                ),
                "status": f.get("Status") or "open",
                "currency": f.get("Currency") or "usd",
            }
        )
    return out


def mark_invoice_paid(invoice_id: str, *, remaining_cents: int = 0) -> None:
    invoices_table().update(
        invoice_id,
        {"Status": "paid", "RemainingCents": remaining_cents},
    )


def mark_invoice_partial(invoice_id: str, *, remaining_cents: int) -> None:
    invoices_table().update(
        invoice_id,
        {"Status": "partial", "RemainingCents": remaining_cents},
    )


def create_payment(
    *,
    client_record_id: str,
    invoice_record_id: str,
    amount_cents: int,
    external_id: str,
    source: str,
    status: str = "posted",
) -> str:
    rec = payments_table().create(
        {
            "Name": f"{source}:{external_id}",
            "ClientRecordId": client_record_id,
            "InvoiceRecordId": invoice_record_id,
            "AmountCents": amount_cents,
            "ExternalId": external_id,
            "Source": source,
            "Status": status,
        }
    )
    return rec["id"]


def get_invoice(invoice_id: str) -> Optional[Dict[str, Any]]:
    try:
        r = invoices_table().get(invoice_id)
    except Exception:  # noqa: BLE001
        return None
    f = r.get("fields") or {}
    return {
        "id": r["id"],
        "name": f.get("Name") or "",
        "client_record_id": f.get("ClientRecordId") or "",
        "client_name": f.get("ClientName") or "",
        "amount_cents": int(f.get("AmountCents") or 0),
        "remaining_cents": int(
            f.get("RemainingCents")
            if f.get("RemainingCents") is not None
            else (f.get("AmountCents") or 0)
        ),
        "status": f.get("Status") or "open",
        "currency": f.get("Currency") or "usd",
        "notes": f.get("Notes") or "",
    }


def list_all_invoices() -> List[Dict[str, Any]]:
    rows = invoices_table().all()
    out = []
    for r in rows:
        f = r.get("fields") or {}
        out.append(
            {
                "id": r["id"],
                "name": f.get("Name") or "",
                "client_record_id": f.get("ClientRecordId") or "",
                "client_name": f.get("ClientName") or "",
                "amount_cents": int(f.get("AmountCents") or 0),
                "remaining_cents": int(
                    f.get("RemainingCents")
                    if f.get("RemainingCents") is not None
                    else (f.get("AmountCents") or 0)
                ),
                "status": f.get("Status") or "open",
                "currency": f.get("Currency") or "usd",
                "notes": f.get("Notes") or "",
            }
        )
    return out


def update_invoice(invoice_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "Name",
        "ClientName",
        "ClientRecordId",
        "AmountCents",
        "RemainingCents",
        "Status",
        "Currency",
        "Notes",
    }
    clean = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not clean:
        inv = get_invoice(invoice_id)
        if not inv:
            raise KeyError("Invoice not found")
        return inv
    try:
        invoices_table().update(invoice_id, clean)
    except Exception:
        # Notes field may not exist yet — retry without Notes
        clean.pop("Notes", None)
        if clean:
            invoices_table().update(invoice_id, clean)
    inv = get_invoice(invoice_id)
    if not inv:
        raise KeyError("Invoice not found")
    return inv


def payments_for_invoice(invoice_id: str) -> List[Dict[str, Any]]:
    rows = payments_table().all()
    out = []
    for r in rows:
        f = r.get("fields") or {}
        if f.get("InvoiceRecordId") != invoice_id:
            continue
        out.append(
            {
                "id": r["id"],
                "name": f.get("Name") or "",
                "amount_cents": int(f.get("AmountCents") or 0),
                "status": f.get("Status") or "",
                "source": f.get("Source") or "",
                "external_id": f.get("ExternalId") or "",
            }
        )
    return out
