# 02 — Entity resolve + strict payment↔invoice match

**What to build:** An inbound payment resolves a client (RapidFuzz, then OpenAI in the middle band) against Airtable `Clients`, applies the strict match policy, and either auto-closes an exact open invoice or leaves a pending low-confidence action. Ambiguity triad fields (Same entity? Already happened? Who acts?) plus confidence are written to EventLog and Axiom. No Slack UI yet — outcomes are verifiable via API/Airtable.

**Blocked by:** 01 — Stripe → Idempotency → Airtable + Axiom spine

**Status:** **done (verified)**

- [x] RapidFuzz scores incoming name/email against Airtable clients (≥90 auto, 60–89 OpenAI, &lt;60 new client + needs_review)
- [x] Strict policy: auto-close only when name similarity ≥ 90 AND amount matches within configured tolerance
- [x] Near-miss amounts and uncertain entity matches create a pending action — never silent wrong merge or false full-pay
- [x] Successful matches update Airtable `Payments` / `Invoices`; all paths log triad answers + confidence
- [x] Verification: exact match closes invoice; fuzzy middle-band does not silently invent a duplicate client; short payment does not mark invoice paid

## Verified scenarios

| Endpoint | Result |
|---|---|
| `POST /demo/scenario/exact-match` | `auto_closed` INV-DEMO-1000, payment posted |
| `POST /demo/scenario/fuzzy-name` | `pending_entity` (LLM yes, score~74, who_acts=human) |
| `POST /demo/scenario/partial-pay` | `pending_partial`, invoice not fully paid |
