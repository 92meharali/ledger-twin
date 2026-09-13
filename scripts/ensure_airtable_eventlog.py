#!/usr/bin/env python3
"""Ensure Airtable EventLog table exists with expected fields."""
from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ["AIRTABLE_BASE_ID"]
TOKEN = os.environ["AIRTABLE_API_KEY"]
TABLE = os.environ.get("AIRTABLE_TABLE_EVENT_LOG", "EventLog")
META = f"https://api.airtable.com/v0/meta/bases/{BASE}/tables"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

FIELDS = [
    {"name": "Status", "type": "singleLineText"},
    {"name": "Source", "type": "singleLineText"},
    {"name": "Type", "type": "singleLineText"},
    {"name": "ExternalId", "type": "singleLineText"},
    {"name": "IdempotencyKey", "type": "singleLineText"},
    {"name": "AmountCents", "type": "number", "options": {"precision": 0}},
    {"name": "Currency", "type": "singleLineText"},
    {"name": "EventDay", "type": "singleLineText"},
    {"name": "NameHints", "type": "singleLineText"},
    {"name": "EmailHints", "type": "singleLineText"},
    {"name": "Message", "type": "multilineText"},
    {"name": "Timestamp", "type": "singleLineText"},
    {"name": "RawJson", "type": "multilineText"},
    {"name": "SameEntity", "type": "singleLineText"},
    {"name": "AlreadyHappened", "type": "singleLineText"},
    {"name": "WhoActs", "type": "singleLineText"},
    {"name": "Confidence", "type": "number", "options": {"precision": 2}},
]


def main() -> int:
    with httpx.Client(timeout=30.0) as client:
        listed = client.get(META, headers=HEADERS)
        if listed.status_code != 200:
            print("LIST FAILED", listed.status_code, listed.text)
            print("Token may need scope: schema.bases:read (and write to create).")
            return 1
        tables = listed.json().get("tables", [])
        existing = next((t for t in tables if t.get("name") == TABLE), None)
        if existing:
            print(f"Table '{TABLE}' already exists id={existing.get('id')}")
            return 0

        # First field becomes primary — use Status as first? Airtable requires primary to be
        # singleLineText / etc. Put Name-like primary first.
        body = {
            "name": TABLE,
            "description": "Ledger Twin event / reliability log",
            "fields": [{"name": "Name", "type": "singleLineText"}, *FIELDS],
        }
        created = client.post(META, headers=HEADERS, json=body)
        if created.status_code not in (200, 201):
            print("CREATE FAILED", created.status_code, created.text)
            return 1
        print("Created table", created.json().get("id"), TABLE)
        return 0


if __name__ == "__main__":
    sys.exit(main())
