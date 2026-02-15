#!/usr/bin/env python3
"""
P9 NATS Bridge — Service that responds to memory.search requests via NATS

Usage:
  python3 p9_nats_bridge.py --db /path/to/unified_memory.db
  python3 p9_nats_bridge.py --db unified_memory.db --nats nats://localhost:4222
  python3 p9_nats_bridge.py --node-name agni
  
Environment Variables:
  NATS_URL — NATS server URL (default: nats://localhost:4222)
  NODE_NAME — Node identifier (default: hostname)
  
NATS Subjects:
  {node_name}.memory.search — Search requests
  {node_name}.memory.stats — Statistics requests
  {node_name}.memory.health — Health checks
  
Request Format (search):
  {
    "query": "search terms",
    "top_k": 10,
    "include_snippets": true
  }
  
Response Format:
  {
    "results": [
      {
        "path": "/path/to/file",
        "title": "Document Title",
        "score": 1.5,
        "snippet": "..."
      }
    ],
    "total": 10,
    "node": "agni",
    "duration_ms": 45.2
  }
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

# Try to import nats, provide helpful error if not available
try:
    import nats
    from nats.aio.client import Client as NATS
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False
    print("⚠️  nats-py not installed. Installing: pip install nats-py")
    print("   Or run without NATS for testing:")
    print("   python3 p9_nats_bridge.py --test-mode")

# Import our search module
from p9_search import P9Searcher


class P9NatsBridge:
    def __init__(self, db_path: str, node_name: str, nats_url: str):
        self.db_path = Path(db_path)
        self.node_name = node_name
        self.nats_url = nats_url
        self.searcher = None
        self.nc = None
        self.subscriptions = []
        
    async def connect(self):
        """Connect to NATS and initialize searcher"""
        # Initialize searcher
        print(f"📁 Initializing searcher: {self.db_path}")
        self.searcher = P9Searcher(self.db_path)
        self.searcher.connect()
        
        # Connect to NATS
        print(f"🔗 Connecting to NATS: {self.nats_url}")
        self.nc = await nats.connect(self.nats_url)
        print(f"✓ Connected to NATS as: {self.node_name}")
        
    async def subscribe(self):
        """Subscribe to NATS subjects"""
        # Search endpoint
        sub_search = await self.nc.subscribe(
            f"{self.node_name}.memory.search",
            cb=self.handle_search
        )
        self.subscriptions.append(sub_search)
        print(f"✓ Subscribed: {self.node_name}.memory.search")
        
        # Stats endpoint
        sub_stats = await self.nc.subscribe(
            f"{self.node_name}.memory.stats",
            cb=self.handle_stats
        )
        self.subscriptions.append(sub_stats)
        print(f"✓ Subscribed: {self.node_name}.memory.stats")
        
        # Health endpoint
        sub_health = await self.nc.subscribe(
            f"{self.node_name}.memory.health",
            cb=self.handle_health
        )
        self.subscriptions.append(sub_health)
        print(f"✓ Subscribed: {self.node_name}.memory.health")
        
        # Wildcard for cross-node discovery
        sub_discovery = await self.nc.subscribe(
            "memory.discover",
            cb=self.handle_discovery
        )
        self.subscriptions.append(sub_discovery)
        print(f"✓ Subscribed: memory.discover")
        
    async def handle_search(self, msg):
        """Handle search requests"""
        start_time = time.time()
        
        try:
            # Parse request
            data = json.loads(msg.data.decode())
            query = data.get("query", "")
            top_k = data.get("top_k", 10)
            include_snippets = data.get("include_snippets", True)
            
            if not query:
                response = {"error": "No query provided", "node": self.node_name}
                await msg.respond(json.dumps(response).encode())
                return
                
            # Search
            if include_snippets:
                results = self.searcher.search_with_snippets(query, top_k)
            else:
                results = self.searcher.search(query, top_k)
                
            # Build response
            response = {
                "results": [
                    {
                        "path": r["path"],
                        "title": r["title"],
                        "score": r.get("score", 0),
                        "snippet": r.get("snippet", "") if include_snippets else None
                    }
                    for r in results
                ],
                "total": len(results),
                "node": self.node_name,
                "duration_ms": round((time.time() - start_time) * 1000, 2),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            print(f"🔍 [{self.node_name}] Search: \"{query[:50]}...\" → {len(results)} results")
            
        except Exception as e:
            response = {
                "error": str(e),
                "node": self.node_name,
                "duration_ms": round((time.time() - start_time) * 1000, 2)
            }
            print(f"✗ [{self.node_name}] Search error: {e}")
            
        # Send response
        await msg.respond(json.dumps(response).encode())
        
    async def handle_stats(self, msg):
        """Handle stats requests"""
        try:
            stats = self.searcher.get_stats()
            response = {
                "stats": stats,
                "node": self.node_name,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            response = {"error": str(e), "node": self.node_name}
            
        await msg.respond(json.dumps(response).encode())
        
    async def handle_health(self, msg):
        """Handle health check requests"""
        try:
            # Quick test query
            self.searcher.search("test", top_k=1)
            response = {
                "status": "healthy",
                "node": self.node_name,
                "database": str(self.db_path),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            response = {
                "status": "unhealthy",
                "error": str(e),
                "node": self.node_name
            }
            
        await msg.respond(json.dumps(response).encode())
        
    async def handle_discovery(self, msg):
        """Respond to discovery requests"""
        response = {
            "node": self.node_name,
            "database": str(self.db_path),
            "endpoints": [
                f"{self.node_name}.memory.search",
                f"{self.node_name}.memory.stats",
                f"{self.node_name}.memory.health"
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await msg.respond(json.dumps(response).encode())
        
    async def run(self):
        """Main run loop"""
        print(f"\n🚀 P9 NATS Bridge starting...")
        print(f"   Node: {self.node_name}")
        print(f"   Database: {self.db_path}")
        print(f"   NATS: {self.nats_url}")
        print()
        
        await self.connect()
        await self.subscribe()
        
        print(f"\n✓ Bridge operational. Waiting for requests...")
        print(f"   Example: nats request {self.node_name}.memory.search '{{\"query\": \"test\"}}'")
        print()
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\n👋 Shutting down...")
            
    async def close(self):
        """Cleanup"""
        for sub in self.subscriptions:
            await sub.unsubscribe()
        if self.nc:
            await self.nc.close()
        if self.searcher:
            self.searcher.close()


class TestModeBridge:
    """Test mode without NATS — simulates requests locally"""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.searcher = None
        
    def run(self):
        """Run in test mode"""
        print("🧪 TEST MODE (no NATS)\n")
        
        self.searcher = P9Searcher(self.db_path)
        self.searcher.connect()
        
        print(f"📁 Database: {self.db_path}")
        
        # Test search
        test_queries = [
            "R_V",
            "context engineering",
            "YAML frontmatter"
        ]
        
        for query in test_queries:
            print(f"\n🔍 Test query: \"{query}\"")
            start = time.time()
            results = self.searcher.search_with_snippets(query, top_k=3)
            duration = (time.time() - start) * 1000
            
            print(f"   Results: {len(results)} (took {duration:.1f}ms)")
            for r in results:
                print(f"   - {r['title'][:50]} (score: {r.get('score', 0):.2f})")
                
        print("\n✓ Test mode complete")
        print("  To run with NATS: pip install nats-py")
        print(f"  Then: python3 p9_nats_bridge.py --db {self.db_path}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="P9 NATS Bridge — Expose memory search via NATS"
    )
    parser.add_argument(
        "--db",
        default="unified_memory.db",
        help="Path to unified_memory.db (default: unified_memory.db)"
    )
    parser.add_argument(
        "--nats",
        default=os.environ.get("NATS_URL", "nats://localhost:4222"),
        help="NATS server URL (default: nats://localhost:4222)"
    )
    parser.add_argument(
        "--node-name",
        default=os.environ.get("NODE_NAME", None),
        help="Node identifier (default: hostname)"
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run without NATS for testing"
    )
    
    args = parser.parse_args()
    
    # Determine node name
    node_name = args.node_name
    if not node_name:
        import socket
        node_name = socket.gethostname().split('.')[0]
    
    # Check database exists
    if not Path(args.db).exists():
        print(f"✗ Database not found: {args.db}")
        print(f"  Run: python3 p9_index.py /path/to/workspace --db {args.db}")
        sys.exit(1)
    
    # Run in test mode or with NATS
    if args.test_mode or not NATS_AVAILABLE:
        bridge = TestModeBridge(args.db)
        try:
            bridge.run()
        finally:
            if bridge.searcher:
                bridge.searcher.close()
    else:
        bridge = P9NatsBridge(args.db, node_name, args.nats)
        try:
            asyncio.run(bridge.run())
        finally:
            asyncio.run(bridge.close())


if __name__ == "__main__":
    main()
