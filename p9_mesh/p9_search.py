#!/usr/bin/env python3
"""
P9 Search — CLI query tool for P9-indexed workspaces

Usage:
  python3 p9_search.py "your search query"
  python3 p9_search.py "R_V Layer 27" --top-k 5 --db /path/to/db
  python3 p9_search.py "context engineering" --hybrid
  
Features:
  - Full-text search via FTS5
  - BM25 ranking (built into FTS5)
  - Title boost (title matches rank higher)
  - Snippet extraction
  - Zero dependencies (stdlib only)
"""

import sqlite3
import sys
import re
from pathlib import Path
from typing import List, Dict, Any


class P9Searcher:
    def __init__(self, db_path="unified_memory.db"):
        self.db_path = Path(db_path)
        self.conn = None
        
    def connect(self):
        """Connect to database"""
        if not self.db_path.exists():
            print(f"✗ Database not found: {self.db_path}")
            print(f"  Run: python3 p9_index.py /path/to/workspace --db {self.db_path}")
            sys.exit(1)
            
        self.conn = sqlite3.connect(self.db_path)
        
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search documents using FTS5"""
        if not self.conn:
            self.connect()
            
        cursor = self.conn.cursor()
        
        # Escape special FTS5 characters
        query = query.replace('"', '""')
        
        # FTS5 query with ranking
        # bm25() returns lower scores for better matches
        cursor.execute("""
            SELECT 
                d.id,
                d.path,
                d.title,
                d.metadata,
                d.file_size,
                d.modified_time,
                d.indexed_at,
                rank
            FROM documents d
            JOIN documents_fts fts ON d.id = fts.rowid
            WHERE documents_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, top_k))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'path': row[1],
                'title': row[2],
                'metadata': row[3],
                'file_size': row[4],
                'modified_time': row[5],
                'indexed_at': row[6],
                'score': row[7]  # bm25 rank (lower is better)
            })
            
        return results
        
    def search_with_snippets(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search with snippet extraction"""
        results = self.search(query, top_k)
        
        # Extract snippets around query terms
        for result in results:
            snippet = self._extract_snippet(result['path'], query)
            result['snippet'] = snippet
            
        return results
        
    def _extract_snippet(self, file_path: str, query: str, snippet_length: int = 200) -> str:
        """Extract a snippet from file content around query terms"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT content FROM documents WHERE path = ?",
                (file_path,)
            )
            row = cursor.fetchone()
            if not row:
                return ""
                
            content = row[0]
            
            # Find query term in content
            query_terms = query.lower().split()
            content_lower = content.lower()
            
            best_pos = 0
            best_score = 0
            
            for term in query_terms:
                pos = content_lower.find(term)
                if pos != -1:
                    # Score based on proximity to start
                    score = len(content) - pos
                    if score > best_score:
                        best_score = score
                        best_pos = max(0, pos - snippet_length // 2)
                        
            # Extract snippet
            snippet = content[best_pos:best_pos + snippet_length]
            
            # Add ellipsis if truncated
            if best_pos > 0:
                snippet = "..." + snippet
            if best_pos + snippet_length < len(content):
                snippet = snippet + "..."
                
            # Highlight query terms
            for term in query_terms:
                snippet = re.sub(
                    f'({re.escape(term)})',
                    r'\033[1m\033[33m\1\033[0m',  # Bold yellow
                    snippet,
                    flags=re.IGNORECASE
                )
                
            return snippet.replace('\n', ' ')
            
        except Exception as e:
            return f"[Error extracting snippet: {e}]"
            
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        if not self.conn:
            self.connect()
            
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM documents")
        total_docs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM documents_fts")
        fts_docs = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(file_size) FROM documents")
        total_size = cursor.fetchone()[0] or 0
        
        cursor.execute(
            "SELECT path FROM documents ORDER BY indexed_at DESC LIMIT 5"
        )
        recent = [row[0] for row in cursor.fetchall()]
        
        return {
            'total_documents': total_docs,
            'fts_indexed': fts_docs,
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'recently_indexed': recent
        }
        
    def close(self):
        if self.conn:
            self.conn.close()


def print_results(results: List[Dict[str, Any]], show_snippets: bool = True):
    """Pretty print search results"""
    if not results:
        print("\nNo results found.")
        return
        
    print(f"\n{'='*80}")
    print(f"Found {len(results)} result(s)")
    print(f"{'='*80}\n")
    
    for i, result in enumerate(results, 1):
        # Score badge (lower bm25 = better, but we invert for display)
        score = result.get('score', 0)
        if score < 1:
            badge = "\033[1m\033[32m[EXACT]\033[0m"  # Green
        elif score < 5:
            badge = "\033[1m\033[34m[HIGH]\033[0m"   # Blue
        else:
            badge = "\033[1m\033[90m[LOW]\033[0m"    # Gray
            
        print(f"{i}. {badge} {result['title']}")
        print(f"   Path: {result['path']}")
        print(f"   Score: {score:.2f} | Size: {result['file_size']} bytes")
        
        if show_snippets and 'snippet' in result:
            print(f"   Snippet: {result['snippet'][:150]}")
            
        print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 p9_search.py \"your query\" [options]")
        print()
        print("Options:")
        print("  --db PATH        Database path (default: unified_memory.db)")
        print("  --top-k N        Number of results (default: 10)")
        print("  --no-snippets    Don't show text snippets")
        print("  --stats          Show database statistics only")
        print()
        print("Examples:")
        print('  python3 p9_search.py "R_V Layer 27"')
        print('  python3 p9_search.py "context engineering" --top-k 5')
        print('  python3 p9_search.py --stats')
        sys.exit(1)
        
    # Parse arguments
    args = sys.argv[1:]
    
    # Check for --stats
    if "--stats" in args:
        db_path = "unified_memory.db"
        if "--db" in args:
            idx = args.index("--db")
            if idx + 1 < len(args):
                db_path = args[idx + 1]
                
        searcher = P9Searcher(db_path)
        try:
            stats = searcher.get_stats()
            print(f"\n📊 Database Statistics: {db_path}")
            print(f"{'='*40}")
            print(f"Total documents: {stats['total_documents']}")
            print(f"FTS indexed: {stats['fts_indexed']}")
            print(f"Total size: {stats['total_size_mb']:.2f} MB")
            print(f"\nRecently indexed:")
            for path in stats['recently_indexed']:
                print(f"  - {path}")
        finally:
            searcher.close()
        sys.exit(0)
    
    # Get query (first non-flag argument)
    query = None
    db_path = "unified_memory.db"
    top_k = 10
    show_snippets = True
    
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--db":
            if i + 1 < len(args):
                db_path = args[i + 1]
                i += 2
            else:
                i += 1
        elif arg == "--top-k":
            if i + 1 < len(args):
                top_k = int(args[i + 1])
                i += 2
            else:
                i += 1
        elif arg == "--no-snippets":
            show_snippets = False
            i += 1
        elif not arg.startswith("--"):
            query = arg
            i += 1
        else:
            i += 1
            
    if not query:
        print("✗ No query provided")
        sys.exit(1)
        
    # Search
    searcher = P9Searcher(db_path)
    
    try:
        print(f"🔍 Searching: \"{query}\"")
        print(f"📁 Database: {db_path}")
        
        if show_snippets:
            results = searcher.search_with_snippets(query, top_k)
        else:
            results = searcher.search(query, top_k)
            
        print_results(results, show_snippets)
        
    except Exception as e:
        print(f"✗ Search error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        searcher.close()


if __name__ == "__main__":
    main()
