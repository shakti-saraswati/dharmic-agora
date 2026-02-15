#!/usr/bin/env python3
"""
P9 Semantic Search — Embedding-based semantic search for P9

Usage:
  python3 p9_semantic.py index --db /path/to/db          # Index documents with embeddings
  python3 p9_semantic.py search "query" --db /path/to/db # Semantic search
  python3 p9_semantic.py hybrid "query" --db /path/to/db # Hybrid FTS5 + semantic
  python3 p9_semantic.py stats --db /path/to/db          # Show vector stats

Features:
  - Sentence-transformers embeddings (all-MiniLM-L6-v2, 384-dim)
  - sqlite-vec for vector storage and similarity search
  - Hybrid search combining FTS5 + semantic similarity
  - Incremental indexing (only changed documents)
"""

import sqlite3
import sys
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import argparse

# Embedding model configuration
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


class SemanticIndexer:
    """Handles embedding generation and vector indexing"""
    
    def __init__(self, db_path: str = "unified_memory.db"):
        self.db_path = Path(db_path)
        self.conn = None
        self.model = None
        
    def connect(self):
        """Connect to database and ensure sqlite-vec is loaded"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.enable_load_extension(True)
        
        # Try to load sqlite-vec extension
        try:
            self.conn.execute("SELECT load_extension('vec0')")
        except sqlite3.OperationalError:
            try:
                # Try common paths
                import os
                possible_paths = [
                    "/usr/local/lib/vec0.dylib",
                    "/opt/homebrew/lib/vec0.dylib",
                    "/usr/lib/vec0.so",
                    "./vec0.dylib",
                    "./vec0.so",
                ]
                for path in possible_paths:
                    if Path(path).exists():
                        self.conn.execute(f"SELECT load_extension('{path}')")
                        break
                else:
                    # Try pip-installed version
                    try:
                        import sqlite_vec
                        sqlite_vec.load(self.conn)
                    except ImportError:
                        pass
            except Exception as e:
                print(f"⚠️  sqlite-vec extension not found: {e}")
                print("   Install with: pip install sqlite-vec")
                raise
                
        # Verify vec0 is loaded
        try:
            self.conn.execute("SELECT vec_version()")
        except sqlite3.OperationalError:
            raise RuntimeError("sqlite-vec extension failed to load")
            
    def init_vector_schema(self):
        """Add vector table to existing P9 database"""
        cursor = self.conn.cursor()
        
        # Virtual table for vector storage
        cursor.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS document_vectors USING vec0(
                document_id INTEGER PRIMARY KEY,
                embedding float[{EMBEDDING_DIM}] distance_metric=cosine
            )
        """)
        
        # Metadata table for indexing status
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vector_index_status (
                document_id INTEGER PRIMARY KEY,
                content_hash TEXT NOT NULL,
                indexed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)
        
        self.conn.commit()
        print(f"✓ Vector schema initialized (dim={EMBEDDING_DIM})")
        
    def load_model(self):
        """Lazy load the embedding model"""
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
                print(f"🔄 Loading embedding model: {EMBEDDING_MODEL}...")
                self.model = SentenceTransformer(EMBEDDING_MODEL)
                print(f"✓ Model loaded")
            except ImportError:
                print("✗ sentence-transformers not installed")
                print("   Install with: pip install sentence-transformers")
                raise
                
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text"""
        self.load_model()
        
        # Truncate very long texts (model limit ~512 tokens)
        # Rough approximation: 4 chars per token
        max_chars = 2000
        if len(text) > max_chars:
            text = text[:max_chars]
            
        embedding = self.model.encode(text, convert_to_numpy=True, show_progress_bar=False)
        return embedding.tolist()
        
    def index_document(self, doc_id: int, content: str, content_hash: str) -> bool:
        """Index a single document with vector embedding"""
        cursor = self.conn.cursor()
        
        # Check if already indexed with same hash
        cursor.execute(
            "SELECT content_hash FROM vector_index_status WHERE document_id = ?",
            (doc_id,)
        )
        row = cursor.fetchone()
        if row and row[0] == content_hash:
            return False  # Already indexed, unchanged
            
        # Generate embedding
        try:
            embedding = self.generate_embedding(content)
        except Exception as e:
            print(f"   ✗ Embedding failed for doc {doc_id}: {e}")
            return False
            
        # Convert to JSON array for sqlite-vec
        embedding_json = json.dumps(embedding)
        
        # Insert or replace vector
        cursor.execute("""
            INSERT OR REPLACE INTO document_vectors (document_id, embedding)
            VALUES (?, ?)
        """, (doc_id, embedding_json))
        
        # Update status
        cursor.execute("""
            INSERT OR REPLACE INTO vector_index_status (document_id, content_hash, indexed_at)
            VALUES (?, ?, datetime('now'))
        """, (doc_id, content_hash))
        
        self.conn.commit()
        return True
        
    def index_all(self, batch_size: int = 32):
        """Index all documents that don't have vectors yet"""
        cursor = self.conn.cursor()
        
        # Get all documents without vectors or with changed content
        cursor.execute("""
            SELECT d.id, d.content, d.content_hash, d.path
            FROM documents d
            LEFT JOIN vector_index_status vis ON d.id = vis.document_id
            WHERE vis.document_id IS NULL OR vis.content_hash != d.content_hash
        """)
        
        to_index = cursor.fetchall()
        
        if not to_index:
            print("✓ All documents already vector-indexed")
            return
            
        print(f"🔄 Indexing {len(to_index)} documents with embeddings...")
        
        indexed = 0
        errors = 0
        
        for doc_id, content, content_hash, path in to_index:
            try:
                if self.index_document(doc_id, content, content_hash):
                    indexed += 1
                    if indexed % 10 == 0:
                        print(f"   ... {indexed} documents indexed")
            except Exception as e:
                print(f"   ✗ Error indexing {path}: {e}")
                errors += 1
                
        print(f"✓ Indexing complete: {indexed} indexed, {errors} errors")
        
    def get_stats(self) -> Dict[str, Any]:
        """Get vector index statistics"""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM document_vectors")
        vector_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM documents")
        total_docs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM vector_index_status")
        indexed_count = cursor.fetchone()[0]
        
        return {
            'total_documents': total_docs,
            'vector_indexed': vector_count,
            'index_status_entries': indexed_count,
            'coverage_pct': (vector_count / total_docs * 100) if total_docs > 0 else 0
        }
        
    def close(self):
        if self.conn:
            self.conn.close()


