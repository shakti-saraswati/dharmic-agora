#!/usr/bin/env python3
"""
P9 Schema Migration — Bridge cartographer_index to documents table for semantic search

This migration:
1. Adds content column to cartographer_index
2. Creates documents table matching p9_semantic.py expectations
3. Migrates existing data
4. Rebuilds FTS5 index
"""

import sqlite3
import sys
from pathlib import Path

try:
    from agora.db_config import DB_PATHS
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from agora.db_config import DB_PATHS


def migrate(db_path: str):
    """Migrate P9 database to support semantic search"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"🔧 Migrating: {db_path}")
    
    # Step 1: Check if documents table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents'")
    if cursor.fetchone():
        print("  ✓ documents table already exists")
    else:
        print("  📝 Creating documents table...")
        cursor.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                content TEXT,
                content_hash TEXT,
                title TEXT,
                metadata TEXT,
                file_size INTEGER,
                modified_time TEXT
            )
        """)
        print("  ✓ documents table created")
    
    # Step 2: Add content column to cartographer_index if missing
    cursor.execute("PRAGMA table_info(cartographer_index)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'content' not in columns:
        print("  📝 Adding content column to cartographer_index...")
        cursor.execute("ALTER TABLE cartographer_index ADD COLUMN content TEXT")
        print("  ✓ content column added")
    else:
        print("  ✓ content column already exists")
    
    # Step 3: Create documents_fts if missing (for p9_semantic.py compatibility)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documents_fts'")
    if not cursor.fetchone():
        print("  📝 Creating documents_fts virtual table...")
        cursor.execute("""
            CREATE VIRTUAL TABLE documents_fts USING fts5(
                path,
                content,
                content=documents,
                content_rowid=id
            )
        """)
        print("  ✓ documents_fts created")
    
    # Step 4: Migrate data from cartographer_index to documents
    print("  🔄 Migrating data to documents table...")
    cursor.execute("""
        SELECT ci.id, ci.path, ci.content, ci.content_hash, ci.file_size, ci.last_modified
        FROM cartographer_index ci
        LEFT JOIN documents d ON ci.path = d.path
        WHERE d.id IS NULL
    """)
    
    migrated = 0
    for row in cursor.fetchall():
        doc_id, path, content, content_hash, file_size, modified_time = row
        
        # Extract title from path
        title = Path(path).stem.replace('_', ' ').replace('-', ' ')
        
        cursor.execute("""
            INSERT OR REPLACE INTO documents (id, path, content, content_hash, title, file_size, modified_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (doc_id, path, content, content_hash, title, file_size, modified_time))
        migrated += 1
    
    conn.commit()
    print(f"  ✓ Migrated {migrated} documents")
    
    # Step 5: Rebuild FTS index
    print("  🔄 Rebuilding FTS index...")
    cursor.execute("INSERT INTO documents_fts(documents_fts) VALUES('rebuild')")
    conn.commit()
    print("  ✓ FTS index rebuilt")
    
    # Step 6: Create vector_index_status table for semantic search
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vector_index_status'")
    if not cursor.fetchone():
        print("  📝 Creating vector_index_status table...")
        cursor.execute("""
            CREATE TABLE vector_index_status (
                document_id INTEGER PRIMARY KEY,
                content_hash TEXT NOT NULL,
                indexed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)
        print("  ✓ vector_index_status created")
    
    # Step 7: Create document_vectors virtual table for sqlite-vec
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='document_vectors'")
    if not cursor.fetchone():
        print("  📝 Creating document_vectors virtual table...")
        try:
            cursor.execute("""
                CREATE VIRTUAL TABLE document_vectors USING vec0(
                    document_id INTEGER PRIMARY KEY,
                    embedding float[384]
                )
            """)
            print("  ✓ document_vectors created")
        except sqlite3.OperationalError as e:
            print(f"  ⚠️ Could not create document_vectors (sqlite-vec may not be available): {e}")
    
    conn.close()
    print(f"\n✅ Migration complete: {db_path}")
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate P9 database schema")
    parser.add_argument("--db", default=str(DB_PATHS["p9_memory"]), help="Database path")
    
    args = parser.parse_args()
    
    if not Path(args.db).exists():
        print(f"❌ Database not found: {args.db}")
        sys.exit(1)
    
    success = migrate(args.db)
    sys.exit(0 if success else 1)
