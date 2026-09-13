"""
Outbound email for monthly ledger reports.

Providers (first match wins):
  1. Resend  — RESEND_API_KEY
  2. SMTP    — SMTP_HOST + SMTP_USER + SMTP_PASSWORD
  3. Demo    — DEMO_MODE stores the message and returns ok (for tests / local)

Temp-mail (mail.tm) is inbound-only and cannot send; it feeds payment signals
into the agent. Monthly reports are delivered to REPORT_TO_EMAIL via this module.
"""

from __future__ import annotations

import logging
import smtplib
import uuid
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# In-memory outbox for DEMO_MODE / tests (last N messages)
_DEMO_OUTBOX: List[Dict[str, Any]] = []


def demo_outbox() -> List[Dict[str, Any]]:
    return list(_DEMO_OUTBOX)


def clear_demo_outbox() -> None:
    _DEMO_OUTBOX.clear()


def send_email(
    *,
    to: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
) -> Dict[str, Any]:
    settings = get_settings()
    to = (to or settings.report_to_email or "").strip()
    if not to:
        return {"ok": False, "provider": None, "message": "No REPORT_TO_EMAIL configured"}

    if settings.resend_api_key:
        return _send_resend(to=to, subject=subject, text_body=text_body, html_body=html_body)

    if settings.smtp_host and settings.smtp_user and settings.smtp_password:
        return _send_smtp(to=to, subject=subject, text_body=text_body, html_body=html_body)

    if settings.demo_mode:
        msg = {
            "id": f"demo_{uuid.uuid4().hex[:10]}",
            "to": to,
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
        _DEMO_OUTBOX.append(msg)
        if len(_DEMO_OUTBOX) > 20:
            del _DEMO_OUTBOX[:-20]
        logger.info("DEMO email queued to %s subject=%s", to, subject)
        return {
            "ok": True,
            "provider": "demo",
            "message": f"Demo mode — email recorded in outbox for {to}",
            "id": msg["id"],
        }

    return {
        "ok": False,
        "provider": None,
        "message": "No email provider configured (set RESEND_API_KEY or SMTP_*). DEMO_MODE also enables a local outbox.",
    }


def _send_resend(
    *,
    to: str,
    subject: str,
    text_body: str,
    html_body: Optional[str],
) -> Dict[str, Any]:
    settings = get_settings()
    from_addr = settings.report_from_email or "Ledger Twin <onboarding@resend.dev>"
    payload: Dict[str, Any] = {
        "from": from_addr,
        "to": [to],
        "subject": subject,
        "text": text_body,
    }
    if html_body:
        payload["html"] = html_body
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "provider": "resend",
                    "message": data.get("message") or resp.text[:300],
                    "status_code": resp.status_code,
                }
            return {
                "ok": True,
                "provider": "resend",
                "message": f"Sent via Resend to {to}",
                "id": data.get("id"),
            }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Resend send failed: %s", exc)
        return {"ok": False, "provider": "resend", "message": str(exc)}


def _send_smtp(
    *,
    to: str,
    subject: str,
    text_body: str,
    html_body: Optional[str],
) -> Dict[str, Any]:
    settings = get_settings()
    from_addr = settings.report_from_email or settings.smtp_user
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return {"ok": True, "provider": "smtp", "message": f"Sent via SMTP to {to}"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("SMTP send failed: %s", exc)
        return {"ok": False, "provider": "smtp", "message": str(exc)}
