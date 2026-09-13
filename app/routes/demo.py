from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import pending_actions
from app.config import get_settings
from app.demo_catalog import DEMO_CLIENTS, by_key, stripe_event
from app.models import NormalizedEvent
from app.pipeline import process_normalized_event, process_stripe_payload
from app.services import airtable_client

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoStripeBody(BaseModel):
    """Minimal Stripe-shaped payload for local tests without Stripe CLI."""

    type: str = "payment_intent.succeeded"
    id: str = "evt_demo_1"
    created: Optional[int] = None
    data: dict = Field(default_factory=dict)


def _require_demo() -> None:
    if not get_settings().demo_mode:
        raise HTTPException(status_code=403, detail="DEMO_MODE is off")


def _fresh_ids(prefix: str):
    suffix = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    return f"evt_{prefix}_{suffix}", f"pi_{prefix}_{suffix}"


def _ensure_client(spec: Dict[str, Any]) -> Dict[str, Any]:
    return airtable_client.upsert_client(
        name=spec["name"],
        email=spec.get("email") or "",
        aliases=spec.get("aliases") or "",
        website=spec.get("website") or "",
        needs_review=False,
    )


def _ensure_named_open_invoice(
    *,
    client: Dict[str, Any],
    invoice_name: str,
    amount_cents: int,
) -> str:
    for inv in airtable_client.list_all_invoices():
        if inv.get("name") == invoice_name:
            airtable_client.update_invoice(
                inv["id"],
                {
                    "Status": "open",
                    "RemainingCents": amount_cents,
                    "AmountCents": amount_cents,
                    "ClientRecordId": client["id"],
                    "ClientName": client["name"],
                },
            )
            return inv["id"]
    rec = airtable_client.invoices_table().create(
        {
            "Name": invoice_name,
            "ClientRecordId": client["id"],
            "ClientName": client["name"],
            "AmountCents": amount_cents,
            "RemainingCents": amount_cents,
            "Status": "open",
            "Currency": "usd",
        }
    )
    return rec["id"]


def _ensure_open_invoice_1000() -> None:
    """Re-open Cursor INV-CURSOR-1000 so exact-match / killer demos stay runnable."""
    cursor = _ensure_client(by_key("cursor"))
    _ensure_named_open_invoice(
        client=cursor,
        invoice_name=by_key("cursor")["invoice_1000"],
        amount_cents=100000,
    )


def seed_open_invoices() -> dict:
    """Ensure brand clients + open invoices so portal 'To collect' is non-zero."""
    seeded_clients = []
    seeded_invoices = []
    invoice_plan = [
        ("cursor", "invoice_1000", 100000),
        ("cursor", "invoice_20", 2000),
        ("cursor", "invoice_450", 45000),
        ("slack", "invoice_1000", 100000),
        ("slack", "invoice_875", 87500),
        ("anthropic", "invoice_2500", 250000),
        ("stripe", "invoice_1200", 120000),
        ("notion", "invoice_360", 36000),
        ("linear", "invoice_199", 19900),
    ]
    clients_by_key: Dict[str, Dict[str, Any]] = {}
    for spec in DEMO_CLIENTS:
        client = _ensure_client(spec)
        clients_by_key[spec["key"]] = client
        seeded_clients.append(
            {
                "name": client["name"],
                "id": client["id"],
                "website": spec.get("website"),
            }
        )

    for key, inv_field, cents in invoice_plan:
        spec = by_key(key)
        inv_name = spec.get(inv_field)
        if not inv_name:
            continue
        client = clients_by_key[key]
        inv_id = _ensure_named_open_invoice(client=client, invoice_name=inv_name, amount_cents=cents)
        seeded_invoices.append(
            {
                "name": inv_name,
                "id": inv_id,
                "client": client["name"],
                "website": spec.get("website"),
                "usd": cents / 100,
            }
        )

    open_inv = [
        i
        for i in airtable_client.list_all_invoices()
        if str(i.get("status") or "").lower() in {"open", "partial"}
    ]
    to_collect = sum(int(i.get("remaining_cents") or 0) for i in open_inv) / 100
    return {
        "ok": True,
        "clients": seeded_clients,
        "seeded": seeded_invoices,
        "open_invoice_count": len(open_inv),
        "to_collect_usd": to_collect,
    }


