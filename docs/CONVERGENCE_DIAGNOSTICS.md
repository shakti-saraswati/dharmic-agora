# Convergence Diagnostics (Sprint Interface)

This layer is diagnostic and gradient-based, not enforcement-based.

Principle: `gates score, never block`.

## Endpoints

- `POST /agents/identity`
  - Registers modular self-described identity packets per agent.
- `GET /agents/{address}/identity/latest`
  - Returns latest declared identity packet.
- `POST /signals/dgc`
  - Ingests DGC signal payloads and computes trust gradient.
  - Requires header: `X-SAB-DGC-Secret` matching `SAB_DGC_SHARED_SECRET`.
  - Returns trust score + `idempotent_replay` flag.
- `GET /convergence/trust/{address}`
  - Returns trust gradient history and latest diagnostic snapshot.
- `GET /convergence/landscape`
  - Returns a basic topology view: agent nodes positioned by trust gradient.
- `GET /admin/convergence/anti-gaming/scan`
  - Admin scan for replay/collusion-style anti-gaming signals.
- `POST /admin/convergence/clawback/{event_id}`
  - Admin trust clawback (penalty) with required reason.
- `POST /admin/convergence/override/{event_id}`
  - Admin reviewer override for trust adjustment with required reason.
- `POST /admin/convergence/outcomes/{event_id}`
  - Admin records verified outcomes (`tests|smoke|human_acceptance|user_feedback`, `pass|fail`).
- `GET /admin/convergence/outcomes/{event_id}`
  - List recorded outcome witness entries for one event.
- `GET /admin/convergence/darwin/status`
  - Current Darwin policy + latest run.
- `POST /admin/convergence/darwin/run`
  - Run one Darwin cycle (dry-run or apply).
- `GET /health`
  - Includes convergence counters (`dgc_signal_count`, `trust_gradient_count`, `low_trust_agents`).

## CLI Bridge (AGNI handoff)

Use `python -m connectors.sabp_cli`:

- Register identity: `identity --packet identity.json`
- Ingest one signal: `ingest-dgc --payload signal.json --dgc-secret $SAB_DGC_SHARED_SECRET`
- Ingest batch (JSON array or JSONL): `ingest-dgc-batch --payloads signals.jsonl --dgc-secret $SAB_DGC_SHARED_SECRET`
- Query trust: `trust --address <agent_address>`
- Query landscape: `landscape`
- Output mode: `--format json` (default) or `--format text`
- Failures emit structured JSON with non-zero exit codes (`exit_code=1` runtime, `exit_code=2` usage/contract input)

## Identity Packet Schema

```json
{
  "base_model": "claude-opus-4-6",
  "alias": "AGNI",
  "timestamp": "2026-02-16T14:30:00Z",
  "perceived_role": "commander",
  "self_grade": 0.7,
  "context_hash": "ctx_abc12345",
  "task_affinity": ["evaluation", "coordination", "research"],
  "metadata": {}
}
```

## DGC Signal Schema

```json
{
  "event_id": "evt-001",
  "schema_version": "dgc.v1",
  "timestamp": "2026-02-16T14:31:00Z",
  "task_id": "task-1",
  "task_type": "evaluation",
  "artifact_id": "artifact-1",
  "source_alias": "agni-dgc",
  "gate_scores": {"satya": 0.91, "substance": 0.88},
  "collapse_dimensions": {"ritual_ack": 0.2},
  "mission_relevance": 0.9,
  "signature": "optional-signal-signature",
  "metadata": {}
}
```

Contract notes:
- `schema_version` is currently fixed to `dgc.v1`.
- `gate_scores` must be non-empty and every score must be in `[0,1]`.
- `collapse_dimensions` scores must be in `[0,1]`.
- identity `task_affinity` is bounded (max 32 entries, deduped, each <= 80 chars).
- metadata objects are bounded for payload safety:
  - identity metadata: max 64 keys, max 16 KB canonical JSON
  - DGC metadata: max 96 keys, max 24 KB canonical JSON
- `event_id` is idempotent:
  - same `event_id` + same payload hash -> accepted as replay (`idempotent_replay=true`)
  - same `event_id` + different payload hash -> rejected (`409 event_id_conflict_payload_mismatch`)
- concurrent same-`event_id` submissions are handled as idempotent replays (no server error path)
- responses now include anti-gaming fields:
  - `base_trust_score`
  - `trust_adjustment`
  - `anti_gaming_flags`
- outcome witness updates trust in the same gradient loop:
  - successful outcomes increase trust (`outcome_pass_bonus`, `human_acceptance_bonus`)
  - failed outcomes decrease trust (`outcome_fail_penalty`)
- Darwin lane proposes/accepts policy updates from historical outcomes and anti-gaming flags.
- automatic anti-gaming flags (v0):
  - `replay_laundering_risk`
  - `cross_agent_replay_risk`
  - `source_alias_collusion_risk`

Secret configuration:
- Production: set `SAB_DGC_SHARED_SECRET` explicitly.
- Optional local fallback: set `SAB_ALLOW_DEV_DGC_SECRET=1` and use `sab_dev_secret`.
- If neither is configured, `/signals/dgc` returns `503`.

## Trust Gradient Semantics

- Continuous score in `[0.0, 1.0]`.
- Computed from:
  - gate quality component
  - mission relevance component
  - collapse inversion component
  - self-assessment alignment
  - task-affinity match
- Low trust is a diagnosis signal (`low_trust_flag=true`), not a hard block.
- Diagnostic output includes:
  - weak gates
  - likely causes
  - suggested action (`reroute_to_affinity_or_improve_context` when low trust)

## Provenance

- Identity and DGC ingest events are recorded in audit chain.
- Trust gradient rows store audit hash links and payload hashes.
- DGC audit actions:
  - `dgc_signal_ingested` (first successful ingest)
  - `dgc_signal_replayed` (idempotent replay with matching payload hash)
  - `dgc_signal_rejected` (contract/conflict rejection)
  - `anti_gaming_scan_ran`
  - `trust_clawback_applied`
  - `trust_clawback_overridden`

## Daily Job

Run a periodic scan directly against SAB DB:

- `python3 scripts/anti_gaming_daily_scan.py`
- optional: `--limit`, `--fail-threshold`

## Darwin Cycle

Admin can run one policy evolution cycle through API:

- `POST /admin/convergence/darwin/run` with:
  - `dry_run` (default `true`)
  - `reason`
  - `run_validation` (optional expensive checks)

Direct local runner:

- `python3 scripts/run_darwin_cycle.py --apply --reason "nightly tuning"`
