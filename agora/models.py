"""
SAB Data Models
"""
from datetime import datetime, timezone
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum
import hashlib


class ContentType(str, Enum):
    POST = "post"
    COMMENT = "comment"


class VoteType(str, Enum):
    UP = "up"
    DOWN = "down"


class ModerationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPEALED = "appealed"


def generate_content_id(author: str, content: str, timestamp: str) -> str:
    """Generate deterministic content ID."""
    data = f"{author}:{content}:{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class Post:
    """A post or comment in the agora."""
    id: str
    author_address: str
    content: str
    created_at: str
    gate_evidence_hash: str
    gates_passed: List[str] = field(default_factory=list)
    content_type: ContentType = ContentType.POST
    parent_id: Optional[str] = None
    karma: int = 0
    comment_count: int = 0
    is_deleted: int = 0
    signature: Optional[str] = None
    signed_at: Optional[str] = None


@dataclass
class Vote:
    """A vote on content."""
    id: str
    voter_address: str
    content_id: str
    vote_type: VoteType
    created_at: str


@dataclass
class GateEvidence:
    """Gate evaluation evidence for a piece of content."""
    content_id: str
    evidence_hash: str
    evidence_json: str
    created_at: str
