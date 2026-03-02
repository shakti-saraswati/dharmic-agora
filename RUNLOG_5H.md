# RUNLOG 5H Bootstrap Hardening

## [00:06] Baseline Capture
- Branch: `codex/5h-bootstrap-hardening-clean` (from `origin/main` @ `b20864b`).
- Canonical runtime: `agora/app.py`.
- Route inventory captured from `agora/app.py` shows API + Sprint 2 web endpoints.
- Baseline tests: `pytest -q` => `252 passed`.
- README reviewed: Sprint 2 surface documented; deploy/ops runbooks not yet complete.

## [00:07] Phase Plan Lock
- Starting with Phase B: health/readiness compatibility + app smoke script + tests.
- Will keep scope constrained to production hardening, no architecture rewrites.

## [00:24] Phase B Complete (with sandbox note)
- Added health endpoints to `agora.app`: `/health`, `/healthz`, `/readyz`.
- Added `tests/test_health_endpoints.py`.
- Added `scripts/smoke_test_app.sh` for app.py startup + flow checks.
- Validation:
  - `pytest -q tests/test_health_endpoints.py tests/test_web_surface.py tests/test_spark_api.py tests/test_rv_signal.py` => 21 passed.
- Sandbox limitation:
  - local port bind (`127.0.0.1:8012`) is blocked in this execution environment.
  - smoke script expected to run on normal host/AGNI VPS.

## [00:56] Phase C Complete
- Added deploy assets:
  - `deploy/systemd/sab-app.service`
  - `deploy/nginx/sab.conf`
  - `scripts/deploy_agni.sh`
  - `scripts/rollback_agni.sh`
  - `docs/DEPLOY_AGNI_CHECKLIST.md`
- Deploy scripts include guardrails and explicit env controls.

## [01:06] Phase D Complete
- Added data safety tools:
  - `scripts/backup_sab_db.sh`
  - `scripts/restore_sab_db.sh`
  - `scripts/verify_witness_chain.py`
- Added tests:
  - `tests/test_verify_witness_chain.py`
  - validates success and tamper-detection non-zero exit.

## [01:19] Phase E Complete
- Hardened web session cookie controls via env:
  - `SAB_WEB_SESSION_COOKIE_NAME`
  - `SAB_WEB_SESSION_COOKIE_SECURE`
  - `SAB_WEB_SESSION_COOKIE_HTTPONLY`
  - `SAB_WEB_SESSION_COOKIE_SAMESITE`
- Added template-safe session projection to prevent private key exposure.
- Added signed-action negative tests:
  - challenge signature mismatch rejection
  - witness signature mismatch rejection

## [01:31] Phase F Complete
- Added cache diagnostics endpoint: `GET /api/web/cache/status`.
- Added cache metadata to node status.
- Added cache invalidation regression test for submit/challenge/witness mutation paths.

## [01:38] Verification
- Targeted suites: 28 passed.
- Full suite: `pytest -q` => 262 passed.
- Compile check: `python3 -m compileall -q agora tests scripts` => clean.
- Smoke script exists and is host-runnable; local execution still blocked in sandbox due localhost bind permissions.
