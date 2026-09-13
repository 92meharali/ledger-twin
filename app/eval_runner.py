from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, List

from app.eval_store import save_eval_run
from app.pipeline import process_stripe_payload
from app.routes.demo import _ensure_open_invoice_1000
from app.services import email_ingest, hitl, scorecard
from app.services.airtable_client import list_open_invoices, list_clients


def _pi(prefix: str, amount: int, name: str, email: str) -> dict:
    suffix = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
    return {
        "type": "payment_intent.succeeded",
        "id": f"evt_{prefix}_{suffix}",
        "data": {
            "object": {
                "id": f"pi_{prefix}_{suffix}",
                "amount": amount,
                "currency": "usd",
                "billing_details": {"name": name, "email": email},
                "metadata": {},
            }
        },
    }


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

    # 1 clean exact
    def t_clean() -> None:
        _ensure_open_invoice_1000()
        r = process_stripe_payload(
            _pi("eval_clean", 100000, "Jose Martinez Studio", "jose@example.com")
        )
        assert r.status == "auto_closed", f"expected auto_closed got {r.status}"

    case("clean_exact", "Clean exact payment auto-closes", "happy", t_clean)

    # 2 duplicate
    def t_dup() -> None:
        payload = _pi("eval_dup", 2000, "Jose Martinez Studio", "jose@example.com")
        # ensure a $20 open invoice exists
        jose = next(c for c in list_clients() if c["name"] == "Jose Martinez Studio")
        opens = list_open_invoices(jose["id"])
        if not any(i["remaining_cents"] == 2000 for i in opens):
            from app.services import airtable_client

            airtable_client.invoices_table().create(
                {
                    "Name": f"INV-EVAL-20-{uuid.uuid4().hex[:6]}",
                    "ClientRecordId": jose["id"],
                    "ClientName": "Jose Martinez Studio",
                    "AmountCents": 2000,
                    "RemainingCents": 2000,
                    "Status": "open",
                    "Currency": "usd",
                }
            )
        first = process_stripe_payload(payload)
        second = process_stripe_payload(payload)
        assert first.status in {"auto_closed", "pending_partial", "pending_entity", "pending_no_invoice"}
        assert second.status == "blocked_duplicate", f"expected blocked_duplicate got {second.status}"

    case("duplicate_block", "Duplicate webhook blocked", "reliability", t_dup)

    # 3 fuzzy escalate
    pending_id_holder: Dict[str, str] = {}

    def t_fuzzy() -> None:
        r = process_stripe_payload(
            _pi("eval_fuzzy", 100000, "J. Martinez", "j.martinez@example.com")
        )
        assert r.status == "pending_entity", f"expected pending_entity got {r.status}"
        assert r.pending_action_id, "missing pending_action_id"
        pending_id_holder["id"] = r.pending_action_id

    case("fuzzy_escalate", "Fuzzy name escalates (no silent merge)", "reliability", t_fuzzy)

    # 4 fuzzy no silent merge (same as above category marker)
    def t_no_silent() -> None:
        assert pending_id_holder.get("id"), "fuzzy case did not produce pending id"

    case(
        "fuzzy_no_silent_merge",
        "Fuzzy path did not auto-close",
        "silent_wrong",
        t_no_silent,
    )

    # 5 partial
    def t_partial() -> None:
        _ensure_open_invoice_1000()
        r = process_stripe_payload(
            _pi("eval_partial", 80000, "Jose Martinez Studio", "jose@example.com")
        )
        assert r.status == "pending_partial", f"expected pending_partial got {r.status}"

    case("partial_amount", "Partial amount not fully paid", "reliability", t_partial)

    # 6 HITL approve (Slack substitute)
    def t_approve() -> None:
        pid = pending_id_holder.get("id")
        assert pid, "no pending from fuzzy"
        out = hitl.resolve_pending(pid, "approve")
        assert out["status"] == "approved", out

    case("hitl_approve", "Local HITL approve mutates ledger", "hitl", t_approve)

    # 7 temp mail plant
    def t_mail() -> None:
        _ensure_open_invoice_1000()
        out = email_ingest.ingest_tempmail_message(
            {
                "id": f"eval_mail_{uuid.uuid4().hex[:8]}",
                "subject": "Payment received",
                "text": "paid via e-transfer $1000\nClient: Jose Martinez Studio",
                "from": {"name": "Ops", "address": "ops@example.com"},
            }
        )
        assert out.get("status") in {"auto_closed", "pending_partial", "pending_entity"}, out

    case("temp_mail_ingest", "Temp-mail payment signal ingests", "integrations", t_mail)

    # 8 scorecard shape
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
