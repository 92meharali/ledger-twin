# 04 — Scorecard dashboard + `/eval/run` + killer demo path

**What to build:** A reliability scorecard (entity-resolution accuracy, duplicate-catch rate, false-merge rate, escalation rate, eval pass counts) powered by EventLog and Axiom-backed counts. `POST /eval/run` injects the verification fixture suite and persists pass/fail. The rehearsable demo path works end-to-end: wrong name → Slack Approve → duplicate webhook blocked → scorecard ticks.

**Blocked by:** 03 — Slack HITL + temp-mail payment signals

**Status:** ready-for-agent

- [ ] `GET /scorecard` returns aggregate reliability metrics and recent events (including triad annotations)
- [ ] Simple dashboard UI polls `/scorecard` and shows live numbers suitable for judges
- [ ] `POST /eval/run` executes the fixture suite and writes results into scorecard/EventLog
- [ ] Killer demo path documented and runnable: wrong-name payment → Slack Approve → identical webhook blocked → scorecard updates
- [ ] Hard-pass verification before demo: clean payment, duplicate block, fuzzy escalate, partial amount, Slack approve/reject, scorecard + eval smoke