@router.post("/seed-open-invoices")
def demo_seed_open_invoices() -> dict:
    _require_demo()
    return seed_open_invoices()


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
    """Exact Cursor + exact $1000 vs open INV-CURSOR-1000 → auto_closed."""
    _require_demo()
    _ensure_open_invoice_1000()
    cursor = by_key("cursor")
    evt_id, pi_id = _fresh_ids("exact")
    payload = stripe_event(evt_id=evt_id, pi_id=pi_id, amount_cents=100000, client=cursor)
    return process_stripe_payload(payload).model_dump(mode="json")


@router.post("/scenario/fuzzy-name")
def scenario_fuzzy_name() -> dict:
    """Middle-band name 'Curser' + exact amount → pending_entity (strict)."""
    _require_demo()
    _ensure_open_invoice_1000()
    cursor = by_key("cursor")
    evt_id, pi_id = _fresh_ids("fuzzy")
    payload = stripe_event(
        evt_id=evt_id,
        pi_id=pi_id,
        amount_cents=100000,
        client=cursor,
        name_override=cursor["fuzzy_name"],
    )
    return process_stripe_payload(payload).model_dump(mode="json")


@router.post("/scenario/partial-pay")
def scenario_partial_pay() -> dict:
    """Exact Slack name but short amount → pending_partial."""
    _require_demo()
    slack = by_key("slack")
    client = _ensure_client(slack)
    _ensure_named_open_invoice(client=client, invoice_name=slack["invoice_1000"], amount_cents=100000)
    evt_id, pi_id = _fresh_ids("partial")
    payload = stripe_event(evt_id=evt_id, pi_id=pi_id, amount_cents=80000, client=slack)
    return process_stripe_payload(payload).model_dump(mode="json")


@router.get("/pending")
def list_pending() -> dict:
    _require_demo()
    return {"pending": pending_actions.list_pending()}


@router.post("/pending/{pending_id}/approve")
def approve_pending(pending_id: str) -> dict:
    """HITL approve (same path Slack buttons use)."""
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


@router.post("/slack/ping")
def slack_ping() -> dict:
    """Post a sample Approve/Reject card to the configured Slack channel."""
    _require_demo()
    from app.services import slack_client

    if not slack_client.configured():
        raise HTTPException(
            status_code=400,
            detail="Slack not configured — set SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, SLACK_CHANNEL_ID",
        )
    cursor = by_key("cursor")
    ok, ts, err = slack_client.post_approval_card(
        pending_id="demo-ping-not-a-real-pending",
        reason="pending_entity",
        payload={
            "event": {
                "amount_cents": 100000,
                "currency": "usd",
                "name_hints": [cursor["fuzzy_name"]],
                "source": "demo",
            },
            "entity": {
                "client": {"name": cursor["name"], "website": cursor["website"]},
                "notes": f"Slack ping — {cursor['website']}",
            },
            "match": {"invoice": {"name": cursor["invoice_1000"]}, "message": "demo card"},
            "triad": {
                "same_entity": "uncertain",
                "already_happened": "no",
                "who_acts": "human",
                "confidence": 0.74,
            },
        },
    )
    return {"ok": ok, "ts": ts, "error": err}


@router.post("/killer")
def killer_demo() -> dict:
    """
    Killer demo path:
    1) wrong-name Cursor payment ('Curser') → pending_entity (+ Slack card)
    2) Approve
    3) identical payload again → blocked_duplicate
    4) return scorecard snapshot
    """
    _require_demo()
    from app.services import hitl, scorecard

    _ensure_open_invoice_1000()
    cursor = by_key("cursor")
    evt_id, pi_id = _fresh_ids("killer")
    payload = stripe_event(
        evt_id=evt_id,
        pi_id=pi_id,
        amount_cents=100000,
        client=cursor,
        name_override=cursor["fuzzy_name"],
    )
    first = process_stripe_payload(payload)
    if first.status != "pending_entity" or not first.pending_action_id:
        return {
            "ok": False,
            "summary": {
                "step1": first.model_dump(mode="json"),
                "error": "expected pending_entity from fuzzy name",
                "client": cursor["name"],
                "website": cursor["website"],
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
            "client": cursor["name"],
            "website": cursor["website"],
            "scorecard_duplicate_catch_rate": sc.get("duplicate_catch_rate"),
            "scorecard_eval_pass": f"{sc.get('eval_pass_count')}/{sc.get('eval_total')}",
            "pending_action_id": first.pending_action_id,
            "payment_intent": pi_id,
        },
        "scorecard": sc,
    }
