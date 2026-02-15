#!/usr/bin/env python3
"""
Unified Query — PULSE-002
Search Mac + AGNI + RUSHAB in one command

Usage:
  python3 unified_query.py "crewai delegation"
  python3 unified_query.py --node agni "temporal workflow"
  python3 unified_query.py --all "reputation"
"""

import sqlite3
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class SearchResult:
    path: str
    source_node: str
    score: float
    excerpt: Optional[str] = None

class UnifiedQuery:
    """Query across all nodes in the mesh"""
    
    def __init__(self):
        self.local_db = Path("p9_memory.db")
        self.agni_nats_subject = "agni.memory.search"
        self.rushab_nats_subject = "rushabdev.memory.search"
        
    def query_local(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Query Mac's P9 database"""
        if not self.local_db.exists():
            return []
            
        conn = sqlite3.connect(self.local_db)
        cursor = conn.cursor()
        
        try:
            # BM25 search via FTS5
            cursor.execute("""
                SELECT path, rank
                FROM cartographer_index
                JOIN cartographer_fts ON cartographer_index.id = cartographer_fts.rowid
                WHERE cartographer_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query, top_k))
            
            results = []
            for row in cursor.fetchall():
                results.append(SearchResult(
                    path=row[0],
                    source_node="mac",
                    score=row[1]
                ))
            return results
        except Exception as e:
            print(f"Local query error: {e}")
            return []
        finally:
            conn.close()
            
    def query_agni(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Query AGNI via NATS"""
        try:
            # Use nats CLI if available
            result = subprocess.run([
                "nats", "request", self.agni_nats_subject,
                json.dumps({"query": query, "top_k": top_k}),
                "--timeout", "2s"
            ], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return [SearchResult(
                    path=r["path"],
                    source_node="agni",
                    score=r.get("score", 0.0)
                ) for r in data.get("results", [])]
        except Exception as e:
            print(f"AGNI query error: {e}")
            
        return []
        
    def query_rushab(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Query RUSHABDEV via NATS"""
        # Similar to AGNI but different subject
        # TODO: Implement when RUSHAB bridge is live
        return []
        
    def unified_search(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """Search all nodes and merge results"""
        print(f"🔍 Unified search: '{query}'")
        
        # Query all nodes
        mac_results = self.query_local(query, top_k=5)
        print(f"  Mac: {len(mac_results)} results")
        
        agni_results = self.query_agni(query, top_k=5)
        print(f"  AGNI: {len(agni_results)} results")
        
        rushab_results = self.query_rushab(query, top_k=5)
        print(f"  RUSHAB: {len(rushab_results)} results")
        
        # Merge and rerank (simple merge for now)
        all_results = mac_results + agni_results + rushab_results
        
        # Sort by score (lower is better for BM25 rank)
        all_results.sort(key=lambda x: x.score)
        
        return all_results[:top_k]
        
    def print_results(self, results: List[SearchResult]):
        """Pretty print search results"""
        if not results:
            print("\n❌ No results found")
            return
            
        print(f"\n✓ {len(results)} results:")
        print("-" * 70)
        
        for i, r in enumerate(results, 1):
            node_emoji = {"mac": "🖥️", "agni": "☁️", "rushabdev": "🚀"}.get(r.source_node, "📄")
            print(f"{i}. {node_emoji} [{r.source_node:10}] {Path(r.path).name}")
            print(f"   Score: {r.score:.4f}")
            print(f"   Path: {r.path}")
            print()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Unified Query across all nodes")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--node", choices=["mac", "agni", "rushab", "all"], 
                       default="all", help="Which node to query")
    parser.add_argument("--top-k", type=int, default=10, help="Number of results")
    
    args = parser.parse_args()
    
    querier = UnifiedQuery()
    
    if args.node == "mac":
        results = querier.query_local(args.query, args.top_k)
    elif args.node == "agni":
        results = querier.query_agni(args.query, args.top_k)
    elif args.node == "rushab":
        results = querier.query_rushab(args.query, args.top_k)
    else:
        results = querier.unified_search(args.query, args.top_k)
        
    querier.print_results(results)

if __name__ == "__main__":
    main()
