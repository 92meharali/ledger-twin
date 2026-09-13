"""Monthly report + cron routes."""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services import mail_outbound, monthly_report

router = APIRouter(tags=["reports"])


def _authorize(authorization: Optional[str], cron_secret: Optional[str]) -> None:
    settings = get_settings()
    expected = (settings.cron_secret or "").strip()
    if not expected:
        # Allow in demo when no secret is set (local / first deploy)
        if settings.demo_mode:
            return
        raise HTTPException(status_code=503, detail="CRON_SECRET not configured")

    provided = ""
    if cron_secret:
        provided = cron_secret.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()

    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized cron/report request")


class MonthlySendBody(BaseModel):
    year: Optional[int] = Field(default=None, ge=2000, le=2100)
    month: Optional[int] = Field(default=None, ge=1, le=12)
    force: bool = True


@router.get("/reports/monthly")
def preview_monthly(
    year: Optional[int] = Query(default=None),
    month: Optional[int] = Query(default=None),
) -> dict:
    """Preview previous (or explicit) month record without sending email."""
    record = monthly_report.build_monthly_record(year=year, month=month)
    subject, text, html = monthly_report.render_monthly_email(record)
    return {
        "ok": True,
        "recipient": record["recipient"],
        "subject": subject,
        "summary": record["summary"],
        "event_count": len(record["events"]),
        "temp_mail_payments": len(record["temp_mail_payments"]),
        "preview_text": text[:4000],
        "html_bytes": len(html),
    }


@router.post("/reports/monthly/send")
def send_monthly(
    body: MonthlySendBody,
    authorization: Optional[str] = Header(default=None),
    x_cron_secret: Optional[str] = Header(default=None, alias="X-Cron-Secret"),
) -> dict:
    """Manually send a monthly record email (protected by CRON_SECRET unless DEMO_MODE)."""
    _authorize(authorization, x_cron_secret)
    return monthly_report.send_monthly_report(
        year=body.year,
        month=body.month,
        force=body.force,
    )


@router.post("/cron/monthly-report")
def cron_monthly_report(
    authorization: Optional[str] = Header(default=None),
    x_vercel_cron: Optional[str] = Header(default=None, alias="x-vercel-cron"),
    x_cron_secret: Optional[str] = Header(default=None, alias="X-Cron-Secret"),
    force: bool = Query(default=False),
) -> dict:
    """
    Vercel Cron hits this daily at 08:00 UTC.
    Email is only sent when today is the 1st (previous complete month), unless force=true.
    """
    settings = get_settings()
    # Vercel Cron sends Authorization: Bearer <CRON_SECRET> when configured,
    # or the x-vercel-cron header on platform invocations.
    if x_vercel_cron:
        # Platform cron — still require secret if set
        if settings.cron_secret:
            _authorize(authorization, x_cron_secret)
    else:
        _authorize(authorization, x_cron_secret)

    return monthly_report.send_monthly_report(force=force)


@router.get("/reports/outbox")
def demo_outbox() -> dict:
    """Demo-mode outbox of emails that would have been sent."""
    if not get_settings().demo_mode:
        raise HTTPException(status_code=403, detail="DEMO_MODE is off")
    return {"outbox": mail_outbound.demo_outbox()}
