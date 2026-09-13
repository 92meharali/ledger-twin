from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, List

from app.demo_catalog import by_key, stripe_event
from app.eval_store import save_eval_run
from app.pipeline import process_stripe_payload
from app.routes.demo import _ensure_client, _ensure_named_open_invoice, _ensure_open_invoice_1000
from app.services import email_ingest, hitl, scorecard
from app.services.airtable_client import list_open_invoices


def _fresh_event(prefix: str, amount: int, client_key: str, *, fuzzy: bool = False) -> dict:
    client = by_key(client_key)
    suffix = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    return stripe_event(
        evt_id=f"evt_{prefix}_{suffix}",
        pi_id=f"pi_{prefix}_{suffix}",
        amount_cents=amount,
        client=client,
        name_override=client["fuzzy_name"] if fuzzy else None,
    )


def run_eval_suite() -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []

    def case(cid: str, name: str, category: str, fn: Callable[[], None]) -> None:
        try:
            fn()
            results.append({"id": cid, "name": name, "category": category, "pass": True, "detail": "ok"})
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "id": cid,
                    "name": name,
                    "category": category,
                    "pass": False,
                    "detail": str(exc),
                }
            )

    def t_clean() -> None:
        _ensure_open_invoice_1000()
        r = process_stripe_payload(_fresh_event("eval_clean", 100000, "cursor"))
        assert r.status == "auto_closed", f"expected auto_closed got {r.status}"

    case("clean_exact", "Clean Cursor payment auto-closes", "happy", t_clean)

    def t_dup() -> None:
        cursor = by_key("cursor")
        client = _ensure_client(cursor)
        opens = list_open_invoices(client["id"])
        if not any(i["remaining_cents"] == 2000 for i in opens):
            _ensure_named_open_invoice(
                client=client,
                invoice_name=f"INV-EVAL-20-{uuid.uuid4().hex[:6]}",
                amount_cents=2000,
            )
        payload = _fresh_event("eval_dup", 2000, "cursor")
        first = process_stripe_payload(payload)
        second = process_stripe_payload(payload)
        assert first.status in {"auto_closed", "pending_partial", "pending_entity", "pending_no_invoice"}
        assert second.status == "blocked_duplicate", f"expected blocked_duplicate got {second.status}"

    case("duplicate_block", "Duplicate webhook blocked", "reliability", t_dup)

    pending_id_holder: Dict[str, str] = {}

    def t_fuzzy() -> None:
        _ensure_open_invoice_1000()
        r = process_stripe_payload(_fresh_event("eval_fuzzy", 100000, "cursor", fuzzy=True))
        assert r.status == "pending_entity", f"expected pending_entity got {r.status}"
        assert r.pending_action_id, "missing pending_action_id"
        pending_id_holder["id"] = r.pending_action_id

    case("fuzzy_escalate", "Fuzzy 'Curser' escalates (no silent merge)", "reliability", t_fuzzy)

    def t_no_silent() -> None:
        assert pending_id_holder.get("id"), "fuzzy case did not produce pending id"

    case(
        "fuzzy_no_silent_merge",
        "Fuzzy path did not auto-close",
        "silent_wrong",
        t_no_silent,
    )

    def t_partial() -> None:
        slack = by_key("slack")
        client = _ensure_client(slack)
        _ensure_named_open_invoice(client=client, invoice_name=slack["invoice_1000"], amount_cents=100000)
        r = process_stripe_payload(_fresh_event("eval_partial", 80000, "slack"))
        assert r.status == "pending_partial", f"expected pending_partial got {r.status}"

    case("partial_amount", "Partial Slack amount not fully paid", "reliability", t_partial)

    def t_approve() -> None:
        pid = pending_id_holder.get("id")
        assert pid, "no pending from fuzzy"
        out = hitl.resolve_pending(pid, "approve")
        assert out["status"] == "approved", out

    case("hitl_approve", "HITL approve mutates ledger", "hitl", t_approve)

    def t_mail() -> None:
        _ensure_open_invoice_1000()
        out = email_ingest.ingest_tempmail_message(
            {
                "id": f"eval_mail_{uuid.uuid4().hex[:8]}",
                "subject": "Payment received — Cursor",
                "text": "paid via e-transfer $1000\nClient: Cursor\nhttps://cursor.com",
                "from": {"name": "Ops", "address": "ops@cursor.com"},
            }
        )
        assert out.get("status") in {"auto_closed", "pending_partial", "pending_entity"}, out

    case("temp_mail_ingest", "Temp-mail payment signal ingests", "integrations", t_mail)

    def t_scorecard() -> None:
        sc = scorecard.build_scorecard()
        for key in (
            "entity_resolution_accuracy",
            "duplicate_catch_rate",
            "escalation_rate",
            "eval_pass_count",
            "recent_events",
        ):
            assert key in sc, f"missing {key}"

    case("scorecard_smoke", "Scorecard payload has required keys", "demo", t_scorecard)

    run_id = f"eval_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    saved = save_eval_run(run_id, results)
    return saved
