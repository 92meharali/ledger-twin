from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app import idempotency, pending_actions
from app.eval_store import latest_eval
from app.services import airtable_client, axiom_client

logger = logging.getLogger(__name__)


def list_recent_events(limit: int = 40) -> List[Dict[str, Any]]:
    try:
        rows = airtable_client.event_log_table().all(max_records=limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("EventLog fetch failed: %s", exc)
        return []
    out = []
    for r in rows:
        f = r.get("fields") or {}
        out.append(
            {
                "id": r.get("id"),
                "name": f.get("Name"),
                "status": f.get("Status"),
                "source": f.get("Source"),
                "type": f.get("Type"),
                "external_id": f.get("ExternalId"),
                "amount_cents": f.get("AmountCents"),
                "message": f.get("Message"),
                "timestamp": f.get("Timestamp"),
                "triad": {
                    "same_entity": f.get("SameEntity"),
                    "already_happened": f.get("AlreadyHappened"),
                    "who_acts": f.get("WhoActs"),
                    "confidence": f.get("Confidence"),
                },
            }
        )
    out.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return out[:limit]


def build_scorecard() -> Dict[str, Any]:
    events = list_recent_events(100)
    statuses = [str(e.get("status") or "") for e in events]
    total = len(statuses) or 1

    blocked = sum(1 for s in statuses if s == "blocked_duplicate")
    auto_closed = sum(1 for s in statuses if s == "auto_closed")
    pending = sum(1 for s in statuses if s.startswith("pending"))
    processed = sum(1 for s in statuses if s != "ignored")

    claimed = idempotency.claimed_count()
    blocked_local = idempotency.blocked_count()
    dup_denom = max(1, claimed + blocked_local)
    duplicate_catch_rate = round(blocked_local / dup_denom, 3)

    # Entity accuracy proxy: events where SameEntity is yes/no and status isn't error
    entity_labeled = [
        e
        for e in events
        if (e.get("triad") or {}).get("same_entity") in {"yes", "no", "new", "uncertain"}
    ]
    # Treat auto_closed + pending_entity(with yes) as consistent resolutions for demo scorecard
    good_entity = 0
    for e in entity_labeled:
        se = (e.get("triad") or {}).get("same_entity")
        st = e.get("status")
        if st == "auto_closed" and se == "yes":
            good_entity += 1
        elif st == "pending_entity" and se in {"yes", "uncertain", "new", "no"}:
            good_entity += 1  # escalated correctly rather than silent merge
        elif st == "blocked_duplicate":
            good_entity += 1
        elif st == "pending_partial" and se == "yes":
            good_entity += 1
    entity_resolution_accuracy = round(
        good_entity / max(1, len(entity_labeled)), 3
    )

    escalation_rate = round(pending / max(1, processed), 3)
    false_merge_rate = 0.0  # tracked via eval failures when present
    eval_row = latest_eval()
    silent_wrong = 0
    eval_pass = 0
    eval_total = 0
    if eval_row:
        eval_pass = eval_row["pass_count"]
        eval_total = eval_row["total"]
        for r in eval_row.get("results") or []:
            if not r.get("pass") and r.get("category") == "silent_wrong":
                silent_wrong += 1
        # if eval has false_merge case failures, reflect
        fail_merge = sum(
            1
            for r in (eval_row.get("results") or [])
            if (not r.get("pass")) and r.get("id") == "fuzzy_no_silent_merge"
        )
        false_merge_rate = round(fail_merge / max(1, eval_total), 3)

    pending_open = pending_actions.list_pending()

    axiom_ok = bool(
        get_settings_safe_axiom()
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entity_resolution_accuracy": entity_resolution_accuracy,
        "duplicate_catch_rate": duplicate_catch_rate,
        "false_merge_rate": false_merge_rate,
        "escalation_rate": escalation_rate,
        "silent_wrong_completions": silent_wrong,
        "eval_pass_count": eval_pass,
        "eval_total": eval_total,
        "counts": {
            "eventlog_rows": len(events),
            "auto_closed": auto_closed,
            "pending": pending,
            "blocked_duplicate": blocked,
            "idempotency_claimed": claimed,
            "idempotency_blocked": blocked_local,
            "pending_actions_open": len(pending_open),
        },
        "axiom_configured": axiom_ok,
        "latest_eval": eval_row,
        "recent_events": events[:25],
        "pending_actions": pending_open[:10],
    }


def get_settings_safe_axiom() -> bool:
    from app.config import get_settings

    s = get_settings()
    return bool(s.axiom_token and s.axiom_dataset)
