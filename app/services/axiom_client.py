from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings
from app.models import NormalizedEvent

logger = logging.getLogger(__name__)


def configured() -> bool:
    settings = get_settings()
    return bool(settings.axiom_token and settings.axiom_dataset)


def _ingest_url() -> str:
    settings = get_settings()
    edge = settings.axiom_edge.strip() or "api.axiom.co"
    edge = edge.replace("https://", "").replace("http://", "")
    return f"https://{edge}/v1/ingest/{settings.axiom_dataset}"


def _query_url() -> str:
    settings = get_settings()
    # Query API lives on api.axiom.co (not the edge ingest host)
    return "https://api.axiom.co/v1/datasets/_apl?format=tabular"


def _headers() -> Dict[str, str]:
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.axiom_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if settings.axiom_org_id:
        headers["X-Axiom-Org-Id"] = settings.axiom_org_id
    return headers


def _flatten_triad(extra: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Promote nested triad keys to flat queryable fields."""
    if not extra:
        return {}
    out = dict(extra)
    triad = out.pop("triad", None)
    if isinstance(triad, dict):
        out.setdefault("same_entity", triad.get("same_entity"))
        out.setdefault("already_happened", triad.get("already_happened"))
        out.setdefault("who_acts", triad.get("who_acts"))
        out.setdefault("confidence", triad.get("confidence"))
        # Keep nested copy for dashboards that expect it
        out["triad"] = triad
    return out


def _post_events(events: List[dict[str, Any]], *, retries: int = 1) -> bool:
    settings = get_settings()
    if not settings.axiom_token:
        logger.debug("Axiom ingest skipped — AXIOM_TOKEN not set")
        return False
    if not events:
        return True

    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(_ingest_url(), headers=_headers(), json=events)
                resp.raise_for_status()
            return True
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("Axiom ingest attempt %s failed: %s", attempt + 1, exc)
            if attempt < retries:
                time.sleep(0.35 * (attempt + 1))
    if last_exc:
        raise last_exc
    return False


def ingest_event(
    *,
    event: NormalizedEvent,
    status: str,
    idempotency_key: str,
    message: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> bool:
    """
    Ingest one pipeline / HITL outcome into Axiom with flattened triad fields.
    Uses the event timestamp for `_time` when available (better monthly queries).
    """
    flat_extra = _flatten_triad(extra)
    event_ts = event.timestamp
    if event_ts.tzinfo is None:
        event_ts = event_ts.replace(tzinfo=timezone.utc)

    payload = [
        {
            "_time": event_ts.astimezone(timezone.utc).isoformat(),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "service": "ledger-twin",
            "kind": "pipeline_outcome",
            "status": status,
            "source": event.source,
            "type": event.type,
            "external_id": event.external_id,
            "idempotency_key": idempotency_key,
            "amount_cents": event.amount_cents,
            "currency": event.currency,
            "event_day": event.event_day(),
            "name_hints": event.name_hints,
            "email_hints": event.email_hints,
            "message": message,
            **{k: v for k, v in flat_extra.items() if v is not None and v != ""},
        }
    ]
    return _post_events(payload)


def ingest_raw(
    *,
    kind: str,
    status: str,
    message: str = "",
    fields: Optional[dict[str, Any]] = None,
) -> bool:
    """Lifecycle / ops events (polls, cron, report sends, webhook ack)."""
    body = {
        "_time": datetime.now(timezone.utc).isoformat(),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "service": "ledger-twin",
        "kind": kind,
        "status": status,
        "message": message,
        **(fields or {}),
    }
    return _post_events([body])


def query_month(
    *,
    year: int,
    month: int,
    limit: int = 5000,
) -> List[dict[str, Any]]:
    """
    Query Axiom APL for all ledger-twin events in a calendar month (UTC).
    Returns [] if not configured or query fails (caller should fall back to Airtable).
    """
    settings = get_settings()
    if not settings.axiom_token:
        return []

    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    dataset = settings.axiom_dataset
    apl = (
        f"['{dataset}'] "
        f"| where _time >= datetime('{start.isoformat()}') "
        f"and _time < datetime('{end.isoformat()}') "
        f"| where service == 'ledger-twin' "
        f"| order by _time desc "
        f"| limit {int(limit)}"
    )
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                _query_url(),
                headers=_headers(),
                json={"apl": apl, "startTime": start.isoformat(), "endTime": end.isoformat()},
            )
            if resp.status_code >= 400:
                logger.warning("Axiom query failed %s: %s", resp.status_code, resp.text[:400])
                return []
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Axiom query error: %s", exc)
        return []

    # Tabular format: columns + tables[0].data rows
    tables = data.get("tables") or data.get("matches") or []
    if not tables:
        # Some responses are {status, matches: [...]}
        if isinstance(data.get("matches"), list):
            return list(data["matches"])
        return []

    table0 = tables[0] if isinstance(tables[0], dict) else {}
    columns = [c.get("name") if isinstance(c, dict) else str(c) for c in (table0.get("columns") or [])]
    rows = table0.get("data") or table0.get("rows") or []
    out: List[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
        elif isinstance(row, list) and columns:
            out.append({columns[i]: row[i] for i in range(min(len(columns), len(row)))})
    return out
