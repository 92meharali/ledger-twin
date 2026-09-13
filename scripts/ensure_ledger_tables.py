#!/usr/bin/env python3
"""Ensure Clients / Invoices / Payments tables exist and seed brand demo ledger rows."""
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

BRANDS = [
    {
        "name": "Cursor",
        "email": "billing@cursor.com",
        "aliases": "Cursor AI, Anysphere",
        "website": "https://cursor.com",
        "invoices": [("INV-CURSOR-1000", 100000), ("INV-CURSOR-20", 2000), ("INV-CURSOR-450", 45000)],
    },
    {
        "name": "Slack",
        "email": "ap@slack.com",
        "aliases": "Slack Technologies, Salesforce Slack",
        "website": "https://slack.com",
        "invoices": [("INV-SLACK-1000", 100000), ("INV-SLACK-875", 87500)],
    },
    {
        "name": "Anthropic",
        "email": "billing@anthropic.com",
        "aliases": "Claude, Anthropic PBC, Claude AI",
        "website": "https://www.anthropic.com",
        "invoices": [("INV-CLAUDE-2500", 250000)],
    },
    {
        "name": "Stripe",
        "email": "billing@stripe.com",
        "aliases": "Stripe Inc, Stripe Payments",
        "website": "https://stripe.com",
        "invoices": [("INV-STRIPE-1200", 120000)],
    },
    {
        "name": "Notion",
        "email": "billing@makenotion.com",
        "aliases": "Notion Labs",
        "website": "https://www.notion.so",
        "invoices": [("INV-NOTION-360", 36000)],
    },
    {
        "name": "Linear",
        "email": "billing@linear.app",
        "aliases": "Linear Orbit",
        "website": "https://linear.app",
        "invoices": [("INV-LINEAR-199", 19900)],
    },
]


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


def ensure_field(client: httpx.Client, table: dict, field_name: str, field_type: str = "singleLineText") -> None:
    existing = {f["name"] for f in table.get("fields", [])}
    if field_name in existing:
        return
    table_id = table["id"]
    r = client.post(
        f"{META}/{table_id}/fields",
        headers=HEADERS,
        json={"name": field_name, "type": field_type},
    )
    if r.status_code not in (200, 201):
        print(f"warn: could not add field {field_name}: {r.status_code} {r.text[:200]}")
    else:
        print(f"Added field {field_name} to {table.get('name')}")


def ensure_tables(client: httpx.Client) -> None:
    existing = list_tables(client)

    if "Clients" not in existing:
        create_table(
            client,
            "Clients",
            [
                {"name": "Email", "type": "email"},
                {"name": "Aliases", "type": "singleLineText"},
                {"name": "Website", "type": "url"},
                {"name": "NeedsReview", "type": "checkbox", "options": {"color": "yellowBright", "icon": "check"}},
            ],
        )
        print("Created Clients")
    else:
        print("Clients exists")
        ensure_field(client, existing["Clients"], "Website", "url")

    existing = list_tables(client)

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
    cr = client.get(f"{DATA}/Clients", headers=HEADERS, params={"maxRecords": 100})
    cr.raise_for_status()
    clients = {((rec.get("fields") or {}).get("Name") or ""): rec for rec in cr.json().get("records", [])}

    ir = client.get(f"{DATA}/Invoices", headers=HEADERS, params={"maxRecords": 100})
    ir.raise_for_status()
    invoices = ir.json().get("records", [])
    inv_by_name = {((x.get("fields") or {}).get("Name") or ""): x for x in invoices}

    for brand in BRANDS:
        rec = clients.get(brand["name"])
        fields = {
            "Name": brand["name"],
            "Email": brand["email"],
            "Aliases": brand["aliases"],
            "Website": brand["website"],
            "NeedsReview": False,
        }
        if not rec:
            r = client.post(f"{DATA}/Clients", headers=HEADERS, json={"fields": fields})
            if r.status_code not in (200, 201):
                fields.pop("Website", None)
                r = client.post(f"{DATA}/Clients", headers=HEADERS, json={"fields": fields})
            r.raise_for_status()
            rec = r.json()
            print("Seeded client", brand["name"], brand["website"], rec["id"])
        else:
            patch = {k: v for k, v in fields.items() if k != "Name"}
            client.patch(f"{DATA}/Clients/{rec['id']}", headers=HEADERS, json={"fields": patch})
            print("Updated client", brand["name"], brand["website"])

        client_id = rec["id"]
        for inv_name, cents in brand["invoices"]:
            existing = inv_by_name.get(inv_name)
            body = {
                "Name": inv_name,
                "ClientRecordId": client_id,
                "ClientName": brand["name"],
                "AmountCents": cents,
                "RemainingCents": cents,
                "Status": "open",
                "Currency": "usd",
            }
            if existing:
                client.patch(
                    f"{DATA}/Invoices/{existing['id']}",
                    headers=HEADERS,
                    json={"fields": body},
                )
                print("Reopened", inv_name)
            else:
                r = client.post(f"{DATA}/Invoices", headers=HEADERS, json={"fields": body})
                r.raise_for_status()
                print("Seeded invoice", inv_name, r.json()["id"])


def main() -> int:
    with httpx.Client(timeout=30.0) as client:
        ensure_tables(client)
        seed(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
