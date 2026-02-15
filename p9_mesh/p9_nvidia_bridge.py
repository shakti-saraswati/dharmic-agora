#!/usr/bin/env python3
"""
P9 ↔ NVIDIA Core Bridge
Links yesterday's P9 toolkit to today's NVIDIA self-improving core

What this does:
1. Indexes NVIDIA core docs (49_NODES.md, agents, core/) into P9
2. Enables querying NVIDIA agents via P9 search
3. Bridges YAML frontmatter v2 (NVIDIA) with P9 metadata
4. Makes the 49-node lattice searchable

Usage:
  python3 p9_nvidia_bridge.py --index  # Index NVIDIA core
  python3 p9_nvidia_bridge.py --query "VAJRA flywheel"  # Search NVIDIA docs
"""

import sqlite3
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Paths
NVIDIA_REPO = Path("/Users/dhyana/rushabdev-workspace/nvidia-power-repo")
P9_DB = Path("/Users/dhyana/clawd/nvidia_memory.db")

class P9NvidiaBridge:
    def __init__(self):
        self.conn = None
        
    def init_db(self):
        """Initialize P9 database for NVIDIA core"""
        self.conn = sqlite3.connect(P9_DB)
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nvidia_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                agent_type TEXT,  -- AKASHA, RENKINJUTSU, etc.
                node_category TEXT, -- 49-node category
                metadata TEXT,
                indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS nvidia_fts USING fts5(
                content,
                path,
                content=nvidia_docs,
                content_rowid=id
            )
        """)
        
        self.conn.commit()
        print(f"✓ NVIDIA-P9 bridge DB initialized: {P9_DB}")
        
    def extract_49_node_category(self, content):
        """Extract which 49-node category this doc belongs to"""
        categories = [
            "AI/Swarm Orchestration",
            "Philosophy/Ethics", 
            "Knowledge Management",
            "Manufacturing/Production",
            "Science/Innovation",
            "Society/Culture",
            "Cosmic/Transcendent"
        ]
        for cat in categories:
            if cat.lower() in content.lower():
                return cat
        return "Unknown"
        
    def extract_agent_type(self, file_path):
        """Extract agent type from path"""
        path_str = str(file_path).lower()
        agents = ["akasha", "renkinjutsu", "setu", "vajra", "mmk", "garuda"]
        for agent in agents:
            if agent in path_str:
                return agent.upper()
        return "CORE"  # For core/ docs
        
    def index_nvidia_core(self):
        """Index all NVIDIA core files into P9"""
        print(f"\n🔍 Indexing NVIDIA core: {NVIDIA_REPO}")
        
        files_indexed = 0
        
        # Index 49_NODES.md
        nodes_file = NVIDIA_REPO / "docs" / "49_NODES.md"
        if nodes_file.exists():
            content = nodes_file.read_text()
            self._index_file(nodes_file, content, "49_NODES", "Lattice")
            files_indexed += 1
            print(f"  ✓ Indexed: 49_NODES.md (49-node lattice)")
            
        # Index agent packages
        agents_dir = NVIDIA_REPO / "agents"
        if agents_dir.exists():
            for agent_dir in agents_dir.iterdir():
                if agent_dir.is_dir() and not agent_dir.name.startswith("__"):
                    for py_file in agent_dir.rglob("*.py"):
                        content = py_file.read_text()
                        agent_type = self.extract_agent_type(py_file)
                        self._index_file(py_file, content, agent_type, "Agent")
                        files_indexed += 1
                        if files_indexed % 10 == 0:
                            print(f"  ... {files_indexed} files indexed")
                            
        # Index core/ modules
        core_dir = NVIDIA_REPO / "core"
        if core_dir.exists():
            for py_file in core_dir.rglob("*.py"):
                content = py_file.read_text()
                self._index_file(py_file, content, "CORE", "Kernel")
                files_indexed += 1
                
        # Index witness_events
        witness_dir = NVIDIA_REPO / "witness_events"
        if witness_dir.exists():
            for event_file in witness_dir.rglob("*.md"):
                content = event_file.read_text()
                self._index_file(event_file, content, "WITNESS", "Event")
                files_indexed += 1
                
        self.conn.commit()
        print(f"\n✓ NVIDIA core indexed: {files_indexed} files")
        
    def _index_file(self, path, content, agent_type, node_category):
        """Index a single file"""
        cursor = self.conn.cursor()
        
        # Extract metadata (simple YAML frontmatter extraction)
        metadata = None
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                metadata = parts[1].strip()
                
        cursor.execute("""
            INSERT INTO nvidia_docs (path, content, agent_type, node_category, metadata)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                content=excluded.content,
                agent_type=excluded.agent_type,
                node_category=excluded.node_category,
                metadata=excluded.metadata,
                indexed_at=CURRENT_TIMESTAMP
        """, (str(path), content, agent_type, node_category, metadata))
        
    def query_nvidia(self, query, top_k=5):
        """Query NVIDIA core via P9"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT path, agent_type, node_category, rank
            FROM nvidia_docs
            JOIN nvidia_fts ON nvidia_docs.id = nvidia_fts.rowid
            WHERE nvidia_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, top_k))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "path": row[0],
                "agent": row[1],
                "category": row[2],
                "score": row[3]
            })
        return results
        
    def close(self):
        if self.conn:
            self.conn.close()

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 p9_nvidia_bridge.py --index     # Index NVIDIA core")
        print("  python3 p9_nvidia_bridge.py --query \"VAJRA\"  # Search")
        sys.exit(1)
        
    bridge = P9NvidiaBridge()
    bridge.init_db()
    
    try:
        if sys.argv[1] == "--index":
            bridge.index_nvidia_core()
            print(f"\n✓ Bridge complete: {P9_DB}")
            print("  Query with: python3 p9_search.py \"query\" --db nvidia_memory.db")
            
        elif sys.argv[1] == "--query":
            query = sys.argv[2] if len(sys.argv) > 2 else "test"
            results = bridge.query_nvidia(query)
            print(f"\n🔍 Results for '{query}':")
            for r in results:
                print(f"  [{r['agent']}] {Path(r['path']).name} ({r['category']})")
                
    finally:
        bridge.close()

if __name__ == "__main__":
    main()
