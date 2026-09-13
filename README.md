# Ledger Twin

Payment & identity reconciliation agent for the **Lemma × Comma Capital Hackathon**.

> Your books lie until payments, emails, and client names agree.

## What it does

An agentic pipeline that reconciles **Stripe** payments and **temp-mail** payment signals against an **Airtable** ledger:

- Idempotency guard (duplicate webhook / double-action protection)
- Fuzzy entity resolution (RapidFuzz) + OpenAI middle-band judgment
- Strict match policy (no silent wrong merges / false full-pay)
- Local HITL Approve/Reject (Slack deferred)
- Axiom observability
- Reliability scorecard + `/eval/run` harness
- User workspace with auth, invoices, tasks, history, light/dark mode

## Apps / URLs (local)

| URL | Purpose |
|---|---|
| http://127.0.0.1:8000/app | User workspace (signup/login) |
| http://127.0.0.1:8000/dashboard | Ops reliability scorecard |
| http://127.0.0.1:8000/docs | API docs |

## External services

| Service | Role |
|---|---|
| Stripe (test) | Payment / invoice webhooks |
| Airtable | Clients, Invoices, Payments, EventLog |
| Axiom | Agent event ingest / observability |
| Temp mail (mail.tm) | Disposable inbox for payment-email signals |
| OpenAI | Entity-resolution reasoning |

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill secrets — see SECRETS.md

uvicorn app.main:app --reload --port 8000
```

Stripe local webhooks:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
# paste whsec_… into .env as STRIPE_WEBHOOK_SECRET, restart API
stripe trigger payment_intent.succeeded
```

## Repo layout

```
app/           FastAPI agent + auth + static UIs
scripts/       Airtable / setup helpers
.scratch/      Ticket specs
DEMO.md        Killer demo script
SECRETS.md     Keys + signup links
.env.example   Env template (no secrets)
```

## Tickets

1. [01 — Stripe spine](.scratch/ledger-twin/issues/01-stripe-idempotency-airtable-axiom-spine.md) — done  
2. [02 — Resolve + match](.scratch/ledger-twin/issues/02-entity-resolve-strict-match.md) — done  
3. [03 — Temp mail (+ Slack deferred)](.scratch/ledger-twin/issues/03-slack-hitl-temp-mail.md) — temp mail done  
4. [04 — Scorecard + eval](.scratch/ledger-twin/issues/04-scorecard-eval-demo.md) — done  

Full build PDF: [`Ledger_Twin_Hackathon_Spec.pdf`](Ledger_Twin_Hackathon_Spec.pdf)

## Security note

Never commit `.env`. Rotate any keys that were shared in chat after the hackathon.
