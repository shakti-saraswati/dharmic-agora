#!/usr/bin/env python3
"""
Watchdog — Agent Health Monitor
Monitors heartbeat files and alerts on stale agents.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

HEARTBEAT_DIR = Path(__file__).parent / "heartbeats"
ALERTS_FILE = Path(__file__).parent / "alerts.jsonl"
DEADMAN_FILE = Path(__file__).parent / "deadman.touch"
STALE_THRESHOLD = 180  # seconds
CHECK_INTERVAL = 60  # seconds


def get_current_time():
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc)


def parse_iso8601(timestamp_str):
    """Parse ISO8601 timestamp string to datetime."""
    # Handle both Z and +00:00 formats
    ts = timestamp_str.replace('Z', '+00:00')
    return datetime.fromisoformat(ts)


def check_heartbeats():
    """Check all heartbeat files for stale agents."""
    if not HEARTBEAT_DIR.exists():
        HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
        return
    
    current_time = get_current_time()
    
    for heartbeat_file in HEARTBEAT_DIR.glob("*.json"):
        try:
            with open(heartbeat_file, 'r') as f:
                data = json.load(f)
            
            agent = data.get("agent", heartbeat_file.stem)
            timestamp_str = data.get("timestamp")
            status = data.get("status", "unknown")
            task = data.get("task", "")
            
            if not timestamp_str:
                continue
            
            heartbeat_time = parse_iso8601(timestamp_str)
            age_seconds = (current_time - heartbeat_time).total_seconds()
            
            if age_seconds > STALE_THRESHOLD:
                alert = {
                    "timestamp": current_time.isoformat(),
                    "level": "warning",
                    "agent": agent,
                    "last_heartbeat": timestamp_str,
                    "age_seconds": int(age_seconds),
                    "status": status,
                    "task": task
                }
                
                # Append to alerts file
                with open(ALERTS_FILE, 'a') as f:
                    f.write(json.dumps(alert) + '\n')
                
                print(f"⚠️  STALE: {agent} — {int(age_seconds)}s old (last: {status})")
        
        except Exception as e:
            print(f"❌ Error checking {heartbeat_file.name}: {e}")


def update_deadman():
    """Update watchdog's own deadman file."""
    DEADMAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEADMAN_FILE.touch()


def main():
    """Main watchdog loop."""
    print(f"🐕 Watchdog starting — monitoring {HEARTBEAT_DIR}")
    print(f"   Stale threshold: {STALE_THRESHOLD}s | Check interval: {CHECK_INTERVAL}s")
    
    while True:
        try:
            check_heartbeats()
            update_deadman()
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\n🛑 Watchdog stopped")
            break
        except Exception as e:
            print(f"❌ Watchdog error: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
