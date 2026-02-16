"""Redis-backed ingestion queue/state manager for AKASHA RAG.

This module provides a thin operational layer so ingestion jobs are queued,
tracked, and auditable instead of being fire-and-forget calls.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis


class IngestionQueue:
    """Queue manager with explicit job state transitions."""

    def __init__(self, redis_url: Optional[str] = None, queue_name: str = "pdf_queue"):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.queue_name = queue_name
        self.state_prefix = "ingest:job:"
        self.client = redis.Redis.from_url(self.redis_url, decode_responses=True)

    def enqueue_pdf(self, file_path: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Enqueue a PDF ingestion job and initialize state in Redis."""
        if not file_path:
            raise ValueError("file_path is required")

        job_id = str(uuid.uuid4())
        payload = {
            "job_id": job_id,
            "file_path": file_path,
            "queue": self.queue_name,
            "state": "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }

        self.client.rpush(self.queue_name, json.dumps(payload))
        self.client.hset(f"{self.state_prefix}{job_id}", mapping={
            "state": "queued",
            "file_path": file_path,
            "queue": self.queue_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return payload

    def set_state(self, job_id: str, state: str, **extra: Any) -> None:
        """Set ingestion job state and optional extra fields."""
        mapping = {
            "state": state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        for key, value in extra.items():
            mapping[key] = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        self.client.hset(f"{self.state_prefix}{job_id}", mapping=mapping)

    def get_state(self, job_id: str) -> Dict[str, Any]:
        """Fetch the current state record for a job."""
        return self.client.hgetall(f"{self.state_prefix}{job_id}")
