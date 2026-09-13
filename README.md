# Ledger Twin

> **Live (Vercel):** [https://ledger-twin.vercel.app](https://ledger-twin.vercel.app)  
> **Demo video:** [Dark Phoenix walkthrough (Google Drive)](https://drive.google.com/file/d/1QmEg3FgbV0J8gi7wgbU4NMrZnpsfwNOf/view?usp=drive_link)  
> **Source:** [https://github.com/92meharali/ledger-twin](https://github.com/92meharali/ledger-twin)

| | |
|---|---|
| App | [https://ledger-twin.vercel.app/app](https://ledger-twin.vercel.app/app) |
| Ops scorecard | [https://ledger-twin.vercel.app/dashboard](https://ledger-twin.vercel.app/dashboard) |
| API docs | [https://ledger-twin.vercel.app/docs](https://ledger-twin.vercel.app/docs) |
| Health | [https://ledger-twin.vercel.app/health](https://ledger-twin.vercel.app/health) |
| Demo login | `demo@ledgertwin.dev` / `demo1234` |

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
7. Every outcome is written to **Axiom** (flattened triad fields for queryable ops).
8. On the **1st of every month**, a full previous-month record (Stripe + temp-mail + HITL) is emailed to **`hamzafarooqsea@gmail.com`**.

One-shot rehearsal (local or against production with `DEMO_MODE`):

```bash
curl -s -X POST https://ledger-twin.vercel.app/demo/killer | python -m json.tool
```

---

## Live URLs (Vercel)

| URL | Purpose |
|---|---|
| https://ledger-twin.vercel.app | Home → redirects to `/app` |
| https://ledger-twin.vercel.app/app | User workspace |
| https://ledger-twin.vercel.app/dashboard | Reliability scorecard UI |
| https://ledger-twin.vercel.app/docs | OpenAPI / Swagger |
| https://ledger-twin.vercel.app/health | Liveness + integration flags |
| https://ledger-twin.vercel.app/scorecard | JSON scorecard |
| https://ledger-twin.vercel.app/reports/monthly | Preview previous month record |
| `POST /cron/monthly-report` | Vercel Cron (daily 08:00 UTC; sends on the 1st) |
| `POST /reports/monthly/send` | Manual send (requires `CRON_SECRET`) |

**Project dashboard:** [Vercel · ledger-twin](https://vercel.com/muhammad-hamza-farooqs-projects-0f6862aa/ledger-twin)

---

## What has been implemented

| Area | Status | Detail |
|---|---|---|
| Stripe webhooks | Done | `POST /webhooks/stripe` with signature verify |
| Idempotency Guard | Done | SQLite claim key; duplicates → `blocked_duplicate` |
| Entity resolution | Done | RapidFuzz bands + OpenAI middle-band judge |
| Strict match policy | Done | Auto-close only if high confidence **and** exact amount |
| Slack HITL | Done | Block Kit cards + Socket Mode buttons (+ HTTP interact fallback) |
| Temp-mail signals | Done | mail.tm poll + plant-and-ingest demo (**inbound** payment emails) |
| Airtable ledger | Done | Clients, Invoices, Payments, EventLog (+ Website links) |
| **Axiom observability** | Done | Detailed ingest (flattened triad, retries, lifecycle events) + APL month query |
| **Monthly email report** | Done | 1st-of-month cron → previous complete month → `REPORT_TO_EMAIL` |
| Reliability scorecard | Done | `/dashboard`, `GET /scorecard` |
| Eval harness | Done | `POST /eval/run` (8 cases) + unit tests (`pytest`) |
| User workspace | Done | Auth, invoices, tasks, history, light/dark (`/app`) |
| Brand demo data | Done | Cursor, Slack, Anthropic/Claude, Stripe, Notion, Linear |
| Vercel deploy | Done | FastAPI service at https://ledger-twin.vercel.app |

---

## Axiom logging (detailed)

Every pipeline / HITL outcome is ingested into the `ledger-twin` dataset.

### Fields written

| Field | Meaning |
|---|---|
| `_time` | Event timestamp (UTC) — used for monthly APL windows |
| `ingested_at` | When Axiom received the row |
| `service` | Always `ledger-twin` |
| `kind` | `pipeline_outcome`, `temp_mail_poll`, `monthly_report`, … |
| `status` | `auto_closed`, `blocked_duplicate`, `pending_*`, `approved`, `rejected`, … |
| `source` / `type` / `external_id` | Stripe / temp_mail / hitl identifiers |
| `idempotency_key` | Dedup key |
| `amount_cents` / `currency` / `event_day` | Money + calendar day |
| `name_hints` / `email_hints` | Entity hints |
| `same_entity` / `already_happened` / `who_acts` / `confidence` | **Flattened triad** (queryable) |
| `triad` | Nested copy for dashboards |
| Extra | `ClientRecordId`, `EntityScore`, `MatchAction`, `InvoiceRecordId`, `SlackTs`, … |

### Lifecycle events

- Temp-mail poll `started` / `completed` (with fetch counts)
- Monthly report `sent` / `send_failed` (recipient, month label, event counts)

### Module

`app/services/axiom_client.py` — `ingest_event`, `ingest_raw`, `query_month` (APL), org header support, one retry on ingest failure.

Set `AXIOM_TOKEN`, `AXIOM_DATASET=ledger-twin`, optional `AXIOM_ORG_ID` / `AXIOM_EDGE`.

---

## Temp-mail + monthly email to hamzafarooqsea@gmail.com

### Inbound (mail.tm)

Temp-mail is **receive-only**. Payment-shaped emails are polled / planted and run through the same agent spine (`source=temp_mail`).

```bash
curl -X POST https://ledger-twin.vercel.app/temp-mail/poll
curl -X POST https://ledger-twin.vercel.app/temp-mail/demo/plant-and-ingest \
  -H 'Content-Type: application/json' \
  -d '{"subject":"Payment received","body":"paid via e-transfer $1000\nClient: Cursor\nhttps://cursor.com"}'
```

### Outbound monthly record

On the **1st of each month** (cron at 08:00 UTC), Ledger Twin builds the **previous complete month** record (Airtable EventLog ∪ Axiom) including:

- All Stripe / temp-mail / HITL outcomes for that month  
- Status + source breakdowns  
- Total USD  
- Dedicated **temp-mail payments** section  

…and emails it to **`hamzafarooqsea@gmail.com`** (`REPORT_TO_EMAIL`).

| Env | Purpose |
|---|---|
| `REPORT_TO_EMAIL` | Default `hamzafarooqsea@gmail.com` |
| `RESEND_API_KEY` | Preferred sender ([Resend](https://resend.com)) |
| `SMTP_*` | Optional SMTP fallback |
| `CRON_SECRET` | Protects cron / manual send |
| `DEMO_MODE=true` | Without Resend/SMTP, emails go to an in-memory outbox (`GET /reports/outbox`) |

Preview / force-send:

```bash
curl -s https://ledger-twin.vercel.app/reports/monthly | python -m json.tool
curl -s -X POST https://ledger-twin.vercel.app/reports/monthly/send \
  -H "Authorization: Bearer $CRON_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"force":true}'
```

Vercel Cron (`vercel.json`): daily `0 8 * * *` → `/cron/monthly-report` (sends only when `today.day == 1`).

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
                         EventLog (Airtable) + Axiom ingest (flattened triad)

Monthly (1st):
  Aggregate prior month (Airtable ∪ Axiom) → email → hamzafarooqsea@gmail.com → Axiom audit
```

### Ambiguity triad (written on every outcome)

| Field | Meaning |
|---|---|
| **Same entity?** | Is this payment about the same client as the ledger row? |
| **Already happened?** | Did we already process this (idempotency)? |
| **Who acts?** | `agent` vs `human` vs `none` |

---

## How tests make this reliable

Reliability is enforced in **two layers**: offline unit tests (no cloud keys) and a live eval harness.

### Unit tests (`pytest`) — fast regression gate

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

| Suite | What it proves |
|---|---|
| `tests/test_core.py` | Brand catalog + Stripe metadata; normalize name hints; **idempotency blocks duplicates**; matcher refuses auto-close on amount mismatch; Slack HMAC + button parse; `/health` smoke |
| `tests/test_axiom_monthly.py` | Axiom triad flattening + ingest payload shape; skip without token; **previous complete month** math; monthly summary filters (Stripe vs temp-mail); **email outbox to `hamzafarooqsea@gmail.com`** in DEMO_MODE; cron skip-unless-1st behavior |

Together these lock in: *no silent wrong merge on fuzzy names*, *duplicates never double-post*, *observability fields stay queryable*, *monthly mail targets the right recipient*.

### Live eval harness — end-to-end against Airtable / LLM

```bash
curl -s -X POST https://ledger-twin.vercel.app/eval/run | python -m json.tool
```

Eight cases: clean auto-close, duplicate block, fuzzy escalate, **no silent merge**, partial amount, HITL approve, temp-mail ingest, scorecard shape.

**Unit tests** catch logic regressions offline. **Eval** proves the live agent spine still obeys strict policy. **Axiom** retains the audit trail. **Monthly email** closes the loop for humans.

---

## Quick start

```bash
git clone https://github.com/92meharali/ledger-twin.git
cd ledger-twin
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env   # fill secrets — see SECRETS.md

uvicorn app.main:app --reload --port 8000
pytest -q
```

Production (Vercel): set the same env vars in Project Settings, including `AXIOM_TOKEN`, `REPORT_TO_EMAIL`, and `RESEND_API_KEY` (or SMTP) for real monthly delivery.

Demo login: `demo@ledgertwin.dev` / `demo1234`

---

## Repo layout

```
app/
  main.py                 FastAPI entry (Vercel service)
  pipeline.py             Orchestration → Airtable + Axiom
  services/
    axiom_client.py       Detailed Axiom ingest + APL month query
    monthly_report.py     Previous-month aggregate + email render/send
    mail_outbound.py      Resend / SMTP / DEMO outbox
    tempmail.py           mail.tm inbound client
    email_ingest.py       Temp-mail → pipeline (+ Axiom poll lifecycle)
  routes/
    reports.py            /reports/monthly, /cron/monthly-report
tests/
  test_core.py            Core reliability unit tests
  test_axiom_monthly.py   Axiom + monthly email unit tests
vercel.json               FastAPI service + daily cron
```

---

## External services (≥5)

Stripe · Airtable · Axiom · OpenAI · Slack · Temp-mail (mail.tm) · Resend/SMTP (monthly outbound) · Vercel

---

## Security

Never commit `.env`. Rotate any keys that were shared in chat after the hackathon. Prefer Socket Mode for Slack interactivity locally; keep `DEMO_MODE` off if you expose the API publicly without auth. Protect cron with `CRON_SECRET`.
