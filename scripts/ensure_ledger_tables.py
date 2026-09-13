#!/usr/bin/env python3
"""Ensure Clients / Invoices / Payments tables exist and seed demo ledger rows."""
from __future__ import annotations

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ["AIRTABLE_BASE_ID"]
TOKEN = os.environ["AIRTABLE_API_KEY"]
META = f"https://api.airtable.com/v0/meta/bases/{BASE}/tables"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
DATA = f"https://api.airtable.com/v0/{BASE}"


def list_tables(client: httpx.Client):
    r = client.get(META, headers=HEADERS)
    r.raise_for_status()
    return {t["name"]: t for t in r.json().get("tables", [])}


def create_table(client: httpx.Client, name: str, fields: list) -> dict:
    body = {
        "name": name,
        "fields": [{"name": "Name", "type": "singleLineText"}, *fields],
    }
    r = client.post(META, headers=HEADERS, json=body)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create {name} failed: {r.status_code} {r.text}")
    return r.json()


def ensure_tables(client: httpx.Client) -> None:
    existing = list_tables(client)

    if "Clients" not in existing:
        create_table(
            client,
            "Clients",
            [
                {"name": "Email", "type": "email"},
                {"name": "Aliases", "type": "singleLineText"},
                {"name": "NeedsReview", "type": "checkbox", "options": {"color": "yellowBright", "icon": "check"}},
            ],
        )
        print("Created Clients")
    else:
        print("Clients exists")

    if "Invoices" not in existing:
        create_table(
            client,
            "Invoices",
            [
                {"name": "ClientRecordId", "type": "singleLineText"},
                {"name": "ClientName", "type": "singleLineText"},
                {"name": "AmountCents", "type": "number", "options": {"precision": 0}},
                {"name": "RemainingCents", "type": "number", "options": {"precision": 0}},
                {"name": "Status", "type": "singleLineText"},
                {"name": "Currency", "type": "singleLineText"},
            ],
        )
        print("Created Invoices")
    else:
        print("Invoices exists")

    if "Payments" not in existing:
        create_table(
            client,
            "Payments",
            [
                {"name": "ClientRecordId", "type": "singleLineText"},
                {"name": "InvoiceRecordId", "type": "singleLineText"},
                {"name": "AmountCents", "type": "number", "options": {"precision": 0}},
                {"name": "ExternalId", "type": "singleLineText"},
                {"name": "Source", "type": "singleLineText"},
                {"name": "Status", "type": "singleLineText"},
            ],
        )
        print("Created Payments")
    else:
        print("Payments exists")


def seed(client: httpx.Client) -> None:
    # If Jose already exists, skip seed
    cr = client.get(f"{DATA}/Clients", headers=HEADERS, params={"maxRecords": 100})
    cr.raise_for_status()
    clients = cr.json().get("records", [])
    jose = None
    for rec in clients:
        if (rec.get("fields") or {}).get("Name") == "Jose Martinez Studio":
            jose = rec
            break

    if not jose:
        r = client.post(
            f"{DATA}/Clients",
            headers=HEADERS,
            json={
                "fields": {
                    "Name": "Jose Martinez Studio",
                    "Email": "jose@example.com",
                    "Aliases": "Jose Martinez, J Martinez",
                    "NeedsReview": False,
                }
            },
        )
        r.raise_for_status()
        jose = r.json()
        print("Seeded client", jose["id"])
    else:
        print("Client already seeded", jose["id"])

    client_id = jose["id"]

    ir = client.get(f"{DATA}/Invoices", headers=HEADERS, params={"maxRecords": 100})
    ir.raise_for_status()
    invoices = ir.json().get("records", [])
    have_1000 = any(
        (x.get("fields") or {}).get("Name") == "INV-DEMO-1000"
        and (x.get("fields") or {}).get("Status") == "open"
        for x in invoices
    )
    have_20 = any(
        (x.get("fields") or {}).get("Name") == "INV-DEMO-20"
        and (x.get("fields") or {}).get("Status") == "open"
        for x in invoices
    )

    if not have_1000:
        r = client.post(
            f"{DATA}/Invoices",
            headers=HEADERS,
            json={
                "fields": {
                    "Name": "INV-DEMO-1000",
                    "ClientRecordId": client_id,
                    "ClientName": "Jose Martinez Studio",
                    "AmountCents": 100000,
                    "RemainingCents": 100000,
                    "Status": "open",
                    "Currency": "usd",
                }
            },
        )
        r.raise_for_status()
        print("Seeded invoice INV-DEMO-1000", r.json()["id"])
    else:
        print("INV-DEMO-1000 already open")

    if not have_20:
        r = client.post(
            f"{DATA}/Invoices",
            headers=HEADERS,
            json={
                "fields": {
                    "Name": "INV-DEMO-20",
                    "ClientRecordId": client_id,
                    "ClientName": "Jose Martinez Studio",
                    "AmountCents": 2000,
                    "RemainingCents": 2000,
                    "Status": "open",
                    "Currency": "usd",
                }
            },
        )
        r.raise_for_status()
        print("Seeded invoice INV-DEMO-20", r.json()["id"])
    else:
        print("INV-DEMO-20 already open")


def main() -> int:
    with httpx.Client(timeout=30.0) as client:
        ensure_tables(client)
        # refresh after creates
        seed(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
