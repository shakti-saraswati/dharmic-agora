"""Central DB path registry for DHARMIC_AGORA runtime components.

Logical names map to default SQLite file paths under `data/`.
Environment variables can still override specific consumers (e.g. SAB_DB_PATH).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DATA_DIR = _REPO_ROOT / "data"

DB_PATHS = {
    "sabp": _DATA_DIR / "sabp.db",
    "witness": _DATA_DIR / "witness.db",
    "p9_memory": _DATA_DIR / "p9_memory.db",
    "p9_agent_core": _DATA_DIR / "p9_agent_core.db",
}

