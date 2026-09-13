from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel, Field

from app import idempotency, pending_actions
from app.auth import get_current_user
from app.config import get_settings
from app.services import airtable_client, scorecard
from app.services.hitl import resolve_pending

router = APIRouter(prefix="/api/user", tags=["user-dashboard"])


def _money(cents: Any) -> float:
    try:
        return round(int(cents or 0) / 100.0, 2)
    except Exception:
        return 0.0


def _invoice_view(inv: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **inv,
        "amount": _money(inv.get("amount_cents")),
        "remaining": _money(inv.get("remaining_cents")),
    }


@router.get("/overview")
def user_overview(user: dict = Depends(get_current_user)) -> dict:
    settings = get_settings()
    sc = scorecard.build_scorecard()

    clients: List[Dict[str, Any]] = []
    try:
        clients = airtable_client.list_clients()
    except Exception:
        clients = []

    invoices: List[Dict[str, Any]] = []
    try:
        invoices = [_invoice_view(i) for i in airtable_client.list_all_invoices()]
    except Exception:
        invoices = []

    payments: List[Dict[str, Any]] = []
    try:
        for r in airtable_client.payments_table().all():
            f = r.get("fields") or {}
            payments.append(
                {
                    "id": r["id"],
                    "name": f.get("Name"),
                    "status": f.get("Status"),
                    "amount": _money(f.get("AmountCents")),
                    "source": f.get("Source"),
                    "external_id": f.get("ExternalId"),
                    "invoice_record_id": f.get("InvoiceRecordId"),
                }
            )
    except Exception:
        payments = []

    open_invoices = [i for i in invoices if str(i.get("status") or "").lower() in {"open", "partial"}]
    paid_invoices = [i for i in invoices if str(i.get("status") or "").lower() == "paid"]
    open_amount = sum(float(i.get("remaining") or 0) for i in open_invoices)
    collected = sum(float(p.get("amount") or 0) for p in payments if str(p.get("status")) == "posted")
    pending = pending_actions.list_pending()

    have, missing = [], []

    def flag(ok: bool, label: str, detail: str) -> None:
        (have if ok else missing).append({"label": label, "detail": detail})

    flag(bool(settings.stripe_secret_key), "Stripe", "Connected for payment events")
    flag(bool(settings.airtable_api_key), "Airtable ledger", "Clients, invoices, payments")
    flag(bool(settings.axiom_token), "Axiom logs", "Live agent observability")
    flag(bool(settings.temp_mail_address), "Temp mail inbox", settings.temp_mail_address or "Not set up")
    flag(bool(settings.openai_api_key), "AI matching", "OpenAI entity judge ready")
    flag(bool(settings.slack_bot_token), "Slack alerts", "Not connected — approve in app instead")
    flag(len(clients) > 0, "Clients", f"{len(clients)} on file")
    flag(len(invoices) > 0, "Invoices", f"{len(invoices)} total")

    return {
        "user": user,
        "summary": {
            "clients": len(clients),
            "open_invoices": len(open_invoices),
            "paid_invoices": len(paid_invoices),
            "open_amount_usd": round(open_amount, 2),
            "collected_usd": round(collected, 2),
            "pending_actions": len(pending),
            "eval_pass": f"{sc.get('eval_pass_count', 0)}/{sc.get('eval_total', 0)}",
            "events_processed": idempotency.claimed_count(),
            "duplicates_blocked": idempotency.blocked_count(),
        },
        "have": have,
        "missing": missing,
        "charts": {
            "status": {
                "labels": ["Paid", "Open/Partial", "Pending tasks", "Dup blocked"],
                "values": [
                    len(paid_invoices),
                    len(open_invoices),
                    len(pending),
                    idempotency.blocked_count(),
                ],
            },
            "reliability": {
                "labels": ["Entity %", "Dup catch %", "Escalation %"],
                "values": [
                    round((sc.get("entity_resolution_accuracy") or 0) * 100, 1),
                    round((sc.get("duplicate_catch_rate") or 0) * 100, 1),
                    round((sc.get("escalation_rate") or 0) * 100, 1),
                ],
            },
        },
        "invoices": invoices,
        "recent_payments": payments[::-1][:12],
        "pending_actions": pending[:12],
        "integrations": {
            "temp_mail_address": settings.temp_mail_address,
            "axiom_dataset": settings.axiom_dataset,
        },
    }


@router.get("/invoices")
def list_invoices(user: dict = Depends(get_current_user)) -> dict:
    try:
        invoices = [_invoice_view(i) for i in airtable_client.list_all_invoices()]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"invoices": invoices}


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: str, user: dict = Depends(get_current_user)) -> dict:
    inv = airtable_client.get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    payments = [
        {**p, "amount": _money(p.get("amount_cents"))}
        for p in airtable_client.payments_for_invoice(invoice_id)
    ]
    return {"invoice": _invoice_view(inv), "payments": payments}


class InvoiceUpdate(BaseModel):
    name: Optional[str] = None
    client_name: Optional[str] = None
    status: Optional[str] = None
    currency: Optional[str] = None
    notes: Optional[str] = None
    amount_usd: Optional[float] = None
    remaining_usd: Optional[float] = None


@router.patch("/invoices/{invoice_id}")
def patch_invoice(
    invoice_id: str,
    body: InvoiceUpdate,
    user: dict = Depends(get_current_user),
) -> dict:
    fields: Dict[str, Any] = {}
    if body.name is not None:
        fields["Name"] = body.name
    if body.client_name is not None:
        fields["ClientName"] = body.client_name
    if body.status is not None:
        fields["Status"] = body.status
    if body.currency is not None:
        fields["Currency"] = body.currency
    if body.notes is not None:
        fields["Notes"] = body.notes
    if body.amount_usd is not None:
        fields["AmountCents"] = int(round(body.amount_usd * 100))
    if body.remaining_usd is not None:
        fields["RemainingCents"] = int(round(body.remaining_usd * 100))
    try:
        inv = airtable_client.update_invoice(invoice_id, fields)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"invoice": _invoice_view(inv)}


@router.get("/history")
def history(user: dict = Depends(get_current_user)) -> dict:
    events = scorecard.list_recent_events(60)
    pending = pending_actions.list_pending(50)
    return {
        "events": events,
        "pending": pending,
        "idempotency": {
            "claimed": idempotency.claimed_count(),
            "blocked": idempotency.blocked_count(),
        },
    }


@router.post("/tasks/{pending_id}/{decision}")
def task_decision(
    pending_id: str,
    decision: str,
    user: dict = Depends(get_current_user),
) -> dict:
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be approve or reject")
    try:
        return resolve_pending(pending_id, decision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/portal")
def portal_page():
    path = Path(__file__).resolve().parent.parent / "static" / "portal.html"
    return FileResponse(path)
