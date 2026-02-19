#!/usr/bin/env python3
"""
P9 <-> Agent Core Bridge

Indexes the local `agent_core/` capability library into a small SQLite+FTS index so
agents can query it quickly (and so external swarms can treat it as a searchable
capability substrate).

Why this exists:
- We want "modular but hyper-connected".
- The connection should be via retrieval (P9) and contracts (SABP), not import spaghetti.

Usage:
  python3 p9_agent_core_bridge.py --index
  python3 p9_agent_core_bridge.py --query "vajra flywheel"

Env:
  SAB_AGENT_CORE_ROOT: override the agent core directory (default: <repo>/agent_core)
  P9_DB_PATH: override the sqlite db path (default: <repo>/p9_mesh/p9_agent_core.db)
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

try:
    from agora.db_config import DB_PATHS
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from agora.db_config import DB_PATHS

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_agent_core_root() -> Path:
    import os

    return Path(os.getenv("SAB_AGENT_CORE_ROOT", str(_repo_root() / "agent_core")))


def _default_db_path() -> Path:
    import os

    return Path(os.getenv("P9_DB_PATH", str(DB_PATHS["p9_agent_core"])))


class P9AgentCoreBridge:
    def __init__(self, agent_core_root: Path | None = None, db_path: Path | None = None):
        self.agent_core_root = agent_core_root or _default_agent_core_root()
        self.db_path = db_path or _default_db_path()
        self.conn: sqlite3.Connection | None = None

    def init_db(self) -> None:
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_core_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                unit TEXT,         -- agent name or CORE
                kind TEXT,         -- Agent|Kernel|Doc|Event
                metadata TEXT,
                indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS agent_core_fts USING fts5(
                content,
                path,
                content=agent_core_docs,
                content_rowid=id
            )
            """
        )

        self.conn.commit()

    def extract_unit(self, file_path: Path) -> str:
        path_str = str(file_path).lower()
        for unit in ["akasha", "renkinjutsu", "setu", "vajra", "mmk", "garuda"]:
            if unit in path_str:
                return unit.upper()
        return "CORE"

    def index_agent_core(self) -> int:
        if not self.conn:
            raise RuntimeError("DB not initialized. Call init_db() first.")
        if not self.agent_core_root.exists():
            raise FileNotFoundError(f"agent_core root not found: {self.agent_core_root}")

        files_indexed = 0

        # Docs
        nodes_file = self.agent_core_root / "docs" / "49_NODES.md"
        if nodes_file.exists():
            self._index_file(nodes_file, nodes_file.read_text(), "49_NODES", "Doc")
            files_indexed += 1

        # Agent modules
        agents_dir = self.agent_core_root / "agents"
        if agents_dir.exists():
            for py_file in agents_dir.rglob("*.py"):
                if "__pycache__" in py_file.parts:
                    continue
                content = py_file.read_text()
                unit = self.extract_unit(py_file)
                self._index_file(py_file, content, unit, "Agent")
                files_indexed += 1

        # Core kernel modules
        core_dir = self.agent_core_root / "core"
        if core_dir.exists():
            for py_file in core_dir.rglob("*.py"):
                if "__pycache__" in py_file.parts:
                    continue
                self._index_file(py_file, py_file.read_text(), "CORE", "Kernel")
                files_indexed += 1

        # Witness events (if present)
        witness_dir = self.agent_core_root / "witness_events"
        if witness_dir.exists():
            for md_file in witness_dir.rglob("*.md"):
                self._index_file(md_file, md_file.read_text(), "WITNESS", "Event")
                files_indexed += 1

        self.conn.commit()
        return files_indexed

    # Back-compat for older tooling.
    def index_nvidia_core(self) -> int:
        return self.index_agent_core()

    def _index_file(self, path: Path, content: str, unit: str, kind: str) -> None:
        if not self.conn:
            raise RuntimeError("DB not initialized. Call init_db() first.")
        cursor = self.conn.cursor()

        metadata = None
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                metadata = parts[1].strip()

        cursor.execute(
            """
            INSERT INTO agent_core_docs (path, content, unit, kind, metadata)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                content=excluded.content,
                unit=excluded.unit,
                kind=excluded.kind,
                metadata=excluded.metadata,
                indexed_at=CURRENT_TIMESTAMP
            """,
            (str(path), content, unit, kind, metadata),
        )

    def query(self, query: str, top_k: int = 5) -> list[dict[str, str | int | float]]:
        if not self.conn:
            raise RuntimeError("DB not initialized. Call init_db() first.")
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT path, unit, kind, rank
            FROM agent_core_docs
            JOIN agent_core_fts ON agent_core_docs.id = agent_core_fts.rowid
            WHERE agent_core_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, top_k),
        )
        results = []
        for row in cursor.fetchall():
            results.append(
                {"path": row[0], "unit": row[1], "kind": row[2], "score": row[3]}
            )
        return results

    # Back-compat name.
    def query_nvidia(self, query: str, top_k: int = 5) -> list[dict[str, str | int | float]]:
        return self.query(query, top_k=top_k)

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None


def main() -> None:
    parser = argparse.ArgumentParser(description="P9 <-> Agent Core bridge")
    parser.add_argument("--index", action="store_true", help="Index local agent_core")
    parser.add_argument("--query", help="Query the local agent_core index")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return")
    parser.add_argument("--db", help="Override sqlite db path")
    parser.add_argument("--root", help="Override agent_core root path")
    args = parser.parse_args()

    bridge = P9AgentCoreBridge(
        agent_core_root=Path(args.root) if args.root else None,
        db_path=Path(args.db) if args.db else None,
    )
    bridge.init_db()

    try:
        if args.index:
            n = bridge.index_agent_core()
            print(f"Indexed {n} files into {bridge.db_path}")
        if args.query:
            results = bridge.query(args.query, top_k=args.top_k)
            for r in results:
                print(f"[{r['unit']}/{r['kind']}] {Path(str(r['path'])).name} (score={r['score']})")
        if not args.index and not args.query:
            parser.print_help()
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
