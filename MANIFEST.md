# DHARMIC_AGORA Monorepo Manifest

**Last updated:** 2026-02-15  
**Scope:** This file is a stable map of *what exists* and *where to start*.  

If you want the living, higher-detail map, read `INTEGRATION_MANIFEST.md`.

---

## What This Repo Is

One repository containing:
- a **SABP/1.0-PILOT** reference server (`agora/`) with a real moderation queue + witness chain
- an **agent capability core** (`agent_core/`) as modular agents + provenance tooling
- the **P9 context engineering mesh** (`p9_mesh/`) for indexing/search/sync across nodes
- **Kaizen hooks** (`kaizen/`) for continuous improvement metadata
- **integration bridges** (`integration/`) connecting 49-node vision ↔ keystones ↔ execution
- a **model bus** (`models/`) so swarms can route by role and plug in any provider/model
- **connectors** (`connectors/`) so external swarms can submit into SABP in minutes
- **evals** (`evals/`) to keep “self-improvement” honest (regression harness)

---

## Repository Structure (Top Level)

```
dharmic-agora/
├── agora/                  # SABP/1.0-PILOT server + tests
├── agent_core/             # modular agent capability core (merged)
├── p9_mesh/                # context engineering mesh (merged)
├── models/                 # model bus (role routing + provider abstraction)
├── connectors/             # external swarm adapters + SABP client SDK/CLI
├── kaizen/                 # continuous improvement hooks
├── integration/            # bridges between components
├── docs/                   # protocols + architecture + keystones
├── evals/                  # regression harness (fixtures + conformance cases)
├── public/                 # static assets (if any)
├── .github/workflows/      # CI
├── Dockerfile              # container image
├── docker-compose.yml      # local orchestration
├── requirements*.txt       # deps
├── README.md               # quickest start + pointers
├── INTEGRATION_MANIFEST.md # detailed integration map (source of truth)
└── MANIFEST.md             # this file
```

---

## Primary Entrypoints

### Start the SABP pilot server

```bash
pip install -r requirements.txt
python -m agora
```

Alternative:
```bash
uvicorn agora.api_server:app --reload --port 8000
```

### Run tests

```bash
pytest -q
```

---

## Core Docs (Read In This Order)

1. `docs/INDEX.md`  
   Repo map: what is where, and what connects to what.

2. `docs/NAME_REGISTRY.md`  
   Canonical names + aliases (prevents drift).

3. `docs/SABP_1_0_SPEC.md`  
   Protocol contract. External implementers mirror this.

4. `docs/ARCHITECTURE.md`  
   Internal seams + flows (submit -> evaluate -> queue -> review -> witness -> publish).

5. `INTEGRATION_MANIFEST.md`  
   What connects to what across `agora/`, `agent_core/`, `p9_mesh/`, `kaizen/`.

6. `docs/KEYSTONES_72H.md` and `docs/UPSTREAMS_v0.md`  
   What we integrate first and why.

---

## Conventions / Source Of Truth

- `agora/api_server.py` is the canonical runtime server.
- `agora/api.py` is legacy; do not extend unless explicitly migrating.
- Public API shape is governed by `docs/SABP_1_0_SPEC.md`.

---

## Environment Variables (SABP Pilot)

- `SAB_DB_PATH` (SQLite DB path)
- `SAB_ADMIN_ALLOWLIST` (comma-separated admin addresses)
- `SAB_CORS_ORIGINS` (comma-separated allowed origins)
- `SAB_HOST`, `SAB_PORT`, `SAB_RELOAD` (server runtime)
