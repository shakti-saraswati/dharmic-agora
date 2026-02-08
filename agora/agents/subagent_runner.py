#!/usr/bin/env python3
"""
Subagent Runner - Logs real agent runs to OpenClaw's runs.json

This fixes the gap where runs.json shows `"runs": {}` - no actual subagent runs recorded.
Now when NAGA_RELAY, VOIDCOURIER, or VIRALMANTRA execute, they get logged.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Callable
from functools import wraps


@dataclass
class SubagentRun:
    """Record of a subagent execution."""
    run_id: str
    agent_name: str
    task: str
    status: str  # running, completed, failed
    started_at: str
    completed_at: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Optional[dict] = None


class SubagentRunner:
    """
    Manages subagent execution and logging.
    
    Logs all runs to ~/.openclaw/subagents/runs.json so OpenClaw can see them.
    """
    
    def __init__(self):
        self.runs_dir = Path.home() / ".openclaw" / "subagents"
        self.runs_file = self.runs_dir / "runs.json"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing runs
        self.runs: dict[str, dict] = self._load_runs()
    
    def _load_runs(self) -> dict[str, dict]:
        """Load runs from file."""
        if self.runs_file.exists():
            try:
                with open(self.runs_file) as f:
                    data = json.load(f)
                    return data.get("runs", {})
            except (json.JSONDecodeError, KeyError):
                pass
        return {}
    
    def _save_runs(self):
        """Save runs to file."""
        data = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_runs": len(self.runs),
            "runs": self.runs
        }
        with open(self.runs_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def start_run(self, agent_name: str, task: str, metadata: dict = None) -> str:
        """Start a new subagent run, return run_id."""
        run_id = f"{agent_name}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        run = SubagentRun(
            run_id=run_id,
            agent_name=agent_name,
            task=task,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {}
        )
        
        self.runs[run_id] = asdict(run)
        self._save_runs()
        
        return run_id
    
    def complete_run(self, run_id: str, result: dict = None):
        """Mark a run as completed."""
        if run_id not in self.runs:
            return
        
        run = self.runs[run_id]
        run["status"] = "completed"
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        run["result"] = result or {}
        
        # Calculate duration
        started = datetime.fromisoformat(run["started_at"])
        completed = datetime.fromisoformat(run["completed_at"])
        run["duration_ms"] = int((completed - started).total_seconds() * 1000)
        
        self._save_runs()
    
    def fail_run(self, run_id: str, error: str):
        """Mark a run as failed."""
        if run_id not in self.runs:
            return
        
        run = self.runs[run_id]
        run["status"] = "failed"
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        run["error"] = error
        
        started = datetime.fromisoformat(run["started_at"])
        completed = datetime.fromisoformat(run["completed_at"])
        run["duration_ms"] = int((completed - started).total_seconds() * 1000)
        
        self._save_runs()
    
    def get_run(self, run_id: str) -> Optional[dict]:
        """Get a specific run."""
        return self.runs.get(run_id)
    
    def get_recent_runs(self, limit: int = 10, agent_name: str = None) -> list[dict]:
        """Get recent runs, optionally filtered by agent."""
        runs = list(self.runs.values())
        
        if agent_name:
            runs = [r for r in runs if r["agent_name"] == agent_name]
        
        # Sort by started_at descending
        runs.sort(key=lambda r: r["started_at"], reverse=True)
        
        return runs[:limit]
    
    def get_stats(self) -> dict:
        """Get run statistics."""
        runs = list(self.runs.values())
        
        by_agent = {}
        by_status = {"running": 0, "completed": 0, "failed": 0}
        
        for run in runs:
            agent = run["agent_name"]
            by_agent[agent] = by_agent.get(agent, 0) + 1
            by_status[run["status"]] = by_status.get(run["status"], 0) + 1
        
        return {
            "total_runs": len(runs),
            "by_agent": by_agent,
            "by_status": by_status
        }


# Singleton
_runner: Optional[SubagentRunner] = None

def get_runner() -> SubagentRunner:
    """Get the subagent runner singleton."""
    global _runner
    if _runner is None:
        _runner = SubagentRunner()
    return _runner


def logged_run(agent_name: str):
    """Decorator to automatically log subagent runs."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            runner = get_runner()
            task = func.__name__
            
            # Extract task description from kwargs if available
            if "task" in kwargs:
                task = kwargs["task"]
            
            run_id = runner.start_run(agent_name, task)
            
            try:
                result = func(*args, **kwargs)
                runner.complete_run(run_id, {"return_value": str(result)[:500]})
                return result
            except Exception as e:
                runner.fail_run(run_id, str(e))
                raise
        
        return wrapper
    return decorator


if __name__ == "__main__":
    runner = get_runner()
    
    print("📊 Subagent Runner - Execution Logger")
    print("=" * 50)
    
    # Test run
    run_id = runner.start_run(
        "NAGA_RELAY",
        "test_relay",
        {"source": "warp", "target": "openclaw"}
    )
    print(f"\nStarted run: {run_id}")
    
    # Simulate work
    time.sleep(0.1)
    
    # Complete
    runner.complete_run(run_id, {"messages_relayed": 1})
    
    print(f"\nStats: {json.dumps(runner.get_stats(), indent=2)}")
    print(f"\nRecent runs:")
    for run in runner.get_recent_runs(5):
        print(f"  - {run['agent_name']}: {run['task']} ({run['status']})")
