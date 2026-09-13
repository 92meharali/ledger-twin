"""Unit tests — no live Airtable/Stripe/Slack required."""

from __future__ import annotations

import hmac
import hashlib
import time
from pathlib import Path

import pytest

from app.demo_catalog import by_key, stripe_event, stripe_pi_object
from app.idempotency import try_claim
from app.models import NormalizedEvent
from app.normalize import normalize_stripe_event
from app.services.matcher import match_payment_to_invoice
from app.services.slack_client import parse_interaction, verify_signature
from datetime import datetime, timezone


@pytest.fixture()
def tmp_settings(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("SQLITE_PATH", str(db))
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "idem.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "test_signing_secret_123456789012")
    from app.config import get_settings
    from app import idempotency, pending_actions

    get_settings.cache_clear()
    settings = get_settings()
    idempotency.init_idempotency_db()
    pending_actions.init_pending_db()
    yield settings
    get_settings.cache_clear()


def test_demo_catalog_has_brand_links():
    for key in ("cursor", "slack", "anthropic", "stripe", "notion", "linear"):
        c = by_key(key)
        assert c["name"]
        assert c["website"].startswith("https://")
        assert c["email"]


def test_stripe_payload_includes_website_metadata():
    cursor = by_key("cursor")
    evt = stripe_event(evt_id="evt_1", pi_id="pi_1", amount_cents=100000, client=cursor)
    obj = evt["data"]["object"]
    assert obj["billing_details"]["name"] == "Cursor"
    assert obj["metadata"]["website"] == "https://cursor.com"
    assert "cursor.com" in obj["description"]


def test_normalize_stripe_reads_company_and_website_name_hints():
    payload = {
        "type": "payment_intent.succeeded",
        "id": "evt_x",
        "data": {
            "object": stripe_pi_object(
                pi_id="pi_x",
                amount_cents=5000,
                name="Cursr",
                email="a@b.com",
                website="https://cursor.com",
                company="Cursor",
            )
        },
    }
    event = normalize_stripe_event(payload)
    assert event.external_id == "pi_x"
    assert event.amount_cents == 5000
    assert "Cursr" in event.name_hints
    assert "Cursor" in event.name_hints


def test_idempotency_blocks_duplicate(tmp_settings):
    event = NormalizedEvent(
        source="stripe",
        type="payment_intent.succeeded",
        external_id="pi_dup_test",
        amount_cents=1000,
        currency="usd",
        name_hints=["Cursor"],
        email_hints=[],
        timestamp=datetime.now(timezone.utc),
        raw={},
    )
    ok1, key1 = try_claim(event)
    ok2, key2 = try_claim(event)
    assert ok1 is True
    assert ok2 is False
    assert key1 == key2


def test_matcher_requires_exact_amount_for_auto_close(tmp_settings, monkeypatch):
    from app.services import matcher as matcher_mod
    from app.services.entity_resolve import EntityResolution

    event = NormalizedEvent(
        source="stripe",
        type="payment_intent.succeeded",
        external_id="pi_amt",
        amount_cents=80000,
        currency="usd",
        name_hints=["Slack"],
        email_hints=[],
        timestamp=datetime.now(timezone.utc),
        raw={},
    )
    entity = EntityResolution(
        client={"id": "rec1", "name": "Slack"},
        score=100.0,
        band="auto",
        same_entity="yes",
        who_acts="agent",
        confidence=0.99,
        notes="exact",
    )

    monkeypatch.setattr(
        matcher_mod.airtable_client,
        "list_open_invoices",
        lambda _cid: [
            {
                "id": "inv1",
                "name": "INV-SLACK-1000",
                "remaining_cents": 100000,
                "amount_cents": 100000,
                "status": "open",
            }
        ],
    )
    monkeypatch.setattr(matcher_mod.airtable_client, "create_payment", lambda **kwargs: "pay1")
    monkeypatch.setattr(matcher_mod.airtable_client, "mark_invoice_partial", lambda *a, **k: None)

    result = match_payment_to_invoice(event, entity)
    assert result.action == "pending_partial"


def test_slack_signature_roundtrip(tmp_settings):
    body = b"payload=%7B%22type%22%3A%22block_actions%22%7D"
    ts = str(int(time.time()))
    secret = tmp_settings.slack_signing_secret
    base = f"v0:{ts}:{body.decode()}"
    sig = "v0=" + hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    assert verify_signature(body=body, timestamp=ts, signature=sig)
    assert not verify_signature(body=body, timestamp=ts, signature="v0=dead")


def test_parse_slack_interaction():
    parsed = parse_interaction(
        {
            "type": "block_actions",
            "actions": [{"action_id": "ledger_twin_approve", "value": "pid-1"}],
            "user": {"username": "judge"},
            "response_url": "https://hooks.slack.com/x",
        }
    )
    assert parsed["decision"] == "approve"
    assert parsed["pending_id"] == "pid-1"


def test_health_endpoint(tmp_settings):
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["service"] == "ledger-twin"
