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
