# 03 — Slack HITL + temp-mail payment signals

**What to build:** Low-confidence pending actions post a Slack Block Kit message (Approve / Reject) that shows the ambiguity triad. Approve executes the ledger mutation; Reject leaves state unchanged and logs the human decision. A mail.tm temp-mail inbox is polled for payment-style emails (“paid via e-transfer”, etc.), which enter the same normalize → resolve → match pipeline. Gmail remains optional polish and is out of scope for this ticket.

**Blocked by:** 02 — Entity resolve + strict payment↔invoice match

**Status:** done

- [x] Low-confidence actions post to the configured Slack channel with triad fields and Approve/Reject buttons
- [x] `POST /webhooks/slack/interact` verifies Slack signing secret, resumes the pending action, and writes `human_decision` to EventLog + Axiom
- [x] Approve mutates Airtable as planned; Reject performs no ledger mutation
- [x] Temp-mail (mail.tm) credentials from env can list/read messages; payment-like messages become Events in the same pipeline
- [x] Verification: fuzzy/partial case escalates to Slack; Approve closes invoice; Reject leaves it open; a planted temp-mail payment email is ingested without crashing

## Slack

- Pipeline posts Block Kit card on any non-`auto_closed` outcome
- Interactivity URL: `{PUBLIC_BASE_URL}/webhooks/slack/interact`
- Local Approve/Reject on `/app` and `/dashboard` still works as fallback
- `POST /demo/slack/ping` — posts a test approval card (no ledger mutation)

## Temp-mail endpoints

- `POST /temp-mail/setup` — create mail.tm inbox, write `.env`
- `GET /temp-mail/inbox` — show configured address
- `GET /temp-mail/messages` — list inbox
- `POST /temp-mail/poll` — ingest payment-like emails into pipeline
- `POST /temp-mail/demo/plant-and-ingest` — demo without real SMTP
