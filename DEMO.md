# Killer demo script — Ledger Twin (~3 minutes)

**Repo / live source:** https://github.com/92meharali/ledger-twin

## Setup

1. API: `uvicorn app.main:app --reload --port 8000`
2. Seed brands (Cursor, Slack, Anthropic/Claude, …):  
   `curl -X POST http://127.0.0.1:8000/demo/seed-open-invoices`
3. Slack Socket Mode: `SLACK_APP_TOKEN` set + Socket Mode enabled
4. Open http://127.0.0.1:8000/dashboard and http://127.0.0.1:8000/app

## One-shot

```bash
curl -s -X POST http://127.0.0.1:8000/demo/killer | python3 -m json.tool
```

Expect `ok: true` — fuzzy **Curser** → Cursor pending → approved → duplicate blocked.

## Narrated beats

1. Show Airtable / portal client **[Cursor](https://cursor.com)** + open `INV-CURSOR-1000`
2. Fire fuzzy payment (`Curser`) → Slack card with triad + website link
3. **Approve** in Slack (or `/app` tasks)
4. Replay → `blocked_duplicate`
5. Point at scorecard + `pytest` / `/eval/run` for reliability story

Also show: Slack partial pay, Anthropic/Claude in portfolio, temp-mail plant.
