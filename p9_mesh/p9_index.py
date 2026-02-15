#!/usr/bin/env python3
"""
P9 Indexer — Standalone workspace indexer for AGNI VPS
Creates SQLite + FTS5 index of all markdown/code files

Usage:
  python3 p9_index.py /path/to/workspace [--db /path/to/unified_memory.db]
  
Output:
  unified_memory.db (SQLite with FTS5 full-text search)
  
Features:
  - Incremental updates (SHA-256 change detection)
  - FTS5 for fast full-text search
  - YAML frontmatter extraction
  - Zero dependencies (stdlib only)
"""

import sqlite3
import hashlib
import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

# File types to index
INDEXABLE_EXTENSIONS = {
    '.md', '.txt', '.py', '.js', '.ts', '.json', '.yaml', '.yml',
    '.rs', '.go', '.java', '.cpp', '.c', '.h', '.sh', '.sql'
}

# Directories to skip
SKIP_DIRS = {'.git', '__pycache__', '.venv', 'node_modules', '.pytest_cache', 'dist', 'build'}

class P9Indexer:
    def __init__(self, workspace_path, db_path="unified_memory.db"):
        self.workspace = Path(workspace_path).resolve()
        self.db_path = Path(db_path)
        self.conn = None
        
    def init_database(self):
        """Create SQLite schema with FTS5"""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()
        
        # Main documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                content_hash TEXT NOT NULL,
                content TEXT NOT NULL,
                title TEXT,
                metadata TEXT,
                file_size INTEGER,
                modified_time TEXT,
                indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # FTS5 virtual table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                content,
                title,
                path,
                content=documents,
                content_rowid=id
            )
        """)
        
        # Triggers to keep FTS index in sync
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_insert AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, content, title, path)
                VALUES (new.id, new.content, new.title, new.path);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_delete AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, content, title, path)
                VALUES ('delete', old.id, old.content, old.title, old.path);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_update AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, content, title, path)
                VALUES ('delete', old.id, old.content, old.title, old.path);
                INSERT INTO documents_fts(rowid, content, title, path)
                VALUES (new.id, new.content, new.title, new.path);
            END
        """)
        
        # Index for faster path lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path)
        """)
        
        self.conn.commit()
        print(f"✓ Database initialized: {self.db_path}")
        
    def compute_hash(self, content):
        """Compute SHA-256 hash of content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
        
    def extract_frontmatter(self, content):
        """Extract YAML frontmatter from markdown files"""
        if not content.startswith('---'):
            return None, content
            
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                # Simple frontmatter extraction (not full YAML parsing)
                frontmatter = parts[1].strip()
                body = parts[2].strip()
                return frontmatter, body
            except:
                pass
        return None, content
        
    def extract_title(self, content):
        """Extract title from content (first # heading or first line)"""
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()
            if line.startswith('## '):
                return line[3:].strip()
        # Fallback: first non-empty line
        for line in lines:
            if line.strip():
                return line.strip()[:100]
        return "Untitled"
        
    def index_file(self, file_path):
        """Index a single file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            print(f"  ✗ Error reading {file_path}: {e}")
            return False
            
        # Compute hash
        content_hash = self.compute_hash(content)
        
        # Check if already indexed and unchanged
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT content_hash FROM documents WHERE path = ?",
            (str(file_path),)
        )
        row = cursor.fetchone()
        if row and row[0] == content_hash:
            return False  # Unchanged, skip
            
        # Extract metadata
        frontmatter, body = self.extract_frontmatter(content)
        title = self.extract_title(content)
        
        # Get file stats
        stat = file_path.stat()
        
        # Insert or update
        cursor.execute("""
            INSERT INTO documents (path, content_hash, content, title, metadata, file_size, modified_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                content_hash=excluded.content_hash,
                content=excluded.content,
                title=excluded.title,
                metadata=excluded.metadata,
                file_size=excluded.file_size,
                modified_time=excluded.modified_time,
                indexed_at=CURRENT_TIMESTAMP
        """, (
            str(file_path),
            content_hash,
            content,
            title,
            frontmatter,
            stat.st_size,
            datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        ))
        
        self.conn.commit()
        return True
        
    def walk_workspace(self):
        """Walk workspace and index all files"""
        indexed = 0
        updated = 0
        skipped = 0
        errors = 0
        
        print(f"\n🔍 Indexing: {self.workspace}")
        print(f"📁 Database: {self.db_path}")
        print()
        
        for root, dirs, files in os.walk(self.workspace):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
            
            for filename in files:
                ext = Path(filename).suffix.lower()
                if ext not in INDEXABLE_EXTENSIONS:
                    skipped += 1
                    continue
                    
                file_path = Path(root) / filename
                
                try:
                    was_updated = self.index_file(file_path)
                    if was_updated:
                        if indexed == 0:
                            print(f"  ✓ {file_path.relative_to(self.workspace)}")
                        updated += 1
                    indexed += 1
                    
                    # Progress indicator every 100 files
                    if indexed % 100 == 0:
                        print(f"  ... {indexed} files processed")
                        
                except Exception as e:
                    print(f"  ✗ {file_path}: {e}")
                    errors += 1
                    
        print(f"\n✓ Indexing complete:")
        print(f"  Total indexed: {indexed}")
        print(f"  Updated: {updated}")
        print(f"  Skipped (wrong type): {skipped}")
        print(f"  Errors: {errors}")
        
        # Print stats
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        total_docs = cursor.fetchone()[0]
        print(f"  Database total: {total_docs} documents")
        
    def cleanup_deleted(self):
        """Remove entries for files that no longer exist"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT path FROM documents")
        to_delete = []
        
        for (path,) in cursor.fetchall():
            if not Path(path).exists():
                to_delete.append(path)
                
        for path in to_delete:
            cursor.execute("DELETE FROM documents WHERE path = ?", (path,))
            
        self.conn.commit()
        print(f"\n🧹 Cleaned up {len(to_delete)} deleted files")
        
    def close(self):
        if self.conn:
            self.conn.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 p9_index.py /path/to/workspace [--db /path/to/db]")
        print("Example: python3 p9_index.py /home/openclaw/workspace --db unified_memory.db")
        sys.exit(1)
        
    workspace = sys.argv[1]
    db_path = "unified_memory.db"
    
    # Parse optional --db argument
    if "--db" in sys.argv:
        db_idx = sys.argv.index("--db")
        if db_idx + 1 < len(sys.argv):
            db_path = sys.argv[db_idx + 1]
    
    if not Path(workspace).exists():
        print(f"✗ Workspace not found: {workspace}")
        sys.exit(1)
        
    indexer = P9Indexer(workspace, db_path)
    
    try:
        indexer.init_database()
        indexer.walk_workspace()
        indexer.cleanup_deleted()
    finally:
        indexer.close()
        
    print(f"\n✓ Database ready: {db_path}")
    print(f"  Query with: python3 p9_search.py \"your query\" --db {db_path}")


if __name__ == "__main__":
    main()
