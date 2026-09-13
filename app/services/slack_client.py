from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api"


def configured() -> bool:
    s = get_settings()
    return bool(s.slack_bot_token and s.slack_channel_id and s.slack_signing_secret)


def verify_signature(*, body: bytes, timestamp: str, signature: str) -> bool:
    """Verify X-Slack-Signature (v0 HMAC-SHA256). Reject stale timestamps (>5 min)."""
    secret = get_settings().slack_signing_secret
    if not secret or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - ts) > 60 * 5:
        return False
    base = f"v0:{timestamp}:{body.decode('utf-8')}"
    digest = hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, signature)


def _auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {get_settings().slack_bot_token}",
        "Content-Type": "application/json; charset=utf-8",
    }


def _money(cents: Optional[int], currency: Optional[str]) -> str:
    if cents is None:
        return "n/a"
    cur = (currency or "usd").upper()
    return f"{cents / 100:.2f} {cur}"


def build_approval_blocks(
    *,
    pending_id: str,
    reason: str,
    triad: Dict[str, Any],
    event: Dict[str, Any],
    entity: Dict[str, Any],
    match: Dict[str, Any],
) -> list:
    client = (entity or {}).get("client") or {}
    invoice = (match or {}).get("invoice") or {}
    name = client.get("name") or (event.get("name_hints") or ["?"])[0]
    fields = [
        {"type": "mrkdwn", "text": f"*Reason*\n`{reason}`"},
        {"type": "mrkdwn", "text": f"*Amount*\n{_money(event.get('amount_cents'), event.get('currency'))}"},
        {"type": "mrkdwn", "text": f"*Same entity?*\n{triad.get('same_entity', '?')}"},
        {"type": "mrkdwn", "text": f"*Already happened?*\n{triad.get('already_happened', '?')}"},
        {"type": "mrkdwn", "text": f"*Who acts?*\n{triad.get('who_acts', '?')}"},
        {"type": "mrkdwn", "text": f"*Confidence*\n{triad.get('confidence', '?')}"},
        {"type": "mrkdwn", "text": f"*Client*\n{name}"},
        {
            "type": "mrkdwn",
            "text": f"*Invoice*\n{invoice.get('name') or invoice.get('id') or 'none'}",
        },
    ]
    website = client.get("website") or ""
    if website:
        fields.append({"type": "mrkdwn", "text": f"*Website*\n<{website}|{website}>"})
    notes = (entity or {}).get("notes") or (match or {}).get("message") or ""
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Ledger Twin — needs human approval", "emoji": True},
        },
        {"type": "section", "fields": fields[:10]},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Notes*\n{notes[:500] or '_none_'}\n`pending_id={pending_id}`",
            },
        },
        {
            "type": "actions",
            "block_id": f"hitl_{pending_id}",
            "elements": [
                {
                    "type": "button",
                    "action_id": "ledger_twin_approve",
                    "text": {"type": "plain_text", "text": "Approve", "emoji": True},
                    "style": "primary",
                    "value": pending_id,
                },
                {
                    "type": "button",
                    "action_id": "ledger_twin_reject",
                    "text": {"type": "plain_text", "text": "Reject", "emoji": True},
                    "style": "danger",
                    "value": pending_id,
                },
            ],
        },
    ]


def post_approval_card(
    *,
    pending_id: str,
    reason: str,
    payload: Dict[str, Any],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Post Block Kit Approve/Reject card to the configured channel.
    Returns (ok, message_ts, error_or_none).
    """
    settings = get_settings()
    if not (settings.slack_bot_token and settings.slack_channel_id):
        return False, None, "slack not configured"

    event = payload.get("event") or {}
    entity = payload.get("entity") or {}
    match = payload.get("match") or {}
    triad = payload.get("triad") or {}
    blocks = build_approval_blocks(
        pending_id=pending_id,
        reason=reason,
        triad=triad,
        event=event,
        entity=entity,
        match=match,
    )
    body = {
        "channel": settings.slack_channel_id,
        "text": f"Ledger Twin pending: {reason} ({pending_id})",
        "blocks": blocks,
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(f"{SLACK_API}/chat.postMessage", headers=_auth_headers(), json=body)
            data = resp.json()
        if not data.get("ok"):
            err = data.get("error") or resp.text
            logger.error("Slack chat.postMessage failed: %s", err)
            return False, None, str(err)
        return True, data.get("ts"), None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Slack post failed: %s", exc)
        return False, None, str(exc)


def update_via_response_url(response_url: str, *, text: str, decision: str) -> bool:
    """Replace the interactive message after Approve/Reject."""
    color_note = "approved ✅" if decision == "approve" else "rejected ❌"
    body = {
        "replace_original": True,
        "text": text,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Ledger Twin — {color_note}*\n{text}",
                },
            }
        ],
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(response_url, json=body)
        return resp.status_code < 300
    except Exception as exc:  # noqa: BLE001
        logger.exception("Slack response_url update failed: %s", exc)
        return False


def parse_interaction(payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Extract pending_id + decision from a Slack block_actions payload."""
    if payload.get("type") != "block_actions":
        return None
    actions = payload.get("actions") or []
    if not actions:
        return None
    action = actions[0]
    action_id = action.get("action_id") or ""
    pending_id = action.get("value") or ""
    if action_id == "ledger_twin_approve":
        decision = "approve"
    elif action_id == "ledger_twin_reject":
        decision = "reject"
    else:
        return None
    if not pending_id:
        return None
    return {
        "pending_id": pending_id,
        "decision": decision,
        "user": ((payload.get("user") or {}).get("username") or (payload.get("user") or {}).get("id") or ""),
        "response_url": payload.get("response_url") or "",
    }
