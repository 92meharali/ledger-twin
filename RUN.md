## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill secrets — see SECRETS.md
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Production-style (same as Railway):

```bash
./scripts/start.sh
# or: PORT=8000 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness + config + idempotency counts |
| GET | `/app` | User workspace |
| GET | `/dashboard` | Ops reliability scorecard |
| POST | `/webhooks/stripe` | Stripe webhook |
| POST | `/demo/killer` | Killer demo path (DEMO_MODE) |
| GET | `/docs` | Swagger UI |

### Deploy (Railway)

1. Connect GitHub repo `92meharali/ledger-twin` in [Railway](https://railway.app)
2. Uses `Dockerfile` + `railway.toml` (health check `/health`)
3. Paste env vars from `.env` into Railway Variables (never commit secrets)
4. Set `PUBLIC_BASE_URL` / `APP_BASE_URL` to the Railway HTTPS URL after first deploy
5. Demo login: `demo@ledgertwin.dev` / `demo1234`

### Stripe CLI (local only)

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
# copy whsec_… → STRIPE_WEBHOOK_SECRET, restart API
stripe trigger payment_intent.succeeded
```
