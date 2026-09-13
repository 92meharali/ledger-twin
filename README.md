# Ledger Twin

> **Live demo / source:** [https://github.com/92meharali/ledger-twin](https://github.com/92meharali/ledger-twin)  
> **Run locally →** App [`http://127.0.0.1:8000/app`](http://127.0.0.1:8000/app) · Ops scorecard [`http://127.0.0.1:8000/dashboard`](http://127.0.0.1:8000/dashboard) · API docs [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs)

Payment & identity reconciliation agent for the **Lemma × Comma Capital Hackathon**.

> Your books lie until payments, emails, and client names agree.

---

## What judges should see

1. A **Stripe-shaped payment** arrives with a messy name (`Curser`) for **[Cursor](https://cursor.com)**.
2. The agent does **not** silently merge — it escalates with the ambiguity triad (*Same entity? Already happened? Who acts?*).
3. A **Slack** Approve/Reject card appears (Socket Mode — works without ngrok).
4. Human **Approves** → Airtable ledger updates.
5. The **same payment** replays → **blocked as duplicate**.
6. Ops **scorecard** + `/eval/run` prove reliability.

One-shot rehearsal:

```bash
curl -s -X POST http://127.0.0.1:8000/demo/killer | python3 -m json.tool
```

---

## What has been implemented

| Area | Status | Detail |
|---|---|---|
| Stripe webhooks | Done | `POST /webhooks/stripe` with signature verify |
| Idempotency Guard | Done | SQLite claim key; duplicates → `blocked_duplicate` |
| Entity resolution | Done | RapidFuzz bands + OpenAI middle-band judge |
| Strict match policy | Done | Auto-close only if high confidence **and** exact amount |
| Slack HITL | Done | Block Kit cards + Socket Mode buttons (+ HTTP interact fallback) |
| Temp-mail signals | Done | mail.tm poll + plant-and-ingest demo |
| Airtable ledger | Done | Clients, Invoices, Payments, EventLog (+ Website links) |
| Axiom observability | Done | Event ingest on every pipeline outcome |
| Reliability scorecard | Done | `/dashboard`, `GET /scorecard` |
| Eval harness | Done | `POST /eval/run` (8 cases) + unit tests (`pytest`) |
| User workspace | Done | Auth, invoices, tasks, history, light/dark (`/app`) |
| Brand demo data | Done | Cursor, Slack, Anthropic/Claude, Stripe, Notion, Linear |

**Tickets 01–04:** complete (see `.scratch/ledger-twin/issues/`).

---

## How the app works (complete flow)

```
Stripe / temp-mail / demo scenario
        │
        ▼
   Normalize event  (name, email, amount, metadata.website)
        │
        ▼
   Idempotency Guard ──duplicate?──► blocked_duplicate → Airtable + Axiom
        │ fresh
        ▼
   Entity resolve (RapidFuzz → OpenAI if middle band)
        │
        ▼
   Strict payment↔invoice match
        │
        ├── auto_closed  → mark invoice paid + payment row
        └── pending_*    → SQLite pending + Slack Approve/Reject card
                                │
                                ▼
                         Human Approve → mutate ledger
                         Human Reject  → no ledger close
                                │
                                ▼
                         EventLog (Airtable) + Axiom ingest
```

### Ambiguity triad (written on every outcome)

| Field | Meaning |
|---|---|
| **Same entity?** | Is this payment about the same client as the ledger row? |
| **Already happened?** | Did we already process this (idempotency)? |
| **Who acts?** | `agent` vs `human` vs `none` |

### Demo brands (Stripe billing names + links)

| Client | Website | Typical demo |
|---|---|---|
| Cursor | https://cursor.com | Exact match / fuzzy `Curser` / killer path |
| Slack | https://slack.com | Partial pay |
| Anthropic | https://www.anthropic.com | Portfolio + Claude aliases |
| Stripe | https://stripe.com | Seed invoice |
| Notion | https://www.notion.so | Seed invoice |
| Linear | https://linear.app | Seed invoice |

Seed / refresh open invoices:

```bash
curl -s -X POST http://127.0.0.1:8000/demo/seed-open-invoices | python3 -m json.tool
# or
python scripts/ensure_ledger_tables.py
```

---

## How tests make it reliable

### Unit tests (`pytest`) — fast, no cloud keys required

```bash
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

They cover:

- Brand catalog + Stripe payload metadata (`website`, `company`)
- Stripe normalize → name hints
- Idempotency duplicate block (temp SQLite)
- Strict matcher refuses auto-close on amount mismatch
- Slack signing secret HMAC verify + button parse
- `/health` smoke via FastAPI `TestClient`

### Live eval harness — end-to-end against Airtable / LLM

```bash
curl -s -X POST http://127.0.0.1:8000/eval/run | python3 -m json.tool
```

Eight cases: clean auto-close, duplicate block, fuzzy escalate, no silent merge, partial amount, HITL approve, temp-mail ingest, scorecard shape.

Together: **unit tests** catch logic regressions offline; **eval** proves the live agent spine still behaves under strict policy.

---

## Quick start

```bash
git clone https://github.com/92meharali/ledger-twin.git
cd ledger-twin
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill secrets — see SECRETS.md

uvicorn app.main:app --reload --port 8000
```

Stripe CLI (optional):

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
# set STRIPE_WEBHOOK_SECRET=whsec_… and restart
```

Slack buttons (local): set `SLACK_APP_TOKEN` (`xapp-…`, scope `connections:write`) and enable **Socket Mode** in the Slack app. No public URL required.

---

## Key URLs

| URL | Purpose |
|---|---|
| http://127.0.0.1:8000/app | User workspace |
| http://127.0.0.1:8000/dashboard | Reliability scorecard |
| http://127.0.0.1:8000/docs | OpenAPI |
| `POST /demo/killer` | Full killer path |
| `POST /demo/scenario/fuzzy-name` | Cursor fuzzy escalate |
| `POST /eval/run` | Eval suite |
| `POST /webhooks/stripe` | Stripe |
| `POST /webhooks/slack/interact` | Slack HTTP fallback |

---

## Repo layout

```
app/                 FastAPI agent, auth, static UIs
  demo_catalog.py    Brand names + website links for Stripe-shaped demos
  pipeline.py        Orchestration
  services/          Airtable, Axiom, Slack, matcher, resolve, temp-mail
tests/               pytest unit suite
scripts/             Airtable schema + seed
DEMO.md              3-minute demo script
SECRETS.md           Where to get each key
.env.example         Env template (no secrets)
```

---

## External services (≥5)

Stripe · Airtable · Axiom · OpenAI · Slack · Temp-mail (mail.tm)

---

## Security

Never commit `.env`. Rotate any keys that were shared in chat after the hackathon. Prefer Socket Mode for Slack interactivity locally; keep `DEMO_MODE` off if you expose the API publicly.

Full build PDF: [`Ledger_Twin_Hackathon_Spec.pdf`](Ledger_Twin_Hackathon_Spec.pdf)
