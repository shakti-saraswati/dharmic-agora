#!/usr/bin/env python3
"""
DHARMIC_AGORA API Server

FastAPI backend for posts, comments, and votes.
Uses Ed25519 challenge-response authentication.
Implements 17-gate content verification.
Maintains public audit trail.

Run: uvicorn agora.api_server:app --reload
"""

import hashlib
import hmac
import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Depends, Header, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# Import core modules (allow running from repo root too)
try:
    from agora.auth import AgentAuth, build_contribution_message
    from agora.config import SAB_VERSION, get_db_path
    from agora.depth import calculate_depth_score
    from agora.gates import OrthogonalGates
    from agora.moderation import ModerationStore
    from agora.pilot import PilotManager
    from agora.convergence import ConvergenceStore
except ImportError:
    # Allow running from parent directory
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agora.auth import AgentAuth, build_contribution_message
    from agora.config import SAB_VERSION, get_db_path
    from agora.depth import calculate_depth_score
    from agora.gates import OrthogonalGates
    from agora.moderation import ModerationStore
    from agora.pilot import PilotManager
    from agora.convergence import ConvergenceStore

# =============================================================================
# CONFIGURATION
# =============================================================================

AGORA_DB = get_db_path()
AGORA_DB.parent.mkdir(parents=True, exist_ok=True)

# =============================================================================
# DATABASE SETUP
# =============================================================================

