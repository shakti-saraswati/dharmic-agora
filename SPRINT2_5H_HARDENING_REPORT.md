# Sprint 2 — 5H Hardening Report

## Scope Executed

Hardening pass completed against `agora.app` on clean branch `codex/5h-bootstrap-hardening-clean`.

Focus areas completed:
1. health/readiness compatibility,
2. deploy + rollback tooling for AGNI,
3. backup/restore + witness integrity verification,
4. session/cookie security hardening,
5. cache diagnostics and invalidation regression coverage,
6. docs synchronization.

## What Changed

### Runtime/API
- Added compatibility + readiness endpoints:
  - `GET /health`
  - `GET /healthz`
  - `GET /readyz`
- Added cache/session diagnostics endpoint:
  - `GET /api/web/cache/status`
- Added cache metadata in `GET /api/node/status`.

### Security Hardening
- Web session cookie policy now configurable via env:
  - `SAB_WEB_SESSION_COOKIE_NAME`
  - `SAB_WEB_SESSION_COOKIE_SECURE`
  - `SAB_WEB_SESSION_COOKIE_HTTPONLY`
  - `SAB_WEB_SESSION_COOKIE_SAMESITE`
- Added template-safe public session projection to avoid exposing private key material in rendered pages.

### Ops / Deploy
- Added AGNI deployment assets:
  - `deploy/systemd/sab-app.service`
  - `deploy/nginx/sab.conf`
  - `scripts/deploy_agni.sh`
  - `scripts/rollback_agni.sh`
  - `docs/DEPLOY_AGNI_CHECKLIST.md`

### Data Safety
- Added backup/restore scripts:
  - `scripts/backup_sab_db.sh`
  - `scripts/restore_sab_db.sh`
- Added witness integrity checker:
  - `scripts/verify_witness_chain.py`

### Smoke Testing
- Added app runtime smoke script:
  - `scripts/smoke_test_app.sh`

### Tests Added/Expanded
- `tests/test_health_endpoints.py` (health/readiness/cache diagnostics)
- `tests/test_verify_witness_chain.py` (valid + tamper paths)
- `tests/test_web_surface.py` expanded (private key non-leak + cache invalidation)
- `tests/test_spark_api.py` expanded (challenge/witness signature mismatch rejection)

### Docs Updated
- `README.md`
- `docs/INDEX.md`
- `docs/DEPLOY_AGNI_CHECKLIST.md` (new)
- `RUNLOG_5H.md` (new execution log)

## Verification Results

- Targeted hardening suites: `28 passed`
- Full suite: `pytest -q` => `262 passed`
- Compile check: `python3 -m compileall -q agora tests scripts` => clean

Note on smoke execution in this environment:
- `scripts/smoke_test_app.sh` is implemented, but localhost bind is blocked in this sandbox.
- Expected to run normally on AGNI VPS or standard local host.

## Residual Risks / Follow-Up

1. Deploy scripts assume SSH + sudo privileges on AGNI host.
2. Smoke script should be validated once on AGNI with real systemd/nginx wiring.
3. Web-session keys are currently in-memory (intentional for Sprint 2); move to encrypted persistence if long-lived browser sessions become required.

## Suggested Sprint 3 Backlog

1. Add authenticated admin diagnostics surface for deploy/cache/session health.
2. Add signed governance mutation ledger endpoints (Section 0 witness triad completion).
3. Add periodic backup + witness-integrity cron on AGNI.
4. Add load tests for feed/challenge/witness mutation throughput.
