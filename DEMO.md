# Killer Demo Script — Ledger Twin (3 minutes)

Slack is deferred. HITL uses local Approve on the dashboard / API.

## Open the scorecard

http://127.0.0.1:8000/dashboard

## One-shot killer path

```bash
curl -s -X POST http://127.0.0.1:8000/demo/killer | python3 -m json.tool
```

Expected summary:
1. `step1_wrong_name`: `pending_entity`
2. `step2_approve`: `approved`
3. `step3_duplicate`: `blocked_duplicate`
4. scorecard duplicate catch rate ticks up

## Manual beats (live talk)

1. Show Airtable client **Jose Martinez Studio** + open invoice
2. Fire fuzzy payment (or click **Killer demo** on dashboard)
3. Show pending on dashboard → **Approve**
4. Re-fire same payment → blocked (`already_happened=yes`)
5. Point at scorecard metrics + recent EventLog triad fields

## Eval harness

```bash
curl -s -X POST http://127.0.0.1:8000/eval/run | python3 -m json.tool
curl -s http://127.0.0.1:8000/scorecard | python3 -m json.tool
```

Hard-pass cases in `/eval/run`:
- clean exact auto-close
- duplicate block
- fuzzy escalate (no silent merge)
- partial amount
- HITL approve
- temp-mail ingest
- scorecard shape