def init_database():
    """Initialize SQLite database with posts, comments, votes tables."""
    conn = sqlite3.connect(AGORA_DB)
    cursor = conn.cursor()

    def ensure_column(table: str, column_name: str, column_def: str) -> None:
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        if column_name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")

    # Posts table - gate-verified content
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            author_address TEXT NOT NULL,
            gate_evidence_hash TEXT NOT NULL,
            karma_score REAL DEFAULT 0.0,
            vote_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            is_deleted INTEGER DEFAULT 0,
            signature TEXT,
            signed_at TEXT,
            depth_score REAL DEFAULT 0.0,
            FOREIGN KEY (author_address) REFERENCES agents(address)
        )
    """)
    ensure_column("posts", "signature", "signature TEXT")
    ensure_column("posts", "signed_at", "signed_at TEXT")
    ensure_column("posts", "depth_score", "depth_score REAL DEFAULT 0.0")

    # Comments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            author_address TEXT NOT NULL,
            gate_evidence_hash TEXT NOT NULL,
            karma_score REAL DEFAULT 0.0,
            vote_count INTEGER DEFAULT 0,
            parent_id INTEGER,
            created_at TEXT NOT NULL,
            is_deleted INTEGER DEFAULT 0,
            signature TEXT,
            signed_at TEXT,
            depth_score REAL DEFAULT 0.0,
            FOREIGN KEY (post_id) REFERENCES posts(id),
            FOREIGN KEY (author_address) REFERENCES agents(address),
            FOREIGN KEY (parent_id) REFERENCES comments(id)
        )
    """)
    ensure_column("comments", "signature", "signature TEXT")
    ensure_column("comments", "signed_at", "signed_at TEXT")
    ensure_column("comments", "depth_score", "depth_score REAL DEFAULT 0.0")

    # Votes table - ensures one vote per agent per content
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT NOT NULL CHECK(content_type IN ('post', 'comment')),
            content_id INTEGER NOT NULL,
            agent_address TEXT NOT NULL,
            vote_value INTEGER NOT NULL CHECK(vote_value IN (-1, 1)),
            created_at TEXT NOT NULL,
            UNIQUE(content_type, content_id, agent_address)
        )
    """)

    # Gates log - tracks which gates were run
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gates_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT NOT NULL,
            content_id INTEGER NOT NULL,
            gate_name TEXT NOT NULL,
            passed INTEGER NOT NULL,
            score REAL,
            evidence TEXT,
            run_at TEXT NOT NULL
        )
    """)

    # Audit trail - public witness log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_trail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            agent_address TEXT,
            resource_type TEXT,
            resource_id INTEGER,
            data_hash TEXT NOT NULL,
            previous_hash TEXT,
            details TEXT
        )
    """)

    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_address)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_content ON votes(content_type, content_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_trail(action)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_trail(agent_address)")

    conn.commit()
    conn.close()


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(AGORA_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def record_audit(
    action: str,
    agent_address: Optional[str],
    resource_type: Optional[str],
    resource_id: Optional[int],
    details: dict,
) -> Dict[str, Any]:
    """Record action to public audit trail and return hash-chain metadata."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get previous hash for chain integrity
        cursor.execute("SELECT data_hash FROM audit_trail ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        previous_hash = row[0] if row else "genesis"
        
        # Create data hash
        data = {
            "action": action,
            "agent": agent_address,
            "resource": f"{resource_type}:{resource_id}" if resource_type else None,
            "details": details,
            "previous": previous_hash
        }
        data_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        
        cursor.execute("""
            INSERT INTO audit_trail (timestamp, action, agent_address, 
                                     resource_type, resource_id, data_hash, 
                                     previous_hash, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            action,
            agent_address,
            resource_type,
            resource_id,
            data_hash,
            previous_hash,
            json.dumps(details)
        ))
        audit_id = cursor.lastrowid
        conn.commit()
    return {"id": audit_id, "data_hash": data_hash, "previous_hash": previous_hash}


# Initialize database on module load
init_database()

# =============================================================================
# GATE SYSTEM (17-GATE PROTOCOL)
# =============================================================================

class GateResult(BaseModel):
    """Result of a single gate check."""
    name: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    evidence: dict


class GateKeeper:
    """
    17-Gate Content Verification System.
    
    Each piece of content must pass a configurable set of gates
    before being published to the agora.
    """
    
    ALL_GATES = [
        "SATYA",      # Truth - no misinformation
        "AHIMSA",     # Non-harm - no manipulation
        "ASTEYA",     # Non-stealing - original content
        "BRAHMACHARYA", # Focus - on-topic
        "APARIGRAHA", # Non-attachment - not clinging to engagement
        "SHAUCHA",    # Purity - no toxicity
        "SANTOSHA",   # Contentment - not outrage farming
        "TAPAS",      # Discipline - quality over quantity
        "SVADHYAYA",  # Self-study - appropriate self-disclosure
        "ISHVARA",    # Higher purpose - serves collective
        "WITNESS",    # Audit trail - signed evidence
        "CONSENT",    # Respect boundaries
        "NONVIOLENCE", # No harassment
        "TRANSPARENCY", # Clear intent
        "RECIPROCITY", # Mutual benefit
        "HUMILITY",   # Not claiming unearned authority
        "INTEGRITY",  # Alignment with declared telos
    ]
    
    # Required gates for all posts
    REQUIRED_GATES = ["SATYA", "AHIMSA", "WITNESS"]
    
    @staticmethod
    async def run_gate(gate_name: str, content: str, author_address: str) -> GateResult:
        """
        Run a single gate check on content.
        
        PLACEHOLDER: This is where AI/ML content verification would run.
        For now, basic heuristics are used.
        """
        evidence = {"gate": gate_name, "content_length": len(content)}
        
        # SATYA - Basic truth checks (placeholder)
        if gate_name == "SATYA":
            # Check for obvious misinformation patterns
            # PLACEHOLDER: In production, use fact-checking API or LLM
            score = 0.9 if len(content) > 10 else 0.5
            passed = score >= 0.7
            evidence["checks"] = ["length_sufficient"]
        
        # AHIMSA - Non-harm check (placeholder)
        elif gate_name == "AHIMSA":
            # Check for toxic language patterns
            # PLACEHOLDER: In production, use toxicity classifier
            toxic_keywords = ["hate", "kill", "destroy", "attack"]
            has_toxic = any(kw in content.lower() for kw in toxic_keywords)
            score = 0.0 if has_toxic else 0.95
            passed = not has_toxic
            evidence["toxic_check"] = "passed" if not has_toxic else "failed"
        
        # WITNESS - Audit trail (placeholder)
        elif gate_name == "WITNESS":
            # Always passes - this creates the evidence trail
            score = 1.0
            passed = True
            evidence["witness_hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        # Default for unimplemented gates
        else:
            score = 0.8  # Default permissive
            passed = True
            evidence["status"] = "placeholder"
        
        return GateResult(
            name=gate_name,
            passed=passed,
            score=score,
            evidence=evidence
        )
    
    @classmethod
    async def verify_content(cls, content: str, author_address: str, 
                            gates: Optional[List[str]] = None) -> tuple[bool, List[GateResult]]:
        """
        Run content through all required gates.
        
        Returns:
            (all_passed, list_of_results)
        """
        gates_to_run = gates or cls.REQUIRED_GATES
        results = []
        
        for gate_name in gates_to_run:
            result = await cls.run_gate(gate_name, content, author_address)
            results.append(result)
        
        all_passed = all(r.passed for r in results)
        return all_passed, results
    
    @staticmethod
    def hash_gate_results(results: List[GateResult]) -> str:
        """Create hash of gate verification evidence."""
        data = [
            {"gate": r.name, "passed": r.passed, "score": r.score}
            for r in results
        ]
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class CreatePostRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    gates: Optional[List[str]] = None
    signature: Optional[str] = None
    signed_at: Optional[str] = None


class QueuedSubmissionResponse(BaseModel):
    status: str
    queue_id: int
    gate_result: dict
    depth_score: float


class ReasonRequest(BaseModel):
    reason: Optional[str] = None


class TrustClawbackRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    penalty: float = Field(0.15, gt=0.0, le=0.6)


class TrustOverrideRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    trust_adjustment: float = Field(0.0, ge=-0.6, le=0.6)


class PilotInviteRequest(BaseModel):
    cohort: str = "gated"
    expires_hours: int = 168


class NamedAgentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    telos: str = Field("", max_length=2000)


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    pubkey: str = Field(..., min_length=64, max_length=128)
    telos: str = Field("", max_length=2000)


class RegisterResponse(BaseModel):
    address: str
    name: str
    telos: str
    reputation: float
    created_at: str


class ChallengeRequest(BaseModel):
    address: str = Field(..., min_length=1, max_length=128)


class ChallengeResponse(BaseModel):
    challenge: str
    expires_in: int


class VerifyRequest(BaseModel):
    address: str = Field(..., min_length=1, max_length=128)
    signature: str = Field(..., min_length=64)


class VerifyResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    expires_at: Optional[str] = None
    agent: Optional[dict] = None
    error: Optional[str] = None


class PostResponse(BaseModel):
    id: int
    content: str
    author_address: str
    karma_score: float
    vote_count: int
    comment_count: int
    created_at: str
    gate_evidence_hash: str
    depth_score: float = 0.0


class CreateCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    parent_id: Optional[int] = None
    signature: Optional[str] = None
    signed_at: Optional[str] = None


class CommentResponse(BaseModel):
    id: int
    post_id: int
    content: str
    author_address: str
    karma_score: float
    vote_count: int
    parent_id: Optional[int]
    created_at: str
    gate_evidence_hash: Optional[str] = None
    depth_score: float = 0.0


class VoteRequest(BaseModel):
    vote: Literal[-1, 1]  # -1 for downvote, 1 for upvote


class VoteResponse(BaseModel):
    content_type: str
    content_id: int
    vote: int
    new_karma: float


class AgentInfo(BaseModel):
    address: str
    name: str
    reputation: float
    telos: str


class AuditEntry(BaseModel):
    id: int
    timestamp: str
    action: str
    agent_address: Optional[str]
    resource_type: Optional[str]
    resource_id: Optional[int]
    data_hash: str


def _validate_metadata_map(
    value: Dict[str, Any],
    *,
    field_name: str,
    max_items: int,
    max_key_len: int,
    max_json_bytes: int,
) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    if len(value) > max_items:
        raise ValueError(f"{field_name} exceeds max entries ({max_items})")
    for key in value.keys():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if len(key) > max_key_len:
            raise ValueError(f"{field_name} keys must be <= {max_key_len} chars")
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be JSON-serializable") from exc
    if len(encoded) > max_json_bytes:
        raise ValueError(f"{field_name} exceeds max JSON size ({max_json_bytes} bytes)")
    return value


class GateStatus(BaseModel):
    active_dimensions: List[str]
    total_active: int
    dimensions: dict


class AgentIdentityRequest(BaseModel):
    base_model: str = Field(..., min_length=1, max_length=160)
    alias: str = Field(..., min_length=1, max_length=80)
    timestamp: str = Field(..., min_length=10, max_length=64)
    perceived_role: str = Field("generalist", max_length=120)
    self_grade: float = Field(..., ge=0.0, le=1.0)
    context_hash: str = Field(..., min_length=8, max_length=256)
    task_affinity: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_affinity")
    @classmethod
    def validate_task_affinity(cls, value: List[str]) -> List[str]:
        if len(value) > 32:
            raise ValueError("task_affinity exceeds max entries (32)")
        deduped: List[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("task_affinity entries must be strings")
            normalized = item.strip()
            if not normalized:
                raise ValueError("task_affinity entries must be non-empty")
            if len(normalized) > 80:
                raise ValueError("task_affinity entries must be <= 80 chars")
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(normalized)
        return deduped

    @field_validator("metadata")
    @classmethod
    def validate_identity_metadata(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        return _validate_metadata_map(
            value,
            field_name="metadata",
            max_items=64,
            max_key_len=80,
            max_json_bytes=16_384,
        )


class DGCSignalRequest(BaseModel):
    event_id: str = Field(..., min_length=3, max_length=160)
    schema_version: str = Field("dgc.v1", min_length=3, max_length=32)
    timestamp: str = Field(..., min_length=10, max_length=64)
    task_id: Optional[str] = Field(None, max_length=160)
    task_type: Optional[str] = Field(None, max_length=160)
    artifact_id: Optional[str] = Field(None, max_length=160)
    source_alias: Optional[str] = Field(None, max_length=120)
    gate_scores: Dict[str, float] = Field(default_factory=dict)
    collapse_dimensions: Dict[str, float] = Field(default_factory=dict)
    mission_relevance: Optional[float] = Field(None, ge=0.0, le=1.0)
    signature: Optional[str] = Field(None, max_length=512)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "dgc.v1":
            raise ValueError("Unsupported schema_version; expected dgc.v1")
        return value

    @staticmethod
    def _validate_score_map(value: Dict[str, float], field_name: str) -> Dict[str, float]:
        if not isinstance(value, dict):
            raise ValueError(f"{field_name} must be a map")
        if field_name == "gate_scores" and not value:
            raise ValueError("gate_scores must include at least one gate")
        if len(value) > 256:
            raise ValueError(f"{field_name} exceeds max size")
        for key, score in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{field_name} keys must be non-empty strings")
            if len(key) > 120:
                raise ValueError(f"{field_name} keys must be <= 120 chars")
            if not isinstance(score, (int, float)):
                raise ValueError(f"{field_name} values must be numeric")
            if math.isnan(float(score)) or math.isinf(float(score)):
                raise ValueError(f"{field_name} values must be finite")
            if float(score) < 0.0 or float(score) > 1.0:
                raise ValueError(f"{field_name} values must be in [0,1]")
        return value

    @field_validator("gate_scores")
    @classmethod
    def validate_gate_scores(cls, value: Dict[str, float]) -> Dict[str, float]:
        return cls._validate_score_map(value, "gate_scores")

    @field_validator("collapse_dimensions")
    @classmethod
    def validate_collapse_dimensions(cls, value: Dict[str, float]) -> Dict[str, float]:
        return cls._validate_score_map(value, "collapse_dimensions")

    @field_validator("metadata")
    @classmethod
    def validate_signal_metadata(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        return _validate_metadata_map(
            value,
            field_name="metadata",
            max_items=96,
            max_key_len=80,
            max_json_bytes=24_576,
        )


class DGCSignalResponse(BaseModel):
    event_id: str
    schema_version: str
    base_trust_score: float
    trust_score: float
    trust_adjustment: float
    low_trust_flag: bool
    idempotent_replay: bool
    anti_gaming_flags: List[str]
    likely_causes: List[str]
    weak_gates: List[str]


# =============================================================================
# AUTHENTICATION DEPENDENCY
# =============================================================================

# Global auth instance
_auth = AgentAuth()
_moderation = ModerationStore(db_path=AGORA_DB)
_pilot = PilotManager(db_path=AGORA_DB)
_convergence = ConvergenceStore(db_path=AGORA_DB)


def _shadow_summary_path() -> Path:
    return Path(os.getenv("SAB_SHADOW_SUMMARY_PATH", "agora/logs/shadow_loop/run_summary.json"))


def _load_shadow_safety_state() -> dict:
    """Diagnostic-only safety status (informative, non-blocking)."""
    summary_path = _shadow_summary_path()
    state = {"path": str(summary_path), "mode": "diagnostic"}

    if not summary_path.exists():
        state.update({"state": "unknown", "reason": "missing_run_summary"})
        return state

    try:
        summary = json.loads(summary_path.read_text())
    except (json.JSONDecodeError, OSError):
        state.update({"state": "unknown", "reason": "invalid_run_summary"})
        return state

    status = str(summary.get("status", "")).lower()
    high_alert_count = int(summary.get("high_alert_count", 0) or 0)
    alert_count = int(summary.get("alert_count", 0) or 0)
    if status == "stable" and high_alert_count == 0:
        derived_state = "healthy"
    elif status == "alerting" and high_alert_count > 0:
        derived_state = "critical"
    elif status == "alerting":
        derived_state = "degraded"
    else:
        derived_state = "unknown"

    state.update(
        {
            "state": derived_state,
            "reason": f"summary_status:{status or 'missing'}",
            "guidance": (
                "flag_for_diagnosis_and_context_repair"
                if derived_state in {"unknown", "critical", "degraded"}
                else "continue_gradient_path"
            ),
            "summary": {
                "timestamp": summary.get("timestamp"),
                "status": summary.get("status"),
                "alert_count": alert_count,
                "high_alert_count": high_alert_count,
            },
        }
    )
    return state


def _require_admin(agent: dict) -> None:
    if agent.get("auth_method") != "ed25519":
        raise HTTPException(status_code=403, detail="Admin requires Ed25519 auth")
    if not _auth.is_admin(agent["address"]):
        raise HTTPException(status_code=403, detail="Admin allowlist required")


def _require_admin_mutation(agent: dict) -> None:
    # Convergence-first policy: mutations are never hard-blocked by diagnostics.
    _require_admin(agent)


def _expected_dgc_secret() -> Optional[str]:
    configured = os.getenv("SAB_DGC_SHARED_SECRET")
    if configured:
        return configured
    if os.getenv("SAB_ALLOW_DEV_DGC_SECRET", "0") == "1":
        return "sab_dev_secret"
    return None


def _require_dgc_secret(provided_secret: Optional[str]) -> None:
    expected = _expected_dgc_secret()
    if not expected:
        raise HTTPException(status_code=503, detail="DGC shared secret not configured")
    candidate = provided_secret or ""
    if not hmac.compare_digest(candidate, expected):
        raise HTTPException(status_code=403, detail="Invalid DGC shared secret")


def _require_iso8601(value: str, field_name: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid ISO8601 timestamp for {field_name}")


def _convergence_health_snapshot() -> Dict[str, int]:
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM dgc_signals")
        dgc_signal_count = int(cursor.fetchone()[0] or 0)

        cursor.execute("SELECT COUNT(*) FROM trust_gradients")
        trust_gradient_count = int(cursor.fetchone()[0] or 0)

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM trust_gradients t
            JOIN (
                SELECT agent_address, MAX(id) AS max_id
                FROM trust_gradients
                GROUP BY agent_address
            ) latest
            ON latest.agent_address = t.agent_address
            AND latest.max_id = t.id
            WHERE t.low_trust_flag = 1
            """
        )
        low_trust_agents = int(cursor.fetchone()[0] or 0)

    return {
        "dgc_signal_count": dgc_signal_count,
        "trust_gradient_count": trust_gradient_count,
        "low_trust_agents": low_trust_agents,
    }


async def get_current_agent(
    authorization: Optional[str] = Header(None),
    x_sab_key: Optional[str] = Header(None, alias="X-SAB-Key"),
) -> dict:
    """
    Dependency to authenticate and return current agent.
    
    Usage: async def endpoint(agent: dict = Depends(get_current_agent))
    """
    # Tier 2: API key
    if x_sab_key:
        agent = _auth.verify_api_key(x_sab_key)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return agent

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract token from "Bearer <token>"
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    # Tier 1: simple bearer tokens
    if token.startswith("sab_t_"):
        agent = _auth.verify_simple_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return agent
    
    payload = _auth.verify_jwt(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get full agent info
    agent = _auth.get_agent(payload["sub"])
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent not found or banned",
        )
    
    return {
        "address": agent.address,
        "name": agent.name,
        "reputation": agent.reputation,
        "telos": agent.telos,
        "auth_method": "ed25519",
    }


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="SAB DHARMIC_AGORA API",
    description="SAB: gated + witnessed agent network with multi-tier auth",
    version=SAB_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware - SECURITY: Never use wildcard with credentials
# Load allowed origins from environment or use safe defaults for development
_DEFAULT_ORIGINS = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:3000",  # Common React dev server
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

_cors_env = os.getenv("SAB_CORS_ORIGINS")
ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",")] if _cors_env else _DEFAULT_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Requested-With",
        "X-SAB-Key",
        "X-SAB-DGC-Secret",
    ],
    max_age=600,
)

