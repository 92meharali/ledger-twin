# 01 — Stripe → Idempotency → Airtable + Axiom spine

**What to build:** A Stripe test webhook hits the app, gets normalized into a common Event, is guarded against duplicates via an idempotency hash store, and lands in Airtable `EventLog` and Axiom. Re-firing the same webhook is blocked and visible in both places. Health check and public URL wiring work so Stripe can reach the endpoint.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent → **done (local verified)**

- [x] FastAPI app boots with `/health` and loads config from `.env`
- [x] `POST /webhooks/stripe` verifies Stripe signature and normalizes the payload into an Event
- [x] Duplicate events (same source + external_id + amount + day) are blocked and recorded; only the first proceeds
- [x] Accepted and blocked events are written to Airtable `EventLog` and ingested to Axiom dataset `ledger-twin`
- [x] Manual verification: send one Stripe test event, then the identical payload again — second is blocked in EventLog + Axiom

## Notes

- Without `STRIPE_WEBHOOK_SECRET`, `DEMO_MODE=true` accepts unsigned JSON on `/webhooks/stripe` and `/demo/stripe-event`.
- Real Stripe: `stripe listen --forward-to localhost:8000/webhooks/stripe` → paste `whsec_…` into `.env`.
- Airtable `EventLog` table created via `scripts/ensure_airtable_eventlog.py`.
