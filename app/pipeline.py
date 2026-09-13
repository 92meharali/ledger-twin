from __future__ import annotations

import logging
from typing import Any, Optional

from app import idempotency, pending_actions
from app.models import NormalizedEvent, ProcessResult
from app.normalize import normalize_stripe_event
from app.services import airtable_client, axiom_client, slack_client
from app.services.entity_resolve import resolve_entity
from app.services.matcher import match_payment_to_invoice

logger = logging.getLogger(__name__)


def _log_sinks(
    *,
    event: NormalizedEvent,
    status: str,
    key: str,
    message: str,
    triad: dict,
    extra_fields: Optional[dict] = None,
) -> tuple:
    airtable_id = None
    axiom_ok = False
    try:
        airtable_id = airtable_client.write_event_log(
            event=event,
            status=status,
            idempotency_key=key,
            message=message,
            triad=triad,
            extra_fields=extra_fields or {},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Airtable write failed: %s", exc)
        message = f"{message}; airtable_error={exc}"
    try:
        axiom_ok = axiom_client.ingest_event(
            event=event,
            status=status,
            idempotency_key=key,
            message=message,
            extra={"triad": triad, **(extra_fields or {})},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Axiom ingest failed: %s", exc)
    return airtable_id, axiom_ok, message


def process_normalized_event(event: NormalizedEvent) -> ProcessResult:
    claimed, key = idempotency.try_claim(event)

    if not claimed:
        triad = {
            "same_entity": "n/a",
            "already_happened": "yes",
            "who_acts": "none",
            "confidence": 1.0,
        }
        message = "Duplicate blocked by Idempotency Guard"
        airtable_id, axiom_ok, message = _log_sinks(
            event=event, status="blocked_duplicate", key=key, message=message, triad=triad
        )
        return ProcessResult(
            status="blocked_duplicate",
            idempotency_key=key,
            event=event,
            message=message,
            airtable_record_id=airtable_id,
            axiom_ok=axiom_ok,
            triad=triad,
        )

    # --- Ticket 02: resolve + match ---
    entity = resolve_entity(event)
    match = match_payment_to_invoice(event, entity)

    triad = {
        "same_entity": entity.same_entity,
        "already_happened": "no",
        "who_acts": match.who_acts if match.action != "auto_closed" else "agent",
        "confidence": round(
            match.confidence if match.action == "auto_closed" else entity.confidence,
            3,
        ),
    }

    extra = {
        "ClientRecordId": (entity.client or {}).get("id"),
        "EntityScore": entity.score,
        "EntityBand": entity.band,
        "MatchAction": match.action,
        "InvoiceRecordId": (match.invoice or {}).get("id"),
        "PaymentRecordId": match.payment_id,
        "LLMAnswer": entity.llm_answer,
    }

    pending_id = None
    status = match.action
    message = f"{entity.notes} | {match.message}".strip(" |")

    if match.action != "auto_closed":
        pending_payload = {
            "event": event.model_dump(mode="json"),
            "entity": {
                "client": entity.client,
                "score": entity.score,
                "band": entity.band,
                "same_entity": entity.same_entity,
                "llm_answer": entity.llm_answer,
                "llm_reasoning": entity.llm_reasoning,
                "notes": entity.notes,
            },
            "match": {
                "action": match.action,
                "invoice": match.invoice,
                "delta_cents": match.delta_cents,
                "message": match.message,
            },
            "triad": triad,
        }
        pending_id = pending_actions.create_pending(
            external_id=event.external_id,
            reason=match.action,
            payload=pending_payload,
        )
        message = f"{message} | pending_action_id={pending_id}"
        slack_ok, slack_ts, slack_err = slack_client.post_approval_card(
            pending_id=pending_id,
            reason=match.action,
            payload=pending_payload,
        )
        if slack_ok:
            message = f"{message} | slack_ts={slack_ts}"
            extra["SlackTs"] = slack_ts
        elif slack_err and slack_err != "slack not configured":
            message = f"{message} | slack_error={slack_err}"
            logger.warning("Slack approval card failed: %s", slack_err)

    airtable_id, axiom_ok, message = _log_sinks(
        event=event,
        status=status,
        key=key,
        message=message,
        triad=triad,
        extra_fields={k: v for k, v in extra.items() if v is not None and v != ""},
    )

    return ProcessResult(
        status=status,
        idempotency_key=key,
        event=event,
        message=message,
        airtable_record_id=airtable_id,
        axiom_ok=axiom_ok,
        pending_action_id=pending_id,
        client_record_id=(entity.client or {}).get("id"),
        invoice_record_id=(match.invoice or {}).get("id"),
        payment_record_id=match.payment_id,
        entity_score=entity.score,
        triad=triad,
    )


def process_stripe_payload(payload: dict[str, Any]) -> ProcessResult:
    event = normalize_stripe_event(payload)
    return process_normalized_event(event)
