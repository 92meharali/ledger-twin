"""Canonical demo / ledger brands — realistic Stripe billing names + product links."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Primary reconciliation demos use Cursor (exact / fuzzy / killer).
# Partial-pay demos use Slack. Seed portfolio includes the rest for the portal.

DEMO_CLIENTS: List[Dict[str, Any]] = [
    {
        "key": "cursor",
        "name": "Cursor",
        "email": "billing@cursor.com",
        "aliases": "Cursor AI, Anysphere",
        "website": "https://cursor.com",
        "fuzzy_name": "Curser",
        "fuzzy_email": "billing@curser.dev",
        "invoice_1000": "INV-CURSOR-1000",
        "invoice_20": "INV-CURSOR-20",
        "invoice_450": "INV-CURSOR-450",
    },
    {
        "key": "slack",
        "name": "Slack",
        "email": "ap@slack.com",
        "aliases": "Slack Technologies, Salesforce Slack",
        "website": "https://slack.com",
        "fuzzy_name": "Slak Technologies",
        "fuzzy_email": "ap@slak.example",
        "invoice_1000": "INV-SLACK-1000",
        "invoice_875": "INV-SLACK-875",
    },
    {
        "key": "anthropic",
        "name": "Anthropic",
        "email": "billing@anthropic.com",
        "aliases": "Claude, Anthropic PBC, Claude AI",
        "website": "https://www.anthropic.com",
        "fuzzy_name": "Claude AI Inc",
        "fuzzy_email": "billing@claude-ai.example",
        "invoice_2500": "INV-CLAUDE-2500",
    },
    {
        "key": "stripe",
        "name": "Stripe",
        "email": "billing@stripe.com",
        "aliases": "Stripe Inc, Stripe Payments",
        "website": "https://stripe.com",
        "invoice_1200": "INV-STRIPE-1200",
    },
    {
        "key": "notion",
        "name": "Notion",
        "email": "billing@makenotion.com",
        "aliases": "Notion Labs",
        "website": "https://www.notion.so",
        "invoice_360": "INV-NOTION-360",
    },
    {
        "key": "linear",
        "name": "Linear",
        "email": "billing@linear.app",
        "aliases": "Linear Orbit",
        "website": "https://linear.app",
        "invoice_199": "INV-LINEAR-199",
    },
]


def by_key(key: str) -> Dict[str, Any]:
    for c in DEMO_CLIENTS:
        if c["key"] == key:
            return c
    raise KeyError(key)


def stripe_pi_object(
    *,
    pi_id: str,
    amount_cents: int,
    name: str,
    email: str,
    website: str = "",
    company: str = "",
) -> dict:
    """Stripe-shaped payment_intent object with proper billing + metadata links."""
    metadata: Dict[str, str] = {
        "client_name": name,
    }
    if company:
        metadata["company"] = company
    if website:
        metadata["website"] = website
        metadata["product_url"] = website
    return {
        "id": pi_id,
        "amount": amount_cents,
        "currency": "usd",
        "billing_details": {"name": name, "email": email},
        "metadata": metadata,
        "description": f"Payment from {name}" + (f" ({website})" if website else ""),
    }


def stripe_event(*, evt_id: str, pi_id: str, amount_cents: int, client: Dict[str, Any], name_override: Optional[str] = None) -> dict:
    name = name_override or client["name"]
    email = client["email"] if name_override is None else client.get("fuzzy_email") or client["email"]
    # When fuzzing, do NOT put the canonical company name into metadata —
    # normalize() promotes metadata.company into name_hints and would auto-match.
    company = "" if name_override else client["name"]
    return {
        "type": "payment_intent.succeeded",
        "id": evt_id,
        "data": {
            "object": stripe_pi_object(
                pi_id=pi_id,
                amount_cents=amount_cents,
                name=name,
                email=email,
                website=client.get("website") or "",
                company=company,
            )
        },
    }
