#!/usr/bin/env python3
"""
Kaizen Hooks — Continuous Improvement System
Auto-updates YAML frontmatter on file access

Usage:
  # In OpenClaw skill or agent code:
  from kaizen_hooks import on_file_read, on_file_write
  
  on_file_read("~/clawd/docs/my_doc.md")
  # Auto-increments use_count, updates last_accessed
  
  on_file_write("~/clawd/docs/my_doc.md")
  # Updates last_modified, modified_by

Integration with P9:
  - Low use_count (90 days) → Flag for archive
  - High use_count + low grade → Flag for upgrade
  - Modified frequently → Trending signal
"""

import re
from datetime import datetime, timezone
from pathlib import Path

class KaizenHooks:
    """Auto-update YAML frontmatter with usage metrics"""
    
    @staticmethod
    def read_yaml_frontmatter(filepath):
        """Extract YAML frontmatter from file"""
        path = Path(filepath)
        if not path.exists():
            return None, None
            
        content = path.read_text()
        
        if not content.startswith("---"):
            return None, content
            
        # Find second ---
        match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if not match:
            return None, content
            
        yaml_text = match.group(1)
        body = content[match.end():]
        
        return yaml_text, body
    
    @staticmethod
    def parse_yaml_simple(yaml_text):
        """Simple YAML parser for basic types"""
        data = {}
        if not yaml_text:
            return data
            
        for line in yaml_text.split('\n'):
            if ':' in line and not line.strip().startswith('#'):
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                
                # Type conversion
                if value.isdigit():
                    value = int(value)
                elif value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
                    
                data[key] = value
                
        return data
    
    @staticmethod
    def format_yaml_simple(data):
        """Format dict as simple YAML"""
        lines = ["---"]
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
            elif isinstance(value, str):
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        return "\n".join(lines)
    
    @staticmethod
    def on_file_access(filepath, agent_id="DC", action="read"):
        """Update frontmatter on file access"""
        path = Path(filepath)
        
        yaml_text, body = KaizenHooks.read_yaml_frontmatter(filepath)
        
        if yaml_text is None:
            # No YAML yet — create minimal
            data = {
                "title": path.stem,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "agent": agent_id,
                "use_count": 1,
                "last_accessed": datetime.now(timezone.utc).isoformat(),
                "status": "draft",
                "quality_grade": "C"
            }
        else:
            data = KaizenHooks.parse_yaml_simple(yaml_text)
            
            # Update metrics
            if action == "read":
                data["use_count"] = data.get("use_count", 0) + 1
                data["last_accessed"] = datetime.now(timezone.utc).isoformat()
                
            elif action == "write":
                data["last_modified"] = datetime.now(timezone.utc).isoformat()
                data["modified_by"] = agent_id
                
        # Check Kaizen triggers
        KaizenHooks.check_triggers(data, filepath)
        
        # Write back
        new_yaml = KaizenHooks.format_yaml_simple(data)
        path.write_text(new_yaml + "\n" + body)
        
        return data
    
    @staticmethod
    def check_triggers(data, filepath):
        """Check if file triggers Kaizen actions"""
        use_count = data.get("use_count", 0)
        grade = data.get("quality_grade", "C")
        
        # Trigger 1: High use, low grade → Upgrade candidate
        if use_count > 50 and grade in ["C", "D"]:
            print(f"🟡 KAIZEN FLAG: {filepath}")
            print(f"   High use ({use_count}) + Low grade ({grade}) → Upgrade to B?")
            # Could auto-create review task here
            
        # Trigger 2: Very low use → Archive candidate
        if use_count < 5:
            last_accessed = data.get("last_accessed", "")
            if last_accessed:
                try:
                    last = datetime.fromisoformat(last_accessed.replace('Z', '+00:00'))
                    days = (datetime.now(timezone.utc) - last).days
                    if days > 90:
                        print(f"🔴 KAIZEN FLAG: {filepath}")
                        print(f"   Unused 90+ days → Archive candidate")
                except:
                    pass
                    
        # Trigger 3: Trending (recent high use)
        if use_count > 20:
            print(f"🟢 KAIZEN FLAG: {filepath}")
            print(f"   Trending ({use_count} uses) → Consider promotion to canon")

# Convenience functions
def on_file_read(filepath, agent_id="DC"):
    return KaizenHooks.on_file_access(filepath, agent_id, "read")

def on_file_write(filepath, agent_id="DC"):
    return KaizenHooks.on_file_access(filepath, agent_id, "write")

# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 kaizen_hooks.py <filepath>")
        sys.exit(1)
        
    filepath = sys.argv[1]
    print(f"🔍 Processing: {filepath}")
    
    data = on_file_read(filepath)
    
    print(f"\n✅ Updated metrics:")
    print(f"   use_count: {data.get('use_count')}")
    print(f"   last_accessed: {data.get('last_accessed')}")
    print(f"   quality_grade: {data.get('quality_grade')}")
