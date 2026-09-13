# 02 — Entity resolve + strict payment↔invoice match

**What to build:** An inbound payment resolves a client (RapidFuzz, then Claude in the middle band) against Airtable `Clients`, applies the strict match policy, and either auto-closes an exact open invoice or leaves a pending low-confidence action. Ambiguity triad fields (Same entity? Already happened? Who acts?) plus confidence are written to EventLog and Axiom. No Slack UI yet — outcomes are verifiable via API/Airtable.

**Blocked by:** 01 — Stripe → Idempotency → Airtable + Axiom spine

**Status:** ready-for-agent

- [ ] RapidFuzz scores incoming name/email against Airtable clients (≥90 auto, 60–89 Claude, &lt;60 new client + needs_review)
- [ ] Strict policy: auto-close only when name similarity ≥ 90 AND amount matches within configured tolerance
- [ ] Near-miss amounts and uncertain entity matches create a pending action — never silent wrong merge or false full-pay
- [ ] Successful matches update Airtable `Payments` / `Invoices`; all paths log triad answers + confidence
- [ ] Verification: exact match closes invoice; fuzzy middle-band does not silently invent a duplicate client; short payment does not mark invoice paid
