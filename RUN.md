## Run the API (ticket 01)

```bash
cd /Users/meharali/Work/924B3ABC-9A26-4BFD-A23C-91259B926BBA
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + config + idempotency counts |
| POST | `/webhooks/stripe` | Stripe webhook (signature verified when `STRIPE_WEBHOOK_SECRET` set) |
| POST | `/demo/stripe-event` | Local inject (DEMO_MODE) — fire twice to prove duplicate block |
| GET | `/docs` | Swagger UI |

### Test idempotency without Stripe CLI

```bash
curl -s -X POST http://127.0.0.1:8000/demo/stripe-event -H 'Content-Type: application/json' -d '{}'
curl -s -X POST http://127.0.0.1:8000/demo/stripe-event -H 'Content-Type: application/json' -d '{}'
```

First → `accepted`. Second → `blocked_duplicate`.

### Wire real Stripe webhooks (optional next)

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Copy `whsec_…` into `.env` as `STRIPE_WEBHOOK_SECRET`, restart API, then:

```bash
stripe trigger payment_intent.succeeded
```
