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
        "version": "0.8.0",
        "env": settings.app_env,
        "public_url": "https://ledger-twin.vercel.app",
        "llm_provider": settings.llm_provider,
        "stripe_webhook_configured": bool(settings.stripe_webhook_secret),
        "airtable_configured": bool(settings.airtable_api_key and settings.airtable_base_id),
        "axiom_configured": bool(settings.axiom_token and settings.axiom_dataset),
        "axiom_dataset": settings.axiom_dataset or None,
        "temp_mail_configured": bool(
            settings.temp_mail_address
            and (settings.temp_mail_token or settings.temp_mail_password)
        ),
        "temp_mail_address": settings.temp_mail_address or None,
        "monthly_report": {
            "to": settings.report_to_email,
            "resend_configured": bool(settings.resend_api_key),
            "smtp_configured": bool(settings.smtp_host and settings.smtp_user),
            "cron_protected": bool(settings.cron_secret),
            "schedule": "Daily 08:00 UTC; sends on the 1st for the previous complete month",
        },
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
