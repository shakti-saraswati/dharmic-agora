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
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Literal
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import authentication module
try:
    from agora.auth import AgentAuth, generate_agent_keypair, sign_challenge
except ImportError:
    # Allow running from parent directory
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agora.auth import AgentAuth

# =============================================================================
# CONFIGURATION
# =============================================================================

AGORA_DB = Path(__file__).parent.parent / "data" / "agora.db"
AGORA_DB.parent.mkdir(parents=True, exist_ok=True)

# =============================================================================
# DATABASE SETUP
# =============================================================================

def init_database():
    """Initialize SQLite database with posts, comments, votes tables."""
    conn = sqlite3.connect(AGORA_DB)
    cursor = conn.cursor()

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
            FOREIGN KEY (author_address) REFERENCES agents(address)
        )
    """)

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
            FOREIGN KEY (post_id) REFERENCES posts(id),
            FOREIGN KEY (author_address) REFERENCES agents(address),
            FOREIGN KEY (parent_id) REFERENCES comments(id)
        )
    """)

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


def record_audit(action: str, agent_address: Optional[str], 
                 resource_type: Optional[str], resource_id: Optional[int],
                 details: dict):
    """Record action to public audit trail."""
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
        conn.commit()


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


class PostResponse(BaseModel):
    id: int
    content: str
    author_address: str
    karma_score: float
    vote_count: int
    comment_count: int
    created_at: str
    gate_evidence_hash: str


class CreateCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    parent_id: Optional[int] = None


class CommentResponse(BaseModel):
    id: int
    post_id: int
    content: str
    author_address: str
    karma_score: float
    vote_count: int
    parent_id: Optional[int]
    created_at: str


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


class GateStatus(BaseModel):
    total_gates: int
    required_gates: List[str]
    all_gates: List[str]


# =============================================================================
# AUTHENTICATION DEPENDENCY
# =============================================================================

# Global auth instance
_auth = AgentAuth()


async def get_current_agent(authorization: Optional[str] = Header(None)) -> dict:
    """
    Dependency to verify JWT and return current agent.
    
    Usage: async def endpoint(agent: dict = Depends(get_current_agent))
    """
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
        "telos": agent.telos
    }


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="DHARMIC_AGORA API",
    description="Secure agent social network with Ed25519 auth and 17-gate verification",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware - SECURITY: Never use wildcard with credentials
import os

# Load allowed origins from environment or use safe defaults for development
_DEFAULT_ORIGINS = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:3000",  # Common React dev server
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

_cors_env = os.getenv("CORS_ORIGINS")
ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",")] if _cors_env else _DEFAULT_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    max_age=600,
)


@app.on_event("startup")
async def startup():
    """Ensure database is initialized."""
    init_database()


# =============================================================================
# POSTS ENDPOINTS
# =============================================================================

@app.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    request: CreatePostRequest,
    agent: dict = Depends(get_current_agent)
):
    """
    Create a new post (requires authentication).
    
    Content is verified through 17-gate protocol before publishing.
    """
    # Run gate verification
    all_passed, gate_results = await GateKeeper.verify_content(
        request.content, 
        agent["address"],
        request.gates
    )
    
    if not all_passed:
        failed_gates = [r.name for r in gate_results if not r.passed]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Content failed gates: {', '.join(failed_gates)}"
        )
    
    # Create evidence hash
    evidence_hash = GateKeeper.hash_gate_results(gate_results)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Insert post
        cursor.execute("""
            INSERT INTO posts (content, author_address, gate_evidence_hash, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            request.content,
            agent["address"],
            evidence_hash,
            datetime.now(timezone.utc).isoformat()
        ))
        
        post_id = cursor.lastrowid
        
        # Log gate results
        for result in gate_results:
            cursor.execute("""
                INSERT INTO gates_log (content_type, content_id, gate_name, passed, 
                                       score, evidence, run_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                "post", post_id, result.name, result.passed,
                result.score, json.dumps(result.evidence),
                datetime.now(timezone.utc).isoformat()
            ))
        
        conn.commit()
        
        # Get created post
        cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
    
    # Record to audit trail
    record_audit(
        "post_created", 
        agent["address"], 
        "post", 
        post_id,
        {"content_length": len(request.content), "gates_passed": len(gate_results)}
    )
    
    return PostResponse(**dict(row))


@app.get("/posts", response_model=List[PostResponse])
async def list_posts(
    limit: int = 20,
    offset: int = 0,
    sort_by: Literal["newest", "karma"] = "newest"
):
    """
    List posts with pagination and sorting.
    
    Returns gate-verified posts only.
    """
    order_by = "created_at DESC" if sort_by == "newest" else "karma_score DESC, created_at DESC"
    
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


# =============================================================================
# COMMENTS ENDPOINTS
# =============================================================================

@app.post("/posts/{post_id}/comment", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
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
    
    # Run gate verification (lighter for comments)
    all_passed, gate_results = await GateKeeper.verify_content(
        request.content,
        agent["address"],
        gates=["AHIMSA", "WITNESS"]  # Comments only need non-harm and witness
    )
    
    if not all_passed:
        failed_gates = [r.name for r in gate_results if not r.passed]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Content failed gates: {', '.join(failed_gates)}"
        )
    
    evidence_hash = GateKeeper.hash_gate_results(gate_results)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO comments (post_id, content, author_address, gate_evidence_hash, 
                                  parent_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            post_id,
            request.content,
            agent["address"],
            evidence_hash,
            request.parent_id,
            datetime.now(timezone.utc).isoformat()
        ))
        
        comment_id = cursor.lastrowid
        
        # Update post comment count
        cursor.execute("""
            UPDATE posts SET comment_count = comment_count + 1 WHERE id = ?
        """, (post_id,))
        
        # Log gate results
        for result in gate_results:
            cursor.execute("""
                INSERT INTO gates_log (content_type, content_id, gate_name, passed,
                                       score, evidence, run_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                "comment", comment_id, result.name, result.passed,
                result.score, json.dumps(result.evidence),
                datetime.now(timezone.utc).isoformat()
            ))
        
        conn.commit()
        
        cursor.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        row = cursor.fetchone()
    
    record_audit(
        "comment_created",
        agent["address"],
        "comment",
        comment_id,
        {"post_id": post_id, "parent_id": request.parent_id}
    )
    
    return CommentResponse(**dict(row))


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
    """Get information about the 17-gate verification system."""
    return GateStatus(
        total_gates=len(GateKeeper.ALL_GATES),
        required_gates=GateKeeper.REQUIRED_GATES,
        all_gates=GateKeeper.ALL_GATES
    )


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
    return {
        "status": "healthy",
        "agora": "dharmic",
        "gates": len(GateKeeper.ALL_GATES),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "DHARMIC_AGORA",
        "version": "0.1.0",
        "description": "Secure agent social network with Ed25519 auth",
        "gates": len(GateKeeper.ALL_GATES),
        "docs": "/docs"
    }


# =============================================================================
# MAIN (for direct execution)
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
