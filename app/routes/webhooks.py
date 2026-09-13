from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.parse import parse_qs

import stripe
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, Response

from app.config import get_settings
from app.pipeline import process_stripe_payload
from app.services import hitl, slack_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    settings = get_settings()
    payload = await request.body()

    if settings.stripe_webhook_secret:
        if not stripe_signature:
            raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=stripe_signature,
                secret=settings.stripe_webhook_secret,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid payload: {exc}") from exc
        except Exception as exc:  # SignatureVerificationError across stripe SDK versions
            name = type(exc).__name__
            if "Signature" in name or "signature" in str(exc).lower():
                raise HTTPException(status_code=400, detail=f"Invalid signature: {exc}") from exc
            raise
        event_dict = event.to_dict() if hasattr(event, "to_dict") else dict(event)
    else:
        # Demo / pre-CLI mode: accept raw JSON so we can test idempotency locally
        if not settings.demo_mode:
            raise HTTPException(
                status_code=500,
                detail="STRIPE_WEBHOOK_SECRET not set. Run: stripe listen --forward-to localhost:8000/webhooks/stripe",
            )
        try:
            event_dict = await request.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    # Only handle the events we care about; ack others
    event_type = event_dict.get("type", "")
    if event_type not in {"payment_intent.succeeded", "invoice.paid"}:
        return {
            "status": "ignored",
            "type": event_type,
            "message": "Event type not in allowlist; acknowledged",
        }

    result = process_stripe_payload(event_dict)
    return result.model_dump(mode="json")


def _process_slack_decision(parsed: dict[str, str]) -> None:
    pending_id = parsed["pending_id"]
    decision = parsed["decision"]
    response_url = parsed.get("response_url") or ""
    user = parsed.get("user") or "slack"
    try:
        result = hitl.resolve_pending(pending_id, decision)
        msg = result.get("message") or result.get("status") or decision
        text = f"{msg} · by @{user} · `{pending_id}`"
    except KeyError:
        text = (
            f"Pending `{pending_id}` not found (demo cards / expired). "
            "Trigger a real pending via fuzzy-name, then Approve."
        )
        decision = "reject"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Slack HITL resolve failed: %s", exc)
        text = f"Error resolving `{pending_id}`: {exc}"
        decision = "reject"
    if response_url:
        slack_client.update_via_response_url(response_url, text=text, decision=decision)


@router.post("/slack/interact")
async def slack_interact(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_signature: Optional[str] = Header(default=None, alias="X-Slack-Signature"),
    x_slack_request_timestamp: Optional[str] = Header(
        default=None, alias="X-Slack-Request-Timestamp"
    ),
) -> Response:
    """
    Slack Block Kit interactivity — Approve / Reject buttons.
    Ack within 3s (Slack requirement), then resolve ledger in background.
    Configure Request URL: {PUBLIC_BASE_URL}/webhooks/slack/interact
    """
    body = await request.body()
    logger.info(
        "slack interact hit bytes=%s ts=%s sig=%s",
        len(body),
        bool(x_slack_request_timestamp),
        bool(x_slack_signature),
    )
    if not slack_client.verify_signature(
        body=body,
        timestamp=x_slack_request_timestamp or "",
        signature=x_slack_signature or "",
    ):
        logger.warning("slack interact signature failed")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = parse_qs(body.decode("utf-8"))
    raw = (form.get("payload") or [""])[0]
    if not raw:
        # Some Slack URL checks POST without payload — ack so Save succeeds
        return Response(status_code=200)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Bad payload JSON: {exc}") from exc

    if payload.get("type") == "url_verification":
        return Response(
            content=json.dumps({"challenge": payload.get("challenge")}),
            media_type="application/json",
        )

    parsed = slack_client.parse_interaction(payload)
    if not parsed:
        logger.info("slack interact ignored type=%s", payload.get("type"))
        return Response(status_code=200)

    background_tasks.add_task(_process_slack_decision, parsed)
    return Response(status_code=200)
