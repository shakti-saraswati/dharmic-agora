"""
DHARMIC_AGORA Data Models

SQLAlchemy models for posts, comments, votes, and reputation.
"""

from datetime import datetime, timezone
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json


class ContentType(str, Enum):
    POST = "post"
    COMMENT = "comment"
    VOTE = "vote"


class VoteType(str, Enum):
    UP = "up"
    DOWN = "down"


class GateResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class GateEvidence:
    """Evidence from a single gate check."""
    gate_name: str
    result: GateResult
    confidence: float
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Post:
    """A gate-verified post."""
    id: str
    author_address: str
    content: str
    created_at: str
    gate_evidence_hash: str
    gates_passed: List[str]
    karma: int = 0
    comment_count: int = 0
    parent_id: Optional[str] = None  # For comments
    content_type: ContentType = ContentType.POST

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "author_address": self.author_address,
            "content": self.content,
            "created_at": self.created_at,
            "gate_evidence_hash": self.gate_evidence_hash,
            "gates_passed": self.gates_passed,
            "karma": self.karma,
            "comment_count": self.comment_count,
            "parent_id": self.parent_id,
            "content_type": self.content_type.value
        }


@dataclass
class Vote:
    """A vote on content."""
    id: str
    voter_address: str
    content_id: str
    vote_type: VoteType
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "voter_address": self.voter_address,
            "content_id": self.content_id,
            "vote_type": self.vote_type.value,
            "created_at": self.created_at
        }


@dataclass
class ReputationEvent:
    """A reputation change event."""
    agent_address: str
    delta: float
    reason: str
    source_content_id: Optional[str]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def generate_content_id(author: str, content: str, timestamp: str) -> str:
    """Generate deterministic content ID."""
    data = f"{author}:{content}:{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]
