from __future__ import annotations

from fastapi import APIRouter

from app import idempotency, pending_actions
from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "ok": True,
        "service": "ledger-twin",
        "env": settings.app_env,
        "llm_provider": settings.llm_provider,
        "stripe_webhook_configured": bool(settings.stripe_webhook_secret),
        "airtable_configured": bool(settings.airtable_api_key and settings.airtable_base_id),
        "axiom_configured": bool(settings.axiom_token and settings.axiom_dataset),
        "temp_mail_configured": bool(
            settings.temp_mail_address
            and (settings.temp_mail_token or settings.temp_mail_password)
        ),
        "temp_mail_address": settings.temp_mail_address or None,
        "slack_configured": bool(
            settings.slack_bot_token
            and settings.slack_signing_secret
            and settings.slack_channel_id
        ),
        "slack_channel_id": settings.slack_channel_id or None,
        "slack_socket_mode": bool(settings.slack_app_token),
        "idempotency": {
            "claimed": idempotency.claimed_count(),
            "blocked_duplicates": idempotency.blocked_count(),
        },
        "pending_actions": len(pending_actions.list_pending()),
    }
