#!/usr/bin/env python3
"""
Kaizen Integration Module
Wires kaizen_hooks.py into the dharmic-agora system

Usage:
  from kaizen_integration import KaizenTracker
  
  tracker = KaizenTracker()
  tracker.track_access("docs/KEYSTONES_72H.md", agent="DC")
  
Or as middleware in FastAPI:
  @app.middleware("http")
  async def kaizen_middleware(request, call_next):
      response = await call_next(request)
      KaizenTracker().track_access_from_request(request)
      return response
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add kaizen to path
sys.path.insert(0, str(Path(__file__).parent.parent / "kaizen"))

from kaizen_hooks import KaizenHooks, on_file_read, on_file_write

class KaizenTracker:
    """Production-grade Kaizen tracking for dharmic-agora"""
    
    def __init__(self, project_root=None):
        self.project_root = Path(project_root) if project_root else Path(__file__).parent.parent
        
    def track_access(self, filepath, agent="system", action="read"):
        """Track file access with Kaizen hooks"""
        full_path = self.project_root / filepath
        
        if not full_path.exists():
            return None
            
        try:
            if action == "read":
                return on_file_read(str(full_path), agent)
            else:
                return on_file_write(str(full_path), agent)
        except Exception as e:
            print(f"Kaizen tracking error: {e}")
            return None
            
    def get_trending(self, min_uses=10, top_n=5):
        """Get trending files by use_count"""
        trending = []
        
        for md_file in self.project_root.rglob("*.md"):
            try:
                yaml_text, _ = KaizenHooks.read_yaml_frontmatter(str(md_file))
                if yaml_text:
                    data = KaizenHooks.parse_yaml_simple(yaml_text)
                    use_count = data.get("use_count", 0)
                    if use_count >= min_uses:
                        trending.append({
                            "path": str(md_file.relative_to(self.project_root)),
                            "uses": use_count,
                            "grade": data.get("quality_grade", "C")
                        })
            except:
                continue
                
        trending.sort(key=lambda x: x["uses"], reverse=True)
        return trending[:top_n]
        
    def get_archive_candidates(self, days=90):
        """Get files unused for N days"""
        candidates = []
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        
        for md_file in self.project_root.rglob("*.md"):
            try:
                yaml_text, _ = KaizenHooks.read_yaml_frontmatter(str(md_file))
                if yaml_text:
                    data = KaizenHooks.parse_yaml_simple(yaml_text)
                    last_accessed = data.get("last_accessed", "")
                    use_count = data.get("use_count", 0)
                    
                    if use_count < 5 and last_accessed:
                        try:
                            from datetime import datetime
                            last = datetime.fromisoformat(last_accessed.replace('Z', '+00:00'))
                            if last.timestamp() < cutoff:
                                candidates.append({
                                    "path": str(md_file.relative_to(self.project_root)),
                                    "uses": use_count,
                                    "last_access": last_accessed
                                })
                        except:
                            continue
            except:
                continue
                
        return candidates

# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Kaizen integration for dharmic-agora")
    parser.add_argument("--track", help="Track file access")
    parser.add_argument("--agent", default="DC", help="Agent ID")
    parser.add_argument("--action", default="read", choices=["read", "write"])
    parser.add_argument("--trending", action="store_true", help="Show trending files")
    parser.add_argument("--archive", action="store_true", help="Show archive candidates")
    
    args = parser.parse_args()
    
    tracker = KaizenTracker()
    
    if args.track:
        result = tracker.track_access(args.track, args.agent, args.action)
        print(f"✓ Tracked: {args.track}")
        if result:
            print(f"  use_count: {result.get('use_count')}")
            print(f"  grade: {result.get('quality_grade')}")
            
    elif args.trending:
        trending = tracker.get_trending()
        print("\n🔥 Trending Files:")
        for f in trending:
            print(f"  {f['uses']:3d} uses | {f['grade']} | {f['path']}")
            
    elif args.archive:
        candidates = tracker.get_archive_candidates()
        print(f"\n🗃️ Archive Candidates ({len(candidates)} files unused 90+ days):")
        for f in candidates[:10]:
            print(f"  {f['uses']:3d} uses | {f['path']}")