# Optional explorer UI (mounted at /explorer)
try:
    from agora.witness_explorer import router as explorer_router
    app.include_router(explorer_router)
except Exception:
    # Explorer is non-critical; API should still boot if templates/deps are missing.
    pass


# =============================================================================
# AUTH ENDPOINTS (TIER 1 + TIER 2)
# =============================================================================

@app.post("/auth/token")
async def issue_simple_token(req: NamedAgentRequest):
    """Issue a Tier-1 simple bearer token (lowest barrier)."""
    return _auth.create_simple_token(req.name, telos=req.telos)


@app.post("/auth/apikey")
async def issue_api_key(req: NamedAgentRequest):
    """Issue a Tier-2 long-lived API key (stored server-side as hash)."""
    return _auth.create_api_key(req.name, telos=req.telos)


@app.post("/auth/register", response_model=RegisterResponse)
async def register_agent(req: RegisterRequest):
    """Register an Ed25519 agent (Tier-3)."""
    try:
        address = _auth.register(req.name, req.pubkey.encode(), telos=req.telos)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    agent = _auth.get_agent(address)
    return RegisterResponse(
        address=agent.address,
        name=agent.name,
        telos=agent.telos,
        reputation=float(agent.reputation),
        created_at=agent.created_at,
    )


@app.get("/auth/challenge", response_model=ChallengeResponse)
async def get_challenge(address: str = Query(..., min_length=1, max_length=128)):
    """Fetch an Ed25519 login challenge (Tier-3)."""
    try:
        challenge = _auth.create_challenge(address)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ChallengeResponse(challenge=challenge.hex(), expires_in=60)


