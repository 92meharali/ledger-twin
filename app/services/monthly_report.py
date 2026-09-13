"""
Monthly ledger record builder + email delivery.

On the 1st of every month (Vercel Cron → POST /cron/monthly-report), we:
  1. Aggregate the *previous* complete calendar month (Airtable EventLog + Axiom).
  2. Email the full month record to REPORT_TO_EMAIL (default: hamzafarooqsea@gmail.com).
  3. Log delivery success/failure to Axiom.
"""

from __future__ import annotations

import calendar
import logging
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config import get_settings
from app.services import airtable_client, axiom_client, mail_outbound

logger = logging.getLogger(__name__)


def previous_complete_month(today: Optional[date] = None) -> Tuple[int, int]:
    """Return (year, month) for the last fully completed calendar month."""
    today = today or datetime.now(timezone.utc).date()
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def month_bounds(year: int, month: int) -> Tuple[str, str, str]:
    """ISO start day, end day (inclusive), and human label."""
    last_day = calendar.monthrange(year, month)[1]
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year:04d}-{month:02d}-{last_day:02d}"
    label = f"{calendar.month_name[month]} {year}"
    return start, end, label


def _parse_day(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def _events_from_airtable(start_day: str, end_day: str) -> List[Dict[str, Any]]:
    try:
        rows = airtable_client.event_log_table().all(max_records=1000)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Airtable EventLog fetch for monthly report failed: %s", exc)
        return []

    out: List[Dict[str, Any]] = []
    for r in rows:
        f = r.get("fields") or {}
        day = _parse_day(f.get("EventDay") or f.get("Timestamp"))
        if not day or day < start_day or day > end_day:
            continue
        out.append(
            {
                "id": r.get("id"),
                "origin": "airtable",
                "status": f.get("Status"),
                "source": f.get("Source"),
                "type": f.get("Type"),
                "external_id": f.get("ExternalId"),
                "amount_cents": f.get("AmountCents"),
                "currency": f.get("Currency") or "usd",
                "event_day": day,
                "message": f.get("Message"),
                "timestamp": f.get("Timestamp"),
                "same_entity": f.get("SameEntity"),
                "already_happened": f.get("AlreadyHappened"),
                "who_acts": f.get("WhoActs"),
                "confidence": f.get("Confidence"),
            }
        )
    return out


def _events_from_axiom(year: int, month: int) -> List[Dict[str, Any]]:
    raw = axiom_client.query_month(year=year, month=month)
    out: List[Dict[str, Any]] = []
    for row in raw:
        day = _parse_day(row.get("event_day") or row.get("_time"))
        out.append(
            {
                "id": row.get("_rowId") or row.get("idempotency_key") or row.get("external_id"),
                "origin": "axiom",
                "status": row.get("status"),
                "source": row.get("source"),
                "type": row.get("type") or row.get("kind"),
                "external_id": row.get("external_id"),
                "amount_cents": row.get("amount_cents"),
                "currency": row.get("currency") or "usd",
                "event_day": day,
                "message": row.get("message"),
                "timestamp": row.get("_time") or row.get("ingested_at"),
                "same_entity": row.get("same_entity"),
                "already_happened": row.get("already_happened"),
                "who_acts": row.get("who_acts"),
                "confidence": row.get("confidence"),
                "kind": row.get("kind"),
            }
        )
    return out


def _merge_events(primary: List[Dict[str, Any]], secondary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prefer Airtable rows; fill gaps from Axiom by external_id+status+day."""
    seen = set()
    merged: List[Dict[str, Any]] = []
    for e in primary + secondary:
        key = (
            str(e.get("external_id") or ""),
            str(e.get("status") or ""),
            str(e.get("event_day") or ""),
            str(e.get("source") or ""),
        )
        if key in seen and key != ("", "", "", ""):
            continue
        seen.add(key)
        merged.append(e)
    merged.sort(key=lambda x: (x.get("event_day") or "", x.get("timestamp") or ""), reverse=True)
    return merged


def build_monthly_record(
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    if year is None or month is None:
        year, month = previous_complete_month(today)
    start_day, end_day, label = month_bounds(year, month)

    airtable_events = _events_from_airtable(start_day, end_day)
    axiom_events = _events_from_axiom(year, month)
    events = _merge_events(airtable_events, axiom_events)

    status_counts = Counter(str(e.get("status") or "unknown") for e in events)
    source_counts = Counter(str(e.get("source") or "unknown") for e in events)
    temp_mail_events = [e for e in events if str(e.get("source") or "") == "temp_mail"]
    stripe_events = [e for e in events if str(e.get("source") or "") == "stripe"]

    amounts = [int(e["amount_cents"]) for e in events if e.get("amount_cents") is not None]
    total_cents = sum(amounts)
    auto_closed = status_counts.get("auto_closed", 0)
    blocked = status_counts.get("blocked_duplicate", 0)
    pending = sum(v for k, v in status_counts.items() if k.startswith("pending"))
    approved = status_counts.get("approved", 0)
    rejected = status_counts.get("rejected", 0)

    return {
        "year": year,
        "month": month,
        "label": label,
        "start_day": start_day,
        "end_day": end_day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recipient": get_settings().report_to_email,
        "summary": {
            "total_events": len(events),
            "airtable_events": len(airtable_events),
            "axiom_events": len(axiom_events),
            "stripe_events": len(stripe_events),
            "temp_mail_events": len(temp_mail_events),
            "auto_closed": auto_closed,
            "blocked_duplicate": blocked,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "total_amount_cents": total_cents,
            "total_amount_usd": round(total_cents / 100.0, 2),
            "status_breakdown": dict(status_counts),
            "source_breakdown": dict(source_counts),
        },
        "events": events,
        "temp_mail_payments": temp_mail_events,
    }


def render_monthly_email(record: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return (subject, text_body, html_body)."""
    s = record["summary"]
    label = record["label"]
    subject = f"Ledger Twin — monthly record for {label}"

    lines = [
        f"Ledger Twin monthly record — {label}",
        f"Period: {record['start_day']} → {record['end_day']} (UTC)",
        f"Generated: {record['generated_at']}",
        "",
        "=== SUMMARY ===",
        f"Total events:          {s['total_events']}",
        f"From Airtable EventLog:{s['airtable_events']}",
        f"From Axiom:            {s['axiom_events']}",
        f"Stripe events:         {s['stripe_events']}",
        f"Temp-mail payments:    {s['temp_mail_events']}",
        f"Auto-closed:           {s['auto_closed']}",
        f"Duplicates blocked:    {s['blocked_duplicate']}",
        f"Pending escalations:   {s['pending']}",
        f"HITL approved:         {s['approved']}",
        f"HITL rejected:         {s['rejected']}",
        f"Total amount (USD):    ${s['total_amount_usd']:,.2f}",
        "",
        "Status breakdown:",
    ]
    for k, v in sorted(s["status_breakdown"].items()):
        lines.append(f"  - {k}: {v}")
    lines.append("")
    lines.append("Source breakdown:")
    for k, v in sorted(s["source_breakdown"].items()):
        lines.append(f"  - {k}: {v}")

    lines.extend(["", "=== TEMP-MAIL PAYMENT SIGNALS ==="])
    if not record["temp_mail_payments"]:
        lines.append("(none this month)")
    else:
        for e in record["temp_mail_payments"]:
            amt = e.get("amount_cents")
            usd = f"${amt / 100:.2f}" if amt is not None else "n/a"
            lines.append(
                f"- {e.get('event_day')} | {e.get('status')} | {usd} | {e.get('external_id')} | {e.get('message')}"
            )

    lines.extend(["", "=== FULL MONTH EVENT LOG ==="])
    if not record["events"]:
        lines.append("(no events recorded this month)")
    else:
        for e in record["events"]:
            amt = e.get("amount_cents")
            usd = f"${amt / 100:.2f}" if amt is not None else "n/a"
            lines.append(
                f"- {e.get('event_day')} | {e.get('source')}/{e.get('type')} | "
                f"{e.get('status')} | {usd} | {e.get('external_id')} | "
                f"same={e.get('same_entity')} happened={e.get('already_happened')} who={e.get('who_acts')}"
            )

    lines.extend(
        [
            "",
            "—",
            "Ledger Twin · https://ledger-twin.vercel.app",
            "Ops scorecard · https://ledger-twin.vercel.app/dashboard",
            "This email is sent automatically on the 1st of each month for the prior complete month.",
        ]
    )
    text = "\n".join(lines)

    def _amt_cell(e: Dict[str, Any]) -> str:
        cents = e.get("amount_cents")
        if cents is None:
            return "—"
        return f"${int(cents) / 100:.2f}"

    row_parts: List[str] = []
    for e in record["events"][:500]:
        row_parts.append(
            "<tr>"
            f"<td>{e.get('event_day') or ''}</td>"
            f"<td>{e.get('source') or ''}</td>"
            f"<td>{e.get('status') or ''}</td>"
            f"<td>{_amt_cell(e)}</td>"
            f"<td>{e.get('external_id') or ''}</td>"
            "</tr>"
        )
    rows_html = "".join(row_parts)
    html = f"""<!DOCTYPE html>
<html><body style="font-family:Segoe UI,Arial,sans-serif;color:#15202b">
  <h1>Ledger Twin — {label}</h1>
  <p>Period <strong>{record['start_day']}</strong> → <strong>{record['end_day']}</strong> (UTC)</p>
  <h2>Summary</h2>
  <ul>
    <li>Total events: <strong>{s['total_events']}</strong></li>
    <li>Temp-mail payments: <strong>{s['temp_mail_events']}</strong></li>
    <li>Stripe events: <strong>{s['stripe_events']}</strong></li>
    <li>Auto-closed: <strong>{s['auto_closed']}</strong></li>
    <li>Duplicates blocked: <strong>{s['blocked_duplicate']}</strong></li>
    <li>Total amount: <strong>${s['total_amount_usd']:,.2f}</strong></li>
  </ul>
  <h2>Full month event log</h2>
  <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px">
    <thead><tr><th>Day</th><th>Source</th><th>Status</th><th>Amount</th><th>External ID</th></tr></thead>
    <tbody>{rows_html or '<tr><td colspan="5">No events</td></tr>'}</tbody>
  </table>
  <p style="margin-top:24px">
    <a href="https://ledger-twin.vercel.app">App</a> ·
    <a href="https://ledger-twin.vercel.app/dashboard">Scorecard</a>
  </p>
</body></html>"""
    return subject, text, html


def send_monthly_report(
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    force: bool = False,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Build previous complete month (or explicit year/month) and email it.
    When called from daily cron, only sends if today.day == 1 unless force=True.
    """
    today = today or datetime.now(timezone.utc).date()
    if not force and today.day != 1:
        return {
            "ok": True,
            "skipped": True,
            "reason": f"Not the 1st of the month (today={today.isoformat()})",
        }

    record = build_monthly_record(year=year, month=month, today=today)
    subject, text, html = render_monthly_email(record)
    to_email = get_settings().report_to_email

    send_result = mail_outbound.send_email(
        to=to_email,
        subject=subject,
        text_body=text,
        html_body=html,
    )

    try:
        axiom_client.ingest_raw(
            kind="monthly_report",
            status="sent" if send_result.get("ok") else "send_failed",
            message=send_result.get("message") or subject,
            fields={
                "report_year": record["year"],
                "report_month": record["month"],
                "report_label": record["label"],
                "recipient": to_email,
                "event_count": record["summary"]["total_events"],
                "temp_mail_count": record["summary"]["temp_mail_events"],
                "provider": send_result.get("provider"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Axiom log for monthly report failed: %s", exc)

    return {
        "ok": bool(send_result.get("ok")),
        "skipped": False,
        "recipient": to_email,
        "report": {
            "year": record["year"],
            "month": record["month"],
            "label": record["label"],
            "summary": record["summary"],
        },
        "email": send_result,
        "preview_text": text[:2000],
    }
