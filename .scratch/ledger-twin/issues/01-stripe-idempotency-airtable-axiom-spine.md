# 01 — Stripe → Idempotency → Airtable + Axiom spine

**What to build:** A Stripe test webhook hits the app, gets normalized into a common Event, is guarded against duplicates via an idempotency hash store, and lands in Airtable `EventLog` and Axiom. Re-firing the same webhook is blocked and visible in both places. Health check and public URL wiring work so Stripe can reach the endpoint.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] FastAPI app boots with `/health` and loads config from `.env`
- [ ] `POST /webhooks/stripe` verifies Stripe signature and normalizes the payload into an Event
- [ ] Duplicate events (same source + external_id + amount + day) are blocked and recorded; only the first proceeds
- [ ] Accepted and blocked events are written to Airtable `EventLog` and ingested to Axiom dataset `ledger-twin`
- [ ] Manual verification: send one Stripe test event, then the identical payload again — second is blocked in EventLog + Axiom
