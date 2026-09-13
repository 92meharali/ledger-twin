# Ledger Twin

Payment & identity reconciliation agent for the **Lemma × Comma Capital Hackathon** (Sep 13, 2026).

> Your books lie until payments, emails, and client names agree.

## What it is

An agentic pipeline that reconciles Stripe payments, email payment signals, and Airtable ledger records with:

- Idempotency guards (duplicate webhook / double-action protection)
- Fuzzy + Claude entity resolution
- Strict match policy (no silent wrong merges)
- Slack human-in-the-loop when confidence is low
- Axiom observability
- Temp-mail (mail.tm) for disposable payment-email demos
- A live reliability scorecard + `/eval/run` harness

## External services (≥3 required)

| # | Service | Role |
|---|---|---|
| 1 | Stripe (test) | Payment / invoice events |
| 2 | Airtable | Canonical ledger |
| 3 | Slack | HITL Approve / Reject |
| 4 | Axiom | Agent event observability |
| 5 | Temp mail (mail.tm) | Disposable inbox for payment emails |

LLM: Anthropic Claude (agent reasoning — not counted as an “app” integration).

## Build tickets

Vertical slices live in [`.scratch/ledger-twin/issues/`](.scratch/ledger-twin/issues/):

1. [Stripe → Idempotency → Airtable + Axiom spine](.scratch/ledger-twin/issues/01-stripe-idempotency-airtable-axiom-spine.md)
2. [Entity resolve + strict payment↔invoice match](.scratch/ledger-twin/issues/02-entity-resolve-strict-match.md) ← blocked by 01
3. [Slack HITL + temp-mail payment signals](.scratch/ledger-twin/issues/03-slack-hitl-temp-mail.md) ← blocked by 02
4. [Scorecard + `/eval/run` + killer demo](.scratch/ledger-twin/issues/04-scorecard-eval-demo.md) ← blocked by 03

```
01 ──► 02 ──► 03 ──► 04
```

## Spec

Full build spec (workflow, features, tests): [`Ledger_Twin_Hackathon_Spec.pdf`](Ledger_Twin_Hackathon_Spec.pdf)

## Secrets / setup

See [`SECRETS.md`](SECRETS.md) for every key, what it’s for, and **direct signup links**.

```bash
cp .env.example .env
# fill .env using SECRETS.md
```

## Stack (planned)

Python 3.11 · FastAPI · LangGraph · Claude · RapidFuzz · SQLite · Airtable · Slack · Axiom · mail.tm
