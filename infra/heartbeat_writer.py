"""
Heartbeat Writer — Library for Agent Health Reporting
Import this in agents to write heartbeat files.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def write_heartbeat(agent_name, status="active", current_task=""):
    """
    Write heartbeat file for an agent.
    
    Args:
        agent_name: Name of the agent (used as filename)
        status: Current status (e.g., "active", "idle", "working")
        current_task: Description of current task
    
    Returns:
        Path to the written heartbeat file
    """
    # Determine heartbeat directory relative to this file
    heartbeat_dir = Path(__file__).parent / "heartbeats"
    heartbeat_dir.mkdir(parents=True, exist_ok=True)
    
    heartbeat_file = heartbeat_dir / f"{agent_name}.json"
    
    heartbeat_data = {
        "agent": agent_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "task": current_task
    }
    
    # Write atomically with temp file + rename
    temp_file = heartbeat_file.with_suffix('.tmp')
    with open(temp_file, 'w') as f:
        json.dump(heartbeat_data, f, indent=2)
    
    temp_file.replace(heartbeat_file)
    
    return heartbeat_file


# Convenience function for importing
__all__ = ['write_heartbeat']
