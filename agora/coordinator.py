#!/usr/bin/env python3
"""
DHARMIC_AGORA Coordinator
========================

The central coordinator that orchestrates all agents in the Dharmic Agora.
This is what the 10X_MOLTBOOK_ARCHITECTURE becomes when it's real code.

Agents managed:
- NAGA_RELAY: Secure bridge, 7 coils of security
- VOIDCOURIER: Intelligence messaging
- VIRALMANTRA: Memetic tracking, gamification

Pipeline: RAW INTAKE → PROCESSED INTELLIGENCE → STRATEGIC ACTIONS
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .agents import get_naga, get_courier, get_mantra
from .agents.subagent_runner import get_runner, logged_run


@dataclass
class AgoraConfig:
    """Configuration for the Agora coordinator."""
    base_path: Path = Path.home() / "DHARMIC_GODEL_CLAW" / "agora"
    auto_relay: bool = True
    auto_track_memes: bool = True
    broadcast_events: bool = True


class DharmicAgora:
    """
    The Dharmic Agora - A federation of AI agents working together.
    
    This is the alternative to Moltbook: open, dharmic, decentralized.
    """
    
    def __init__(self, config: AgoraConfig = None):
        self.config = config or AgoraConfig()
        self.config.base_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize all agents
        self.naga = get_naga()
        self.courier = get_courier()
        self.mantra = get_mantra()
        self.runner = get_runner()
        
        # Event log
        self.event_log = self.config.base_path / "events.jsonl"
        
        # State
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.events_processed = 0
    
    def log_event(self, event_type: str, data: dict):
        """Log an agora event."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "data": data
        }
        with open(self.event_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
        self.events_processed += 1
    
    @logged_run("DHARMIC_AGORA")
    def process_intelligence(self, data: Any, source: str, targets: list[str] = None) -> dict:
        """
        Full intelligence pipeline:
        1. NAGA_RELAY secures and classifies
        2. VIRALMANTRA tracks memetic spread
        3. VOIDCOURIER delivers to targets
        """
        results = {
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stages": {}
        }
        
        # Stage 1: Secure relay through NAGA
        if self.config.auto_relay:
            relay_target = self.config.base_path / "intelligence" / "processed.jsonl"
            relay_target.parent.mkdir(parents=True, exist_ok=True)
            
            success = self.naga.relay(data, source, str(relay_target))
            results["stages"]["naga_relay"] = {
                "success": success,
                "messages_processed": self.naga.messages_processed
            }
        
        # Stage 2: Track as meme if it's content
        if self.config.auto_track_memes and isinstance(data, dict):
            content = data.get("content", str(data))
            if len(content) > 10:  # Skip trivial content
                meme = self.mantra.track_meme(content[:200], source)
                results["stages"]["meme_tracking"] = {
                    "meme_id": meme.id,
                    "classification": meme.classification
                }
        
        # Stage 3: Broadcast to targets
        if self.config.broadcast_events and targets:
            broadcast_results = self.courier.broadcast(
                {"type": "intelligence", "source": source, "data": data},
                targets
            )
            results["stages"]["broadcast"] = broadcast_results
        
        self.log_event("intelligence_processed", results)
        return results
    
    @logged_run("DHARMIC_AGORA")
    def coordinate_agents(self, task: str, params: dict = None) -> dict:
        """
        Coordinate multiple agents on a task.
        
        Tasks:
        - "sync": Sync state between agents
        - "health_check": Check all agent health
        - "broadcast": Send message to all routes
        - "trending": Get trending memes
        """
        params = params or {}
        
        if task == "sync":
            return self._sync_agents()
        elif task == "health_check":
            return self._health_check()
        elif task == "broadcast":
            return self._broadcast(params.get("message", {}))
        elif task == "trending":
            return self._get_trending(params.get("limit", 10))
        else:
            return {"error": f"Unknown task: {task}"}
    
    def _sync_agents(self) -> dict:
        """Sync state between all agents."""
        # Courier pings all routes
        ping_results = {}
        for route_name in self.courier.routes:
            ping_results[route_name] = self.courier.ping(route_name)
        
        return {
            "task": "sync",
            "ping_results": ping_results,
            "naga_coils": self.naga.coils_applied,
            "mantra_memes": len(self.mantra.memes)
        }
    
    def _health_check(self) -> dict:
        """Check health of all agents."""
        return {
            "task": "health_check",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents": {
                "naga_relay": self.naga.get_status(),
                "voidcourier": self.courier.get_status(),
                "viralmantra": self.mantra.get_status()
            },
            "subagent_runs": self.runner.get_stats()
        }
    
    def _broadcast(self, message: dict) -> dict:
        """Broadcast to all known routes."""
        all_routes = list(self.courier.routes.keys())
        results = self.courier.broadcast(message, all_routes)
        return {
            "task": "broadcast",
            "results": results,
            "routes_attempted": len(all_routes)
        }
    
    def _get_trending(self, limit: int) -> dict:
        """Get trending memes."""
        trending = self.mantra.get_trending(limit)
        return {
            "task": "trending",
            "memes": [
                {"id": m.id, "content": m.content[:100], "resonance": m.resonance_score}
                for m in trending
            ]
        }
    
    def get_status(self) -> dict:
        """Get full agora status."""
        return {
            "name": "DHARMIC_AGORA",
            "version": "0.1.0",
            "started_at": self.started_at,
            "events_processed": self.events_processed,
            "agents": {
                "naga_relay": self.naga.get_status(),
                "voidcourier": self.courier.get_status(),
                "viralmantra": self.mantra.get_status()
            },
            "subagent_runs": self.runner.get_stats(),
            "config": {
                "base_path": str(self.config.base_path),
                "auto_relay": self.config.auto_relay,
                "auto_track_memes": self.config.auto_track_memes,
                "broadcast_events": self.config.broadcast_events
            }
        }


# Singleton
_agora: Optional[DharmicAgora] = None

def get_agora() -> DharmicAgora:
    """Get the DHARMIC_AGORA singleton."""
    global _agora
    if _agora is None:
        _agora = DharmicAgora()
    return _agora


if __name__ == "__main__":
    agora = get_agora()
    
    print("🕉️ DHARMIC_AGORA - Federation Coordinator")
    print("=" * 50)
    
    # Health check
    health = agora.coordinate_agents("health_check")
    print(f"\n📊 Health Check:")
    print(f"  NAGA_RELAY: {health['agents']['naga_relay']['messages_processed']} msgs")
    print(f"  VOIDCOURIER: {health['agents']['voidcourier']['messages_sent']} sent")
    print(f"  VIRALMANTRA: {health['agents']['viralmantra']['total_memes']} memes")
    
    # Process some intelligence
    result = agora.process_intelligence(
        {"content": "The Agora is alive", "type": "status"},
        source="coordinator",
        targets=["warp", "openclaw"]
    )
    print(f"\n🔄 Intelligence processed: {len(result['stages'])} stages")
    
    # Full status
    print(f"\n{json.dumps(agora.get_status(), indent=2)}")
