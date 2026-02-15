#!/usr/bin/env python3
"""
P9 Cartographer Bridge — PULSE-002
Auto-indexes files from context cartographer inventory

Usage:
  python3 p9_cartographer_bridge.py --scan-local
  python3 p9_cartographer_bridge.py --sync-to-agni
  python3 p9_cartographer_bridge.py --report
"""

import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime

# Paths
P9_DB = Path("p9_memory.db")
CARTOGRAPHER_DIR = Path("../../docs/cartographer")  # Where inventory files live

class CartographerBridge:
    def __init__(self):
        self.conn = None
        
    def init_db(self):
        """Initialize P9 with cartographer-aware schema"""
        self.conn = sqlite3.connect(P9_DB)
        cursor = self.conn.cursor()
        
        # Extended schema with cartographer fields
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cartographer_index (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                content_hash TEXT,
                source_node TEXT,  -- 'mac', 'agni', 'rushabdev'
                file_size INTEGER,
                last_modified TEXT,
                indexed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                sync_status TEXT DEFAULT 'pending'  -- 'pending', 'synced', 'orphan'
            )
        """)
        
        # FTS5 for search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS cartographer_fts USING fts5(
                path,
                content,
                content=cartographer_index,
                content_rowid=id
            )
        """)
        
        self.conn.commit()
        print(f"✓ Cartographer bridge DB initialized: {P9_DB}")
        
    def scan_local_files(self, root_dirs):
        """Scan local directories and build inventory"""
        print(f"\n🔍 Scanning local files...")
        
        inventory = []
        for root_dir in root_dirs:
            root_path = Path(root_dir)
            if not root_path.exists():
                continue
                
            for file_path in root_path.rglob("*.md"):
                try:
                    stat = file_path.stat()
                    content = file_path.read_text()
                    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                    
                    inventory.append({
                        "path": str(file_path),
                        "content_hash": content_hash,
                        "source_node": "mac",
                        "file_size": stat.st_size,
                        "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except Exception as e:
                    print(f"  ⚠️ Error reading {file_path}: {e}")
                    
        print(f"  ✓ Scanned {len(inventory)} files")
        return inventory
        
    def sync_to_p9(self, inventory):
        """Sync inventory to P9 database"""
        cursor = self.conn.cursor()
        
        added = 0
        updated = 0
        
        for item in inventory:
            # Check if exists
            cursor.execute("SELECT content_hash FROM cartographer_index WHERE path = ?", 
                         (item["path"],))
            row = cursor.fetchone()
            
            if row is None:
                # New file
                cursor.execute("""
                    INSERT INTO cartographer_index (path, content_hash, source_node, file_size, last_modified)
                    VALUES (?, ?, ?, ?, ?)
                """, (item["path"], item["content_hash"], item["source_node"],
                      item["file_size"], item["last_modified"]))
                added += 1
            elif row[0] != item["content_hash"]:
                # Updated file
                cursor.execute("""
                    UPDATE cartographer_index 
                    SET content_hash = ?, file_size = ?, last_modified = ?, sync_status = 'pending'
                    WHERE path = ?
                """, (item["content_hash"], item["file_size"], item["last_modified"], item["path"]))
                updated += 1
                
        self.conn.commit()
        print(f"  ✓ Synced: {added} added, {updated} updated")
        
    def report_orphans(self):
        """Report files that exist only on one node"""
        cursor = self.conn.cursor()
        
        # Find files only on mac
        cursor.execute("""
            SELECT path, source_node FROM cartographer_index
            WHERE source_node = 'mac'
            AND path NOT IN (SELECT path FROM cartographer_index WHERE source_node != 'mac')
        """)
        mac_only = cursor.fetchall()
        
        print(f"\n🚨 ORPHAN REPORT:")
        print(f"  Mac-only files: {len(mac_only)}")
        for path, _ in mac_only[:5]:  # Show first 5
            print(f"    • {path}")
            
        return mac_only
        
    def generate_sync_request(self, orphans):
        """Generate JSON request for AGNI to sync missing files"""
        request = {
            "pulse": "002",
            "timestamp": datetime.now().isoformat(),
            "request_type": "orphan_sync",
            "files_needed": [path for path, _ in orphans]
        }
        
        output_path = Path("sync_request_002.json")
        with open(output_path, 'w') as f:
            json.dump(request, f, indent=2)
            
        print(f"\n📤 Sync request written: {output_path}")
        return output_path
        
    def close(self):
        if self.conn:
            self.conn.close()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="P9 Cartographer Bridge")
    parser.add_argument("--scan-local", action="store_true", help="Scan local files")
    parser.add_argument("--sync-to-agni", action="store_true", help="Request sync to AGNI")
    parser.add_argument("--report", action="store_true", help="Generate orphan report")
    
    args = parser.parse_args()
    
    bridge = CartographerBridge()
    bridge.init_db()
    
    try:
        if args.scan_local:
            # Scan key directories (expand ~ to home)
            from pathlib import Path
            roots = [
                Path.home() / "trishula/shared",
                Path.home() / "clawd/memory",
                Path.home() / "clawd/docs",
                "../nvidia_core/docs"  # Relative to p9_mesh/
            ]
            inventory = bridge.scan_local_files(roots)
            bridge.sync_to_p9(inventory)
            
        if args.report or args.sync_to_agni:
            orphans = bridge.report_orphans()
            if args.sync_to_agni and orphans:
                bridge.generate_sync_request(orphans)
                
    finally:
        bridge.close()

if __name__ == "__main__":
    main()
