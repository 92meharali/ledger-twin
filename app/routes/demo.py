from __future__ import annotations

import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import pending_actions
from app.config import get_settings
from app.models import NormalizedEvent
from app.pipeline import process_normalized_event, process_stripe_payload
from app.services import airtable_client

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoStripeBody(BaseModel):
    """Minimal Stripe-shaped payload for local tests without Stripe CLI."""

    type: str = "payment_intent.succeeded"
    id: str = "evt_demo_1"
    created: Optional[int] = None
    data: dict = Field(
        default_factory=lambda: {
            "object": {
                "id": "pi_demo_1000",
                "amount": 100000,
                "currency": "usd",
                "billing_details": {
                    "name": "Jose Martinez Studio",
                    "email": "jose@example.com",
                },
                "metadata": {},
            }
        }
    )


def _require_demo() -> None:
    if not get_settings().demo_mode:
        raise HTTPException(status_code=403, detail="DEMO_MODE is off")


def _fresh_ids(prefix: str):
    suffix = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    return f"evt_{prefix}_{suffix}", f"pi_{prefix}_{suffix}"


def _ensure_open_invoice_1000() -> None:
    """Re-open or create INV-DEMO-1000 so exact-match demos stay runnable."""
    clients = airtable_client.list_clients()
    jose = next((c for c in clients if c.get("name") == "Jose Martinez Studio"), None)
    if not jose:
        jose = airtable_client.create_client(
            name="Jose Martinez Studio",
            email="jose@example.com",
            aliases="Jose Martinez, J Martinez",
            needs_review=False,
        )
    opens = airtable_client.list_open_invoices(jose["id"])
    if any(i.get("name") == "INV-DEMO-1000" for i in opens):
        return
    airtable_client.invoices_table().create(
        {
            "Name": "INV-DEMO-1000",
            "ClientRecordId": jose["id"],
            "ClientName": "Jose Martinez Studio",
            "AmountCents": 100000,
            "RemainingCents": 100000,
            "Status": "open",
            "Currency": "usd",
        }
    )


@router.post("/stripe-event")
def demo_stripe_event(body: DemoStripeBody) -> dict:
    _require_demo()
    return process_stripe_payload(body.model_dump()).model_dump(mode="json")


@router.post("/replay-normalized")
def demo_replay(event: NormalizedEvent) -> dict:
    _require_demo()
    return process_normalized_event(event).model_dump(mode="json")


@router.post("/scenario/exact-match")
def scenario_exact_match() -> dict:
    """Exact name + exact $1000 vs open INV-DEMO-1000 → auto_closed."""
    _require_demo()
    _ensure_open_invoice_1000()
    evt_id, pi_id = _fresh_ids("exact")
    body = DemoStripeBody(
        id=evt_id,
        data={
            "object": {
                "id": pi_id,
                "amount": 100000,
                "currency": "usd",
                "billing_details": {
                    "name": "Jose Martinez Studio",
                    "email": "jose@example.com",
                },
                "metadata": {},
            }
        },
    )
    return process_stripe_payload(body.model_dump()).model_dump(mode="json")


@router.post("/scenario/fuzzy-name")
def scenario_fuzzy_name() -> dict:
    """Middle-band name 'J. Martinez' + exact amount → pending_entity (strict)."""
    _require_demo()
    evt_id, pi_id = _fresh_ids("fuzzy")
    body = DemoStripeBody(
        id=evt_id,
        data={
            "object": {
                "id": pi_id,
                "amount": 100000,
                "currency": "usd",
                "billing_details": {
                    "name": "J. Martinez",
                    "email": "j.martinez@example.com",
                },
                "metadata": {},
            }
        },
    )
    return process_stripe_payload(body.model_dump()).model_dump(mode="json")


@router.post("/scenario/partial-pay")
def scenario_partial_pay() -> dict:
    """Exact client name but short amount → pending_partial, invoice not fully paid."""
    _require_demo()
    _ensure_open_invoice_1000()
    evt_id, pi_id = _fresh_ids("partial")
    body = DemoStripeBody(
        id=evt_id,
        data={
            "object": {
                "id": pi_id,
                "amount": 80000,
                "currency": "usd",
                "billing_details": {
                    "name": "Jose Martinez Studio",
                    "email": "jose@example.com",
                },
                "metadata": {},
            }
        },
    )
    return process_stripe_payload(body.model_dump()).model_dump(mode="json")


@router.get("/pending")
def list_pending() -> dict:
    _require_demo()
    return {"pending": pending_actions.list_pending()}


@router.post("/pending/{pending_id}/approve")
def approve_pending(pending_id: str) -> dict:
    """Local HITL approve (Slack substitute until Slack is wired)."""
    _require_demo()
    from app.services import hitl

    try:
        return hitl.resolve_pending(pending_id, "approve")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/pending/{pending_id}/reject")
def reject_pending(pending_id: str) -> dict:
    _require_demo()
    from app.services import hitl

    try:
        return hitl.resolve_pending(pending_id, "reject")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/killer")
def killer_demo() -> dict:
    """
    Killer demo path (Slack deferred → local HITL):
    1) wrong-name payment → pending_entity
    2) Approve
    3) identical payload again → blocked_duplicate
    4) return scorecard snapshot
    """
    _require_demo()
    from app.services import hitl, scorecard

    _ensure_open_invoice_1000()
    evt_id, pi_id = _fresh_ids("killer")
    payload = {
        "type": "payment_intent.succeeded",
        "id": evt_id,
        "data": {
            "object": {
                "id": pi_id,
                "amount": 100000,
                "currency": "usd",
                "billing_details": {
                    "name": "J. Martinez",
                    "email": "j.martinez@example.com",
                },
                "metadata": {},
            }
        },
    }
    first = process_stripe_payload(payload)
    if first.status != "pending_entity" or not first.pending_action_id:
        return {
            "ok": False,
            "summary": {
                "step1": first.model_dump(mode="json"),
                "error": "expected pending_entity from fuzzy name",
            },
        }
    approved = hitl.resolve_pending(first.pending_action_id, "approve")
    second = process_stripe_payload(payload)
    sc = scorecard.build_scorecard()
    return {
        "ok": second.status == "blocked_duplicate" and approved.get("status") == "approved",
        "summary": {
            "step1_wrong_name": first.status,
            "step2_approve": approved.get("status"),
            "step3_duplicate": second.status,
            "scorecard_duplicate_catch_rate": sc.get("duplicate_catch_rate"),
            "scorecard_eval_pass": f"{sc.get('eval_pass_count')}/{sc.get('eval_total')}",
            "pending_action_id": first.pending_action_id,
            "payment_intent": pi_id,
        },
        "scorecard": sc,
    }
