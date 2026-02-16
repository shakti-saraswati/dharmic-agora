"""
Provider-agnostic model bus.

This package is intentionally small and dependency-light. It exists so any swarm
can route calls by *role* (planner/coder/critic/embedder) and plug in any model
or provider without rewriting the swarm.
"""

from .bus import ModelBus

__all__ = ["ModelBus"]