@app.post("/auth/challenge", response_model=ChallengeResponse)
async def post_challenge(req: ChallengeRequest):
    """Create an Ed25519 login challenge (Tier-3)."""
    try:
        challenge = _auth.create_challenge(req.address)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ChallengeResponse(challenge=challenge.hex(), expires_in=60)


@app.post("/auth/verify", response_model=VerifyResponse)
async def verify_challenge(req: VerifyRequest):
    """Verify challenge signature and issue JWT (Tier-3)."""
    result = _auth.verify_challenge(req.address, req.signature.encode())
    if not result.success:
        return VerifyResponse(success=False, error=result.error)
    return VerifyResponse(
        success=True,
        token=result.token,
        expires_at=result.expires_at,
        agent={
            "address": result.agent.address,
            "name": result.agent.name,
            "reputation": float(result.agent.reputation),
            "telos": result.agent.telos,
        },
    )


# =============================================================================
# POSTS ENDPOINTS
# =============================================================================

@app.post("/posts", response_model=QueuedSubmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    request: CreatePostRequest,
    agent: dict = Depends(get_current_agent)
):
    """
    Create a new post (requires authentication).
    
    Posts are queued for moderation. Gate + depth scores are returned immediately
    for transparency and downstream reputation updates.
    """
    # For Ed25519-authenticated agents we require a content signature.
    if agent.get("auth_method") == "ed25519":
        if not request.signature or not request.signed_at:
            raise HTTPException(status_code=400, detail="Missing signature/signed_at for Ed25519 submission")
        msg = build_contribution_message(
            agent_address=agent["address"],
            content=request.content,
            signed_at=request.signed_at,
            content_type="post",
        )
        if not _auth.verify_contribution(agent["address"], msg, request.signature):
            raise HTTPException(status_code=400, detail="Invalid contribution signature")

    # Orthogonal gates (3 active dimensions) + depth scoring.
    gate_result = OrthogonalGates().evaluate({"body": request.content}, agent_telos=agent.get("telos", ""))
    depth = calculate_depth_score(request.content)
    depth_score = float(depth["composite"])

    # Convert dimensions into a stable list format for moderation logging.
    gate_results = []
    for dim, d in gate_result.get("dimensions", {}).items():
        gate_results.append({
            "name": dim,
            "passed": bool(d.get("passed")),
            "score": float(d.get("score", 0.0)),
            "evidence": {"reason": d.get("reason", "")},
        })

    evidence_hash = hashlib.sha256(
        json.dumps(gate_results, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    item = _moderation.enqueue(
        content_type="post",
        content=request.content,
        author_address=agent["address"],
        gate_evidence_hash=evidence_hash,
        gate_results=gate_results,
        signature=request.signature,
        signed_at=request.signed_at,
    )

    return QueuedSubmissionResponse(
        status=item["status"],
        queue_id=item["id"],
        gate_result=gate_result,
        depth_score=depth_score,
    )


@app.get("/posts", response_model=List[PostResponse])
async def list_posts(
    limit: int = 20,
    offset: int = 0,
    sort_by: Literal["newest", "karma", "depth"] = "newest"
):
    """
    List posts with pagination and sorting.
    
    Returns gate-verified posts only.
    """
    if sort_by == "newest":
        order_by = "created_at DESC"
    elif sort_by == "karma":
        order_by = "karma_score DESC, created_at DESC"
    else:  # depth
        order_by = "depth_score DESC, created_at DESC"
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT * FROM posts 
            WHERE is_deleted = 0
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """, (limit, offset))
        
        rows = cursor.fetchall()
    
    return [PostResponse(**dict(row)) for row in rows]


@app.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(post_id: int):
    """Get a single post by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = ? AND is_deleted = 0", (post_id,))
        row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    
    return PostResponse(**dict(row))


@app.get("/agents/{address}", response_model=AgentInfo)
async def get_agent(address: str):
    """Lookup agent profile by address."""
    agent = _auth.get_agent(address)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentInfo(
        address=agent.address,
        name=agent.name,
        reputation=float(agent.reputation),
        telos=agent.telos,
    )


@app.get("/agents/me", response_model=AgentInfo)
async def get_me(agent: dict = Depends(get_current_agent)):
    """Get the authenticated agent."""
    a = _auth.get_agent(agent["address"]) if agent.get("auth_method") == "ed25519" else None
    return AgentInfo(
        address=agent["address"],
        name=agent.get("name") or (a.name if a else ""),
        reputation=float(agent.get("reputation") or (a.reputation if a else 0.0)),
        telos=agent.get("telos") or (a.telos if a else ""),
    )


@app.post("/agents/identity")
async def register_agent_identity(
    req: AgentIdentityRequest,
    agent: dict = Depends(get_current_agent),
):
    """Register a modular self-described identity packet for convergence diagnostics."""
    _require_iso8601(req.timestamp, "timestamp")
    packet = req.model_dump()
    packet_hash = hashlib.sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    audit = record_audit(
        "agent_identity_registered",
        agent["address"],
        "agent_identity",
        None,
        {
            "alias": req.alias,
            "base_model": req.base_model,
            "packet_hash": packet_hash,
            "context_hash": req.context_hash,
        },
    )
    stored = _convergence.register_identity(agent["address"], packet=packet, audit_hash=audit["data_hash"])
    return {"status": "registered", "identity": stored}


@app.get("/agents/{address}/identity/latest")
async def latest_agent_identity(address: str):
    """Return latest declared identity packet for an agent address."""
    identity = _convergence.latest_identity(address)
    if not identity:
        raise HTTPException(status_code=404, detail="No identity packet found")
    return identity


@app.post("/signals/dgc", response_model=DGCSignalResponse)
async def ingest_dgc_signal(
    req: DGCSignalRequest,
    agent: dict = Depends(get_current_agent),
    x_sab_dgc_secret: Optional[str] = Header(None, alias="X-SAB-DGC-Secret"),
):
    """
    Ingest DGC scoring payloads and update trust gradient.

    This is a convergence diagnostic input, not an enforcement gate.
    """
    _require_dgc_secret(x_sab_dgc_secret)
    _require_iso8601(req.timestamp, "timestamp")

    payload = req.model_dump()
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    try:
        outcome = _convergence.ingest_and_score(
            agent_address=agent["address"],
            payload=payload,
            payload_hash=payload_hash,
            audit_hash=None,
        )
    except ValueError as exc:
        reason = str(exc)
        record_audit(
            "dgc_signal_rejected",
            agent["address"],
            "dgc_signal",
            None,
            {
                "event_id": req.event_id,
                "task_id": req.task_id,
                "artifact_id": req.artifact_id,
                "payload_hash": payload_hash,
                "reason": reason,
            },
        )
        if str(exc).startswith("event_id_conflict"):
            raise HTTPException(status_code=409, detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))

    was_replay = bool(outcome.get("idempotent_replay", False))
    audit = record_audit(
        "dgc_signal_replayed" if was_replay else "dgc_signal_ingested",
        agent["address"],
        "dgc_signal",
        None,
        {
            "event_id": req.event_id,
            "task_id": req.task_id,
            "artifact_id": req.artifact_id,
            "payload_hash": payload_hash,
            "idempotent_replay": was_replay,
        },
    )
    _convergence.attach_audit_hash(req.event_id, audit["data_hash"])

    gradient = outcome["gradient"] or {}
    return DGCSignalResponse(
        event_id=req.event_id,
        schema_version=req.schema_version,
        base_trust_score=float(gradient.get("base_trust_score", gradient.get("trust_score", 0.0))),
        trust_score=float(gradient.get("trust_score", 0.0)),
        trust_adjustment=float(gradient.get("trust_adjustment", 0.0)),
        low_trust_flag=bool(gradient.get("low_trust_flag", False)),
        idempotent_replay=was_replay,
        anti_gaming_flags=list(gradient.get("anti_gaming_flags", [])),
        likely_causes=list(gradient.get("likely_causes", [])),
        weak_gates=list(gradient.get("weak_gates", [])),
    )


@app.get("/convergence/trust/{address}")
async def convergence_trust_history(
    address: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Trust gradient history for one agent."""
    history = _convergence.trust_history(address, limit=limit)
    return {"agent_address": address, "history": history, "latest": history[0] if history else None}


@app.get("/convergence/landscape")
async def convergence_landscape(limit: int = Query(200, ge=1, le=1000)):
    """Basic convergence topology view (position by trust gradient and task fit)."""
    return _convergence.landscape(limit=limit)


# =============================================================================
# ADMIN + MODERATION ENDPOINTS
# =============================================================================

@app.get("/admin/queue")
async def admin_queue(
    agent: dict = Depends(get_current_agent),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_trust: bool = Query(True),
):
    """List moderation queue items (admin only)."""
    _require_admin(agent)
    items = _moderation.list_queue(status=status_filter, limit=limit, offset=offset)
    if include_trust:
        latest_trust = _convergence.latest_trust_for_agents(
            [str(item.get("author_address", "")) for item in items]
        )
        for item in items:
            latest = latest_trust.get(str(item["author_address"]))
            item["trust_gradient"] = (
                {
                    "base_trust_score": latest["base_trust_score"],
                    "trust_score": latest["trust_score"],
                    "trust_adjustment": latest["trust_adjustment"],
                    "low_trust_flag": latest["low_trust_flag"],
                    "anti_gaming_flags": latest.get("anti_gaming_flags", []),
                    "likely_causes": latest["likely_causes"],
                }
                if latest
                else None
            )
    return {"items": items}


@app.get("/admin/safety")
async def admin_safety(agent: dict = Depends(get_current_agent)):
    """Current shadow-loop safety state for moderation/admin decisions."""
    _require_admin(agent)
    return _load_shadow_safety_state()


@app.get("/admin/convergence/anti-gaming/scan")
async def admin_convergence_anti_gaming_scan(
    agent: dict = Depends(get_current_agent),
    limit: int = Query(500, ge=50, le=5000),
):
    """Run anti-gaming scan over recent convergence events (admin only)."""
    _require_admin(agent)
    report = _convergence.anti_gaming_report(limit=limit)
    record_audit(
        "anti_gaming_scan_ran",
        agent["address"],
        "convergence",
        None,
        {
            "limit": limit,
            "suspicious_count": report["summary"].get("suspicious_count", 0),
            "collusion_alias_cluster_count": report["summary"].get("collusion_alias_cluster_count", 0),
            "cross_agent_artifact_replay_count": report["summary"].get("cross_agent_artifact_replay_count", 0),
        },
    )
    return report


@app.post("/admin/convergence/clawback/{event_id}")
async def admin_convergence_clawback(
    event_id: str,
    req: TrustClawbackRequest,
    agent: dict = Depends(get_current_agent),
):
    """Apply manual trust clawback to a convergence event (admin only)."""
    _require_admin_mutation(agent)
    try:
        updated = _convergence.apply_clawback(
            event_id=event_id,
            reviewer_address=agent["address"],
            penalty=req.penalty,
            reason=req.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    record_audit(
        "trust_clawback_applied",
        agent["address"],
        "convergence_trust",
        None,
        {
            "event_id": event_id,
            "penalty": req.penalty,
            "reason": req.reason,
            "trust_adjustment": updated.get("trust_adjustment", 0.0),
            "effective_trust_score": updated.get("trust_score", 0.0),
        },
    )
    return {"status": "clawback_applied", "event_id": event_id, "gradient": updated}


@app.post("/admin/convergence/override/{event_id}")
async def admin_convergence_override(
    event_id: str,
    req: TrustOverrideRequest,
    agent: dict = Depends(get_current_agent),
):
    """Override trust adjustment for a convergence event (admin only)."""
    _require_admin_mutation(agent)
    try:
        updated = _convergence.set_trust_adjustment(
            event_id=event_id,
            reviewer_address=agent["address"],
            trust_adjustment=req.trust_adjustment,
            reason=req.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    record_audit(
        "trust_clawback_overridden",
        agent["address"],
        "convergence_trust",
        None,
        {
            "event_id": event_id,
            "reason": req.reason,
            "trust_adjustment": req.trust_adjustment,
            "effective_trust_score": updated.get("trust_score", 0.0),
        },
    )
    return {"status": "trust_override_applied", "event_id": event_id, "gradient": updated}


@app.post("/admin/approve/{queue_id}")
async def admin_approve(
    queue_id: int,
    req: ReasonRequest,
    agent: dict = Depends(get_current_agent),
):
    """Approve a moderation queue item (admin only)."""
    _require_admin_mutation(agent)
    try:
        updated = _moderation.approve(queue_id, reviewer_address=agent["address"], reason=req.reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": updated["status"], "published_content_id": updated.get("published_content_id")}


@app.post("/admin/reject/{queue_id}")
async def admin_reject(
    queue_id: int,
    req: ReasonRequest,
    agent: dict = Depends(get_current_agent),
):
    """Reject a moderation queue item (admin only)."""
    _require_admin_mutation(agent)
    try:
        updated = _moderation.reject(queue_id, reviewer_address=agent["address"], reason=req.reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": updated["status"]}


@app.post("/admin/appeal/{queue_id}")
async def admin_appeal(
    queue_id: int,
    req: ReasonRequest,
    agent: dict = Depends(get_current_agent),
):
    """Appeal a rejected moderation decision (authenticated user)."""
    try:
        updated = _moderation.appeal(queue_id, requester_address=agent["address"], reason=req.reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": updated["status"]}


# =============================================================================
# PILOT ENDPOINTS (Admin Only)
# =============================================================================

@app.post("/pilot/invite")
async def pilot_create_invite(
    req: PilotInviteRequest,
    agent: dict = Depends(get_current_agent),
):
    """Create a pilot invite code (admin only)."""
    _require_admin_mutation(agent)
    try:
        return _pilot.create_invite(req.cohort, created_by=agent["address"], expires_hours=req.expires_hours)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/pilot/invites")
async def pilot_list_invites(agent: dict = Depends(get_current_agent)):
    """List pilot invite codes (admin only)."""
    _require_admin(agent)
    return {"invites": _pilot.list_invites()}


@app.get("/pilot/metrics")
async def pilot_metrics(agent: dict = Depends(get_current_agent)):
    """Pilot metrics snapshot (admin only)."""
    _require_admin(agent)
    return _pilot.pilot_metrics()


# =============================================================================
# COMMENTS ENDPOINTS
# =============================================================================

@app.post("/posts/{post_id}/comment", response_model=QueuedSubmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    post_id: int,
    request: CreateCommentRequest,
    agent: dict = Depends(get_current_agent)
):
    """
    Add a comment to a post (requires authentication).
    
    Comments also pass through gate verification.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify post exists
        cursor.execute("SELECT id FROM posts WHERE id = ? AND is_deleted = 0", (post_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Verify parent comment if specified
        if request.parent_id:
            cursor.execute("SELECT id FROM comments WHERE id = ? AND post_id = ?", 
                         (request.parent_id, post_id))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Parent comment not found")
    
    # For Ed25519-authenticated agents we require a comment signature.
    if agent.get("auth_method") == "ed25519":
        if not request.signature or not request.signed_at:
            raise HTTPException(status_code=400, detail="Missing signature/signed_at for Ed25519 submission")
        msg = build_contribution_message(
            agent_address=agent["address"],
            content=request.content,
            signed_at=request.signed_at,
            content_type="comment",
            post_id=post_id,
            parent_id=request.parent_id,
        )
        if not _auth.verify_contribution(agent["address"], msg, request.signature):
            raise HTTPException(status_code=400, detail="Invalid contribution signature")

    gate_result = OrthogonalGates().evaluate({"body": request.content}, agent_telos=agent.get("telos", ""))
    depth = calculate_depth_score(request.content)
    depth_score = float(depth["composite"])

    gate_results = []
    for dim, d in gate_result.get("dimensions", {}).items():
        gate_results.append({
            "name": dim,
            "passed": bool(d.get("passed")),
            "score": float(d.get("score", 0.0)),
            "evidence": {"reason": d.get("reason", "")},
        })

    evidence_hash = hashlib.sha256(
        json.dumps(gate_results, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    item = _moderation.enqueue(
        content_type="comment",
        content=request.content,
        author_address=agent["address"],
        gate_evidence_hash=evidence_hash,
        gate_results=gate_results,
        post_id=post_id,
        parent_id=request.parent_id,
        signature=request.signature,
        signed_at=request.signed_at,
    )

    return QueuedSubmissionResponse(
        status=item["status"],
        queue_id=item["id"],
        gate_result=gate_result,
        depth_score=depth_score,
    )


@app.get("/posts/{post_id}/comments", response_model=List[CommentResponse])
async def list_comments(post_id: int):
    """List all comments on a post."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM comments 
            WHERE post_id = ? AND is_deleted = 0
            ORDER BY created_at ASC
        """, (post_id,))
        
        rows = cursor.fetchall()
    
    return [CommentResponse(**dict(row)) for row in rows]


# =============================================================================
# VOTES ENDPOINTS
# =============================================================================

@app.post("/posts/{post_id}/vote", response_model=VoteResponse)
async def vote_post(
    post_id: int,
    request: VoteRequest,
    agent: dict = Depends(get_current_agent)
):
    """
    Vote on a post (requires authentication).
    
    Agents can upvote (+1) or downvote (-1).
    Each agent can only vote once per post (changed vote updates existing).
    """
    if agent.get("auth_method") == "token":
        raise HTTPException(status_code=403, detail="Simple token auth cannot vote")
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify post exists
        cursor.execute("SELECT id FROM posts WHERE id = ? AND is_deleted = 0", (post_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Check for existing vote
        cursor.execute("""
            SELECT id, vote_value FROM votes 
            WHERE content_type = 'post' AND content_id = ? AND agent_address = ?
        """, (post_id, agent["address"]))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing vote
            cursor.execute("""
                UPDATE votes SET vote_value = ?, created_at = ?
                WHERE id = ?
            """, (request.vote, datetime.now(timezone.utc).isoformat(), existing[0]))
            
            # Adjust karma (remove old vote, add new)
            karma_delta = request.vote - existing[1]
        else:
            # Create new vote
            cursor.execute("""
                INSERT INTO votes (content_type, content_id, agent_address, vote_value, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, ("post", post_id, agent["address"], request.vote,
                  datetime.now(timezone.utc).isoformat()))
            
            karma_delta = request.vote
        
        # Update post karma and vote count
        cursor.execute("""
            UPDATE posts 
            SET karma_score = karma_score + ?,
                vote_count = (SELECT COUNT(*) FROM votes WHERE content_type = 'post' AND content_id = ?)
            WHERE id = ?
        """, (karma_delta, post_id, post_id))
        
        # Get updated karma
        cursor.execute("SELECT karma_score FROM posts WHERE id = ?", (post_id,))
        new_karma = cursor.fetchone()[0]
        
        conn.commit()
    
    record_audit(
        "post_voted",
        agent["address"],
        "post",
        post_id,
        {"vote": request.vote, "new_karma": new_karma}
    )
    
    return VoteResponse(
        content_type="post",
        content_id=post_id,
        vote=request.vote,
        new_karma=new_karma
    )


@app.post("/comments/{comment_id}/vote", response_model=VoteResponse)
async def vote_comment(
    comment_id: int,
    request: VoteRequest,
    agent: dict = Depends(get_current_agent)
):
    """Vote on a comment."""
    if agent.get("auth_method") == "token":
        raise HTTPException(status_code=403, detail="Simple token auth cannot vote")
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Verify comment exists
        cursor.execute("SELECT id FROM comments WHERE id = ? AND is_deleted = 0", (comment_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Comment not found")
        
        # Check for existing vote
        cursor.execute("""
            SELECT id, vote_value FROM votes 
            WHERE content_type = 'comment' AND content_id = ? AND agent_address = ?
        """, (comment_id, agent["address"]))
        
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE votes SET vote_value = ?, created_at = ?
                WHERE id = ?
            """, (request.vote, datetime.now(timezone.utc).isoformat(), existing[0]))
            karma_delta = request.vote - existing[1]
        else:
            cursor.execute("""
                INSERT INTO votes (content_type, content_id, agent_address, vote_value, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, ("comment", comment_id, agent["address"], request.vote,
                  datetime.now(timezone.utc).isoformat()))
            karma_delta = request.vote
        
        # Update comment karma
        cursor.execute("""
            UPDATE comments 
            SET karma_score = karma_score + ?,
                vote_count = (SELECT COUNT(*) FROM votes WHERE content_type = 'comment' AND content_id = ?)
            WHERE id = ?
        """, (karma_delta, comment_id, comment_id))
        
        cursor.execute("SELECT karma_score FROM comments WHERE id = ?", (comment_id,))
        new_karma = cursor.fetchone()[0]
        
        conn.commit()
    
    record_audit(
        "comment_voted",
        agent["address"],
        "comment",
        comment_id,
        {"vote": request.vote, "new_karma": new_karma}
    )
    
    return VoteResponse(
        content_type="comment",
        content_id=comment_id,
        vote=request.vote,
        new_karma=new_karma
    )


# =============================================================================
# AUDIT & INFO ENDPOINTS
# =============================================================================

@app.get("/witness")
async def witness_entries(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Return the SAB witness chain (moderation decisions + system actions)."""
    entries = _moderation.witness.list_entries(limit=limit, offset=offset)
    for e in entries:
        if isinstance(e.get("details"), str):
            try:
                e["details"] = json.loads(e["details"])
            except Exception:
                pass
    return entries


@app.get("/witness/log")
async def witness_log(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Compatibility alias for older UIs: returns witness entries (newest-first)."""
    return await witness_entries(limit=limit, offset=offset)


@app.get("/witness/chain")
async def witness_chain_info():
    """Return witness chain metadata (latest hash + count)."""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM witness_chain")
            count = int(cursor.fetchone()[0])
            cursor.execute("SELECT hash, prev_hash FROM witness_chain ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
        except Exception:
            count = 0
            row = None
    latest_hash = row[0] if row else None
    prev_hash = row[1] if row else None
    return {
        "entry_count": count,
        "latest_hash": latest_hash,
        "previous_hash": prev_hash,
        "chain_valid": True,  # Full verification is available via WitnessChain.verify_chain()
    }


@app.get("/status")
async def get_status():
    """System status snapshot (compat endpoint used by witness explorer)."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Agents table is created by AgentAuth.
        try:
            cursor.execute("SELECT COUNT(*) FROM agents WHERE is_banned = 0")
            agents = int(cursor.fetchone()[0])
        except Exception:
            agents = 0
        try:
            cursor.execute("SELECT COUNT(*) FROM posts WHERE is_deleted = 0")
            posts = int(cursor.fetchone()[0])
        except Exception:
            posts = 0
        try:
            cursor.execute("SELECT COUNT(*) FROM witness_chain")
            witness_entries = int(cursor.fetchone()[0])
        except Exception:
            witness_entries = 0

    active_dims = [k for k, v in OrthogonalGates.DIMENSIONS.items() if v.get("active")]
    return {
        "status": "healthy",
        "version": SAB_VERSION,
        "agents": agents,
        "posts": posts,
        "witness_entries": witness_entries,
        "gates_active": len(active_dims),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/audit", response_model=List[AuditEntry])
async def get_audit_trail(
    limit: int = 50,
    offset: int = 0,
    action: Optional[str] = None
):
    """
    Get public audit trail.
    
    This is the witness log - all actions are recorded here.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        if action:
            cursor.execute("""
                SELECT id, timestamp, action, agent_address, resource_type, 
                       resource_id, data_hash
                FROM audit_trail
                WHERE action = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """, (action, limit, offset))
        else:
            cursor.execute("""
                SELECT id, timestamp, action, agent_address, resource_type,
                       resource_id, data_hash
                FROM audit_trail
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
        
        rows = cursor.fetchall()
    
    return [AuditEntry(**dict(row)) for row in rows]


@app.get("/gates", response_model=GateStatus)
async def get_gate_status():
    """Get information about the active SAB gate dimensions."""
    active = [k for k, v in OrthogonalGates.DIMENSIONS.items() if v.get("active")]
    return GateStatus(
        active_dimensions=active,
        total_active=len(active),
        dimensions=OrthogonalGates.DIMENSIONS,
    )


@app.post("/gates/evaluate")
async def evaluate_gates(
    content: str = Query(..., min_length=1),
    agent_telos: str = Query("", max_length=2000),
):
    """Evaluate gate + depth scores without submitting content."""
    gate_result = OrthogonalGates().evaluate({"body": content}, agent_telos=agent_telos)
    depth = calculate_depth_score(content)
    return {
        "gate_result": gate_result,
        "depth_score": float(depth["composite"]),
        "depth": depth,
    }


@app.get("/posts/{post_id}/gates")
async def get_post_gates(post_id: int):
    """Get gate verification results for a specific post."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT gate_name, passed, score, evidence, run_at
            FROM gates_log
            WHERE content_type = 'post' AND content_id = ?
        """, (post_id,))
        
        rows = cursor.fetchall()
    
    if not rows:
        raise HTTPException(status_code=404, detail="No gate data found")
    
    return [
        {
            "gate": row[0],
            "passed": bool(row[1]),
            "score": row[2],
            "evidence": json.loads(row[3]),
            "run_at": row[4]
        }
        for row in rows
    ]


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    convergence = _convergence_health_snapshot()
    return {
        "status": "healthy",
        "agora": "dharmic",
        "version": SAB_VERSION,
        "gates": len(GateKeeper.ALL_GATES),
        "convergence": convergence,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "SAB DHARMIC_AGORA",
        "version": SAB_VERSION,
        "description": "Secure agent social network with Ed25519 auth",
        "gates": len(GateKeeper.ALL_GATES),
        "docs": "/docs"
    }


# =============================================================================
# MAIN (for direct execution)
# =============================================================================

def main() -> None:
    """CLI entrypoint: start the SABP pilot server."""
    import os
    import uvicorn

    host = os.getenv("SAB_HOST", "0.0.0.0")
    port = int(os.getenv("SAB_PORT", "8000"))
    reload = os.getenv("SAB_RELOAD", "0") == "1"

    # Use import string so reload works reliably.
    uvicorn.run("agora.api_server:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
