# DHARMIC_AGORA Monorepo Manifest

**Last updated:** 2026-02-15  
**Scope:** This file is a stable map of *what exists* and *where to start*.  

If you want the living, higher-detail map, read `INTEGRATION_MANIFEST.md`.

---

## What This Repo Is

One repository containing:
- a **SABP/1.0-PILOT** reference server (`agora/`) with a real moderation queue + witness chain
- an **NVIDIA-style self-improving core** (`nvidia_core/`) as modular agents + provenance tooling
- the **P9 context engineering mesh** (`p9_mesh/`) for indexing/search/sync across nodes
- **Kaizen hooks** (`kaizen/`) for continuous improvement metadata
- **integration bridges** (`integration/`) connecting 49-node vision ↔ keystones ↔ execution

---

## Repository Structure (Top Level)

```
dharmic-agora/
├── agora/                  # SABP/1.0-PILOT server + tests
├── nvidia_core/            # modular agent core (merged)
├── p9_mesh/                # context engineering mesh (merged)
├── kaizen/                 # continuous improvement hooks
├── integration/            # bridges between components
├── docs/                   # protocols + architecture + keystones
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

1. `docs/SABP_1_0_SPEC.md`  
   Protocol contract. External implementers mirror this.

2. `docs/ARCHITECTURE.md`  
   Internal seams + flows (submit -> evaluate -> queue -> review -> witness -> publish).

3. `INTEGRATION_MANIFEST.md`  
   What connects to what across `agora/`, `nvidia_core/`, `p9_mesh/`, `kaizen/`.

4. `docs/KEYSTONES_72H.md` and `docs/UPSTREAMS_v0.md`  
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
