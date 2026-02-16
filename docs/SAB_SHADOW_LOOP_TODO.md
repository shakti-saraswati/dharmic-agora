# SAB Shadow Loop TODO

Purpose: run an orthogonal track that keeps SAB honest under drift, stress, and blind spots.

This is the "come back every session" list.

## Session Ritual
- [ ] Run `python3 scripts/orthogonal_safety_loop.py`
- [ ] Read `agora/logs/shadow_loop/run_summary.json`
- [ ] If `status=alerting`, file a concrete fix task before coding anything else
- [ ] Append one line to this file under "Session Notes"

## Phase 0 - Bootstrap (Now)
- [x] Make security/compliance modules self-contained (no hard dependency on external `swarm` package path)
- [x] Add local systemic monitor module
- [x] Add one-command shadow loop runner
- [x] Add smoke test for security tooling import/runtime

## Phase 1 - Evidence Quality
- [x] Add canonical red-team fixture set (`agora/evidence/redteam/ab_test_*.json`) for stable ACP output
- [x] Add policy files under `agora/security/policy/` for systemic thresholds and anomaly thresholds
- [x] Add signature key handling runbook (`ACP_SIGNING_KEY`, `TOKEN_SIGNING_KEY`, `SKILL_REGISTRY_SIGNING_KEY`)
- [x] Track trend deltas (today vs previous run) in `run_summary.json`

## Phase 2 - Trust Gates
- [x] Wire ACP status into a moderation-visible endpoint
- [x] Fail closed on "critical+unknown" safety state for privileged actions
- [x] Add replayable "known bad" adversarial corpus and expected outcomes
- [x] Add CI check: shadow loop must execute with zero import/runtime errors

## Phase 3 - Operations Cadence
- [ ] Add cron/launchd entry for hourly shadow loop
- [ ] Add alert routing (file + webhook) for high severity anomalies
- [ ] Add weekly digest report from shadow loop outputs
- [ ] Add SLO: max time from high alert to triaged issue < 24h

## Parking Lot
- [ ] Synthetic agent simulation for burst-rate stress tests
- [ ] Differential analysis between gated and ungated cohorts from pilot logs
- [ ] Cryptographic attestation bundle export for external audits

## Session Notes
- 2026-02-16: Bootstrapped SAB Shadow Loop (self-contained modules + runner + starter tests).
- 2026-02-16: First loop run completed (`status=stable`, `high_alert_count=0`).
- 2026-02-16: Phase 1 reached (policy files + canonical red-team evidence + key runbook + summary trend deltas).
- 2026-02-16: Phase 2 reached (admin safety endpoint + fail-closed privileged writes + adversarial replay corpus + CI runtime gate).
