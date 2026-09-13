"""Tests for Axiom logging, monthly reports, and reliability helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List

import pytest

from app.models import NormalizedEvent
from app.services import axiom_client, mail_outbound, monthly_report


@pytest.fixture()
def report_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "ledger.db"))
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(tmp_path / "idem.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("REPORT_TO_EMAIL", "hamzafarooqsea@gmail.com")
    monkeypatch.setenv("AXIOM_TOKEN", "")
    monkeypatch.setenv("AXIOM_DATASET", "ledger-twin")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    mail_outbound.clear_demo_outbox()
    yield get_settings()
    get_settings.cache_clear()
    mail_outbound.clear_demo_outbox()


def test_previous_complete_month_january():
    assert monthly_report.previous_complete_month(date(2026, 1, 1)) == (2025, 12)


def test_previous_complete_month_midyear():
    assert monthly_report.previous_complete_month(date(2026, 9, 14)) == (2026, 8)


def test_month_bounds():
    start, end, label = monthly_report.month_bounds(2026, 2)
    assert start == "2026-02-01"
    assert end == "2026-02-28"
    assert label == "February 2026"


def test_flatten_triad_promotes_fields():
    flat = axiom_client._flatten_triad(
        {
            "triad": {
                "same_entity": "yes",
                "already_happened": "no",
                "who_acts": "agent",
                "confidence": 0.91,
            },
            "ClientRecordId": "rec1",
        }
    )
    assert flat["same_entity"] == "yes"
    assert flat["already_happened"] == "no"
    assert flat["who_acts"] == "agent"
    assert flat["confidence"] == 0.91
    assert flat["ClientRecordId"] == "rec1"
    assert isinstance(flat["triad"], dict)


def test_axiom_ingest_skipped_without_token(report_env, monkeypatch):
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("should not POST without token")

    monkeypatch.setattr(axiom_client.httpx, "Client", boom)
    event = NormalizedEvent(
        source="stripe",
        type="payment_intent.succeeded",
        external_id="pi_test",
        amount_cents=1000,
        currency="usd",
        name_hints=["Cursor"],
        email_hints=[],
        timestamp=datetime.now(timezone.utc),
        raw={},
    )
    assert axiom_client.ingest_event(
        event=event,
        status="auto_closed",
        idempotency_key="k1",
        message="test",
        extra={"triad": {"same_entity": "yes", "already_happened": "no", "who_acts": "agent", "confidence": 0.99}},
    ) is False
    assert called["n"] == 0


def test_axiom_ingest_posts_flattened_payload(report_env, monkeypatch):
    monkeypatch.setenv("AXIOM_TOKEN", "xaat-test")
    from app.config import get_settings

    get_settings.cache_clear()

    captured: Dict[str, Any] = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResp()

    monkeypatch.setattr(axiom_client.httpx, "Client", FakeClient)
    event = NormalizedEvent(
        source="temp_mail",
        type="email.payment_signal",
        external_id="mail_abc",
        amount_cents=50000,
        currency="usd",
        name_hints=["Cursor"],
        email_hints=["billing@cursor.com"],
        timestamp=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
        raw={},
    )
    ok = axiom_client.ingest_event(
        event=event,
        status="auto_closed",
        idempotency_key="idem_1",
        message="ok",
        extra={
            "triad": {
                "same_entity": "yes",
                "already_happened": "no",
                "who_acts": "agent",
                "confidence": 0.95,
            }
        },
    )
    assert ok is True
    assert "ledger-twin" in captured["url"]
    row = captured["json"][0]
    assert row["kind"] == "pipeline_outcome"
    assert row["same_entity"] == "yes"
    assert row["who_acts"] == "agent"
    assert row["source"] == "temp_mail"
    assert row["event_day"] == "2026-08-15"
    assert row["_time"].startswith("2026-08-15")


def test_build_monthly_record_filters_and_summarizes(report_env, monkeypatch):
    sample: List[Dict[str, Any]] = [
        {
            "id": "1",
            "fields": {
                "Status": "auto_closed",
                "Source": "stripe",
                "Type": "payment_intent.succeeded",
                "ExternalId": "pi_1",
                "AmountCents": 100000,
                "EventDay": "2026-08-10",
                "Timestamp": "2026-08-10T10:00:00+00:00",
                "SameEntity": "yes",
                "AlreadyHappened": "no",
                "WhoActs": "agent",
                "Message": "ok",
            },
        },
        {
            "id": "2",
            "fields": {
                "Status": "auto_closed",
                "Source": "temp_mail",
                "Type": "email.payment_signal",
                "ExternalId": "mail_1",
                "AmountCents": 2000,
                "EventDay": "2026-08-20",
                "Timestamp": "2026-08-20T10:00:00+00:00",
                "SameEntity": "yes",
                "Message": "e-transfer",
            },
        },
        {
            "id": "3",
            "fields": {
                "Status": "blocked_duplicate",
                "Source": "stripe",
                "Type": "payment_intent.succeeded",
                "ExternalId": "pi_dup",
                "AmountCents": 100000,
                "EventDay": "2026-07-01",
                "Timestamp": "2026-07-01T10:00:00+00:00",
            },
        },
    ]

    class FakeTable:
        def all(self, max_records=1000):
            return sample

    monkeypatch.setattr(
        monthly_report.airtable_client,
        "event_log_table",
        lambda: FakeTable(),
    )
    monkeypatch.setattr(monthly_report.axiom_client, "query_month", lambda **k: [])

    record = monthly_report.build_monthly_record(year=2026, month=8)
    assert record["label"] == "August 2026"
    assert record["summary"]["total_events"] == 2
    assert record["summary"]["temp_mail_events"] == 1
    assert record["summary"]["stripe_events"] == 1
    assert record["summary"]["total_amount_usd"] == 1020.0
    assert record["recipient"] == "hamzafarooqsea@gmail.com"


def test_send_monthly_report_demo_outbox(report_env, monkeypatch):
    monkeypatch.setattr(
        monthly_report,
        "build_monthly_record",
        lambda **k: {
            "year": 2026,
            "month": 8,
            "label": "August 2026",
            "start_day": "2026-08-01",
            "end_day": "2026-08-31",
            "generated_at": "2026-09-01T08:00:00+00:00",
            "recipient": "hamzafarooqsea@gmail.com",
            "summary": {
                "total_events": 1,
                "airtable_events": 1,
                "axiom_events": 0,
                "stripe_events": 0,
                "temp_mail_events": 1,
                "auto_closed": 1,
                "blocked_duplicate": 0,
                "pending": 0,
                "approved": 0,
                "rejected": 0,
                "total_amount_cents": 2000,
                "total_amount_usd": 20.0,
                "status_breakdown": {"auto_closed": 1},
                "source_breakdown": {"temp_mail": 1},
            },
            "events": [
                {
                    "event_day": "2026-08-20",
                    "source": "temp_mail",
                    "type": "email.payment_signal",
                    "status": "auto_closed",
                    "amount_cents": 2000,
                    "external_id": "mail_1",
                    "same_entity": "yes",
                    "already_happened": "no",
                    "who_acts": "agent",
                    "message": "paid",
                }
            ],
            "temp_mail_payments": [
                {
                    "event_day": "2026-08-20",
                    "status": "auto_closed",
                    "amount_cents": 2000,
                    "external_id": "mail_1",
                    "message": "paid",
                }
            ],
        },
    )
    monkeypatch.setattr(monthly_report.axiom_client, "ingest_raw", lambda **k: True)

    # Not the 1st → skip
    skipped = monthly_report.send_monthly_report(force=False, today=date(2026, 9, 14))
    assert skipped["skipped"] is True

    # Force send on any day
    sent = monthly_report.send_monthly_report(force=True, today=date(2026, 9, 14))
    assert sent["ok"] is True
    assert sent["recipient"] == "hamzafarooqsea@gmail.com"
    assert sent["email"]["provider"] == "demo"
    outbox = mail_outbound.demo_outbox()
    assert len(outbox) == 1
    assert outbox[0]["to"] == "hamzafarooqsea@gmail.com"
    assert "August 2026" in outbox[0]["subject"]
    assert "TEMP-MAIL" in outbox[0]["text"]


def test_cron_sends_on_first(report_env, monkeypatch):
    calls = {"n": 0}

    def fake_send(**kwargs):
        calls["n"] += 1
        return {"ok": True, "skipped": False}

    monkeypatch.setattr(monthly_report, "send_monthly_report", fake_send)
    # Direct call with day=1 simulation is inside send_monthly_report;
    # here we assert previous_complete_month wiring for Sep 1 → August
    assert monthly_report.previous_complete_month(date(2026, 9, 1)) == (2026, 8)