class SemanticSearcher:
    """Handles semantic and hybrid search"""
    
    def __init__(self, db_path: str = "unified_memory.db"):
        self.db_path = Path(db_path)
        self.conn = None
        self.model = None
        
    def connect(self):
        """Connect to database with sqlite-vec loaded"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.enable_load_extension(True)
        
        # Load sqlite-vec (try multiple methods)
        try:
            self.conn.execute("SELECT load_extension('vec0')")
        except sqlite3.OperationalError:
            try:
                import sqlite_vec
                sqlite_vec.load(self.conn)
            except:
                # Try explicit paths
                import platform
                system = platform.system()
                ext = "dylib" if system == "Darwin" else "so"
                paths = [
                    f"/opt/homebrew/lib/vec0.{ext}",
                    f"/usr/local/lib/vec0.{ext}",
                    f"./vec0.{ext}",
                ]
                for path in paths:
                    if Path(path).exists():
                        self.conn.execute(f"SELECT load_extension('{path}')")
                        break
                        
    def load_model(self):
        """Lazy load the embedding model"""
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(EMBEDDING_MODEL)
            
    def search(
        self, 
        query: str, 
        top_k: int = 10,
        min_similarity: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Pure semantic search using cosine similarity"""
        self.load_model()
        
        # Generate query embedding
        query_embedding = self.model.encode(query, convert_to_numpy=True)
        query_json = json.dumps(query_embedding.tolist())
        
        cursor = self.conn.cursor()
        
        # sqlite-vec cosine similarity search
        # vec_distance_cosine returns distance (0 = identical, 2 = opposite)
        # Convert to similarity: 1 - distance/2
        cursor.execute("""
            SELECT 
                d.id,
                d.path,
                d.title,
                d.metadata,
                d.file_size,
                d.modified_time,
                vec_distance_cosine(dv.embedding, ?) as distance
            FROM document_vectors dv
            JOIN documents d ON dv.document_id = d.id
            ORDER BY distance
            LIMIT ?
        """, (query_json, top_k * 2))  # Get extra for filtering
        
        results = []
        for row in cursor.fetchall():
            distance = row[6]
            similarity = 1 - (distance / 2)  # Convert distance to similarity
            
            if similarity >= min_similarity:
                results.append({
                    'id': row[0],
                    'path': row[1],
                    'title': row[2],
                    'metadata': row[3],
                    'file_size': row[4],
                    'modified_time': row[5],
                    'similarity': similarity,
                    'score_type': 'semantic'
                })
                
        return results[:top_k]
        
    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        semantic_weight: float = 0.7,
        fts_weight: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Hybrid search combining FTS5 and semantic similarity"""
        self.load_model()
        
        # Get semantic results
        semantic_results = self.search(query, top_k=top_k * 2, min_similarity=0.1)
        semantic_dict = {r['id']: r for r in semantic_results}
        
        # Get FTS5 results
        query_escaped = query.replace('"', '""')
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    d.id,
                    d.path,
                    d.title,
                    rank
                FROM documents d
                JOIN documents_fts fts ON d.id = fts.rowid
                WHERE documents_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query_escaped, top_k * 2))
            
            fts_results = []
            for row in cursor.fetchall():
                # Convert BM25 rank to score (lower rank = better, normalize)
                # BM25 rank is negative log of probability, typically -10 to 0
                rank = row[3] if row[3] else 0
                # Normalize to 0-1 (approximate)
                fts_score = max(0, min(1, 1 - (abs(rank) / 10)))
                
                fts_results.append({
                    'id': row[0],
                    'path': row[1],
                    'title': row[2],
                    'fts_score': fts_score
                })
                
        except Exception as e:
            print(f"⚠️  FTS search error: {e}")
            fts_results = []
            
        # Combine results
        all_ids = set(semantic_dict.keys())
        for r in fts_results:
            all_ids.add(r['id'])
            
        combined = []
        for doc_id in all_ids:
            sem_score = semantic_dict.get(doc_id, {}).get('similarity', 0)
            fts_score = next((r['fts_score'] for r in fts_results if r['id'] == doc_id), 0)
            
            # Weighted combination
            combined_score = (semantic_weight * sem_score) + (fts_weight * fts_score)
            
            # Get document details from semantic result or fetch
            if doc_id in semantic_dict:
                doc = semantic_dict[doc_id].copy()
            else:
                cursor.execute(
                    "SELECT id, path, title, metadata, file_size, modified_time FROM documents WHERE id = ?",
                    (doc_id,)
                )
                row = cursor.fetchone()
                if not row:
                    continue
                doc = {
                    'id': row[0],
                    'path': row[1],
                    'title': row[2],
                    'metadata': row[3],
                    'file_size': row[4],
                    'modified_time': row[5],
                    'similarity': 0
                }
                
            doc['hybrid_score'] = combined_score
            doc['semantic_score'] = sem_score
            doc['fts_score'] = fts_score
            doc['score_type'] = 'hybrid'
            combined.append(doc)
            
        # Sort by hybrid score descending
        combined.sort(key=lambda x: x['hybrid_score'], reverse=True)
        return combined[:top_k]
        
    def close(self):
        if self.conn:
            self.conn.close()


def print_results(results: List[Dict[str, Any]], show_scores: bool = True):
    """Pretty print search results"""
    if not results:
        print("\nNo results found.")
        return
        
    print(f"\n{'='*80}")
    print(f"Found {len(results)} result(s)")
    print(f"{'='*80}\n")
    
    for i, result in enumerate(results, 1):
        # Score badge based on similarity/score
        if 'similarity' in result and result['similarity'] > 0.8:
            badge = "\033[1m\033[32m[EXACT]\033[0m"
        elif 'similarity' in result and result['similarity'] > 0.6:
            badge = "\033[1m\033[34m[HIGH]\033[0m"
        elif 'hybrid_score' in result and result['hybrid_score'] > 0.5:
            badge = "\033[1m\033[36m[HYBRID]\033[0m"
        else:
            badge = "\033[1m\033[90m[OK]\033[0m"
            
        print(f"{i}. {badge} {result['title']}")
        print(f"   Path: {result['path']}")
        
        if show_scores:
            if 'similarity' in result:
                print(f"   Similarity: {result['similarity']:.3f}")
            if 'hybrid_score' in result:
                print(f"   Hybrid: {result['hybrid_score']:.3f} (sem: {result.get('semantic_score', 0):.3f}, fts: {result.get('fts_score', 0):.3f})")
                
        print()


def main():
    parser = argparse.ArgumentParser(
        description="P9 Semantic Search — Embedding-based document search"
    )
    parser.add_argument(
        "--db",
        default="unified_memory.db",
        help="Database path (default: unified_memory.db)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Index command
    index_parser = subparsers.add_parser("index", help="Index documents with embeddings")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Semantic search")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--top-k", type=int, default=10, help="Number of results")
    search_parser.add_argument("--min-sim", type=float, default=0.3, help="Minimum similarity")
    
    # Hybrid command
    hybrid_parser = subparsers.add_parser("hybrid", help="Hybrid FTS5 + semantic search")
    hybrid_parser.add_argument("query", help="Search query")
    hybrid_parser.add_argument("--top-k", type=int, default=10, help="Number of results")
    hybrid_parser.add_argument("--sem-weight", type=float, default=0.7, help="Semantic weight")
    hybrid_parser.add_argument("--fts-weight", type=float, default=0.3, help="FTS weight")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show vector index statistics")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    if args.command == "index":
        indexer = SemanticIndexer(args.db)
        try:
            indexer.connect()
            indexer.init_vector_schema()
            indexer.index_all()
            stats = indexer.get_stats()
            print(f"\n📊 Index coverage: {stats['coverage_pct']:.1f}% ({stats['vector_indexed']}/{stats['total_documents']})")
        except Exception as e:
            print(f"✗ Indexing failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            indexer.close()
            
    elif args.command == "search":
        searcher = SemanticSearcher(args.db)
        try:
            searcher.connect()
            print(f"🔍 Semantic search: \"{args.query}\"")
            results = searcher.search(args.query, top_k=args.top_k, min_similarity=args.min_sim)
            print_results(results)
        except Exception as e:
            print(f"✗ Search failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            searcher.close()
            
    elif args.command == "hybrid":
        searcher = SemanticSearcher(args.db)
        try:
            searcher.connect()
            print(f"🔍 Hybrid search: \"{args.query}\"")
            print(f"   Weights: semantic={args.sem_weight}, fts={args.fts_weight}")
            results = searcher.hybrid_search(
                args.query,
                top_k=args.top_k,
                semantic_weight=args.sem_weight,
                fts_weight=args.fts_weight
            )
            print_results(results)
        except Exception as e:
            print(f"✗ Search failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            searcher.close()
            
    elif args.command == "stats":
        indexer = SemanticIndexer(args.db)
        try:
            indexer.connect()
            stats = indexer.get_stats()
            print(f"\n📊 Vector Index Statistics: {args.db}")
            print(f"{'='*40}")
            print(f"Total documents: {stats['total_documents']}")
            print(f"Vector indexed: {stats['vector_indexed']}")
            print(f"Coverage: {stats['coverage_pct']:.1f}%")
        finally:
            indexer.close()


if __name__ == "__main__":
    main()
