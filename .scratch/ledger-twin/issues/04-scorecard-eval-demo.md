# 04 — Scorecard dashboard + `/eval/run` + killer demo path

**What to build:** A reliability scorecard (entity-resolution accuracy, duplicate-catch rate, false-merge rate, escalation rate, eval pass counts) powered by EventLog and Axiom-backed counts. `POST /eval/run` injects the verification fixture suite and persists pass/fail. The rehearsable demo path works end-to-end: wrong name → HITL Approve → identical webhook blocked → scorecard ticks.

**Blocked by:** 03 — Slack HITL + temp-mail payment signals (Slack deferred; local HITL used)

**Status:** **done (verified)**

- [x] `GET /scorecard` returns aggregate reliability metrics and recent events (including triad annotations)
- [x] Simple dashboard UI polls `/scorecard` and shows live numbers suitable for judges
- [x] `POST /eval/run` executes the fixture suite and writes results into scorecard/EventLog
- [x] Killer demo path documented and runnable: wrong-name payment → Approve → identical webhook blocked → scorecard updates
- [x] Hard-pass verification: clean payment, duplicate block, fuzzy escalate, partial amount, HITL approve/reject, scorecard + eval smoke

## Verified

- `POST /demo/killer` → ok true (pending_entity → approved → blocked_duplicate)
- `POST /eval/run` → **8/8 PASS**
- `GET /dashboard` → 200
- Scorecard: entity 0.857, dup catch 0.25, escalation 0.304, eval 8/8
