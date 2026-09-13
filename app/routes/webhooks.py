from __future__ import annotations

from typing import Any, Optional

import stripe
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import get_settings
from app.pipeline import process_stripe_payload

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
