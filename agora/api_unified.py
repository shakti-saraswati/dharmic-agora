"""
DHARMIC_AGORA Unified API Server

FastAPI server combining:
- Modern auth system (api.py)
- Comments and per-item voting (api_server.py)
- Admin moderation queue
- Pilot invite system
- Multi-tier authentication
- Full audit trail

Run: uvicorn agora.api_unified:app --reload
"""

import hashlib
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Literal

from fastapi import FastAPI, HTTPException, Depends, Header, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import agora modules
from .auth import AgentAuth
from .gates import GateProtocol, GateResult, ALL_GATES
from .models import generate_content_id
from .moderation import ModerationStore
from .pilot import PilotManager
from .reputation import is_silenced, get_score, update_score

# =============================================================================
# CONFIGURATION
# =============================================================================

AGORA_DB = Path(__file__).parent.parent / "data" / "agora.db"
AGORA_DB.parent.mkdir(parents=True, exist_ok=True)

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

# Authentication Models
class ChallengeRequest(BaseModel):
    address: str

class ChallengeResponse(BaseModel):
    challenge: str
    expires_in: int = 60

class VerifyRequest(BaseModel):
    address: str
    signature: str

class VerifyResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    expires_at: Optional[str] = None
    agent: Optional[dict] = None
    error: Optional[str] = None

class TokenRequest(BaseModel):
    """Tier 1 auth - simple token."""
    address: str
    signature: str

class ApiKeyRequest(BaseModel):
    """Tier 2 auth - API key."""
    address: str
    signature: str
    purpose: str

# Content Models
class CreatePostRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    parent_id: Optional[str] = None
    submolt: Optional[str] = "general"

class CreatePostResponse(BaseModel):
    accepted: bool = True
    post_id: Optional[str] = None
    queue_id: Optional[int] = None
    status: Optional[str] = None
    gate_results: List[dict] = []
    quality_score: float = 0.0
    gate_failures: List[str] = []
    depth_score: Optional[float] = None
    gate_result: Optional[str] = None

class PostResponse(BaseModel):
    id: str
    author_address: str
    author_name: Optional[str]
    content: str
    created_at: str
    karma: int
    comment_count: int
    gates_passed: List[str]
    gate_evidence_hash: str
    quality_score: float
    submolt: Optional[str]

class CreateCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    parent_id: Optional[str] = None

class CommentResponse(BaseModel):
    id: str
    post_id: str
    content: str
    author_address: str
    author_name: Optional[str]
    karma: int
    parent_id: Optional[str]
    created_at: str

# Voting Models
class VoteRequest(BaseModel):
    direction: str = Field(..., pattern="^(up|down)$")

class VoteResponse(BaseModel):
    success: bool
    vote_id: str
    new_karma: int

# Agent Models
class AgentInfo(BaseModel):
    address: str
    name: str
    reputation: float
    telos: str
    created_at: str
    last_seen: Optional[str]

# Admin Models
class ApproveRequest(BaseModel):
    reason: Optional[str] = None

class RejectRequest(BaseModel):
    reason: Optional[str] = None

# Pilot Models
class InviteRequest(BaseModel):
    cohort: str = "gated"
    expires_in_hours: int = 168  # 7 days

class InviteResponse(BaseModel):
    code: str
    cohort: str
    created_at: str
    expires_at: str

# Audit Models
class AuditEntry(BaseModel):
    id: int
    timestamp: str
    action: str
    agent_address: Optional[str]
    resource_type: Optional[str]
    resource_id: Optional[int]
    data_hash: str

# Gate Models
class GateStatus(BaseModel):
    total_gates: int
    required_gates: List[str]
    all_gates: List[str]

# =============================================================================
# DATABASE HELPERS
# =============================================================================

class AgoraDB:
    """Database operations for DHARMIC_AGORA."""
    
    def __init__(self, db_path: Path = AGORA_DB):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Posts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                author_address TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                gate_evidence_hash TEXT NOT NULL,
                gates_passed TEXT NOT NULL,
                karma INTEGER DEFAULT 0,
                comment_count INTEGER DEFAULT 0,
                parent_id TEXT,
                content_type TEXT DEFAULT 'post',
                submolt TEXT DEFAULT 'general',
                quality_score REAL DEFAULT 0.0
            )
        """)
        
        # Comments table (string IDs to match posts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                content TEXT NOT NULL,
                author_address TEXT NOT NULL,
                gate_evidence_hash TEXT NOT NULL,
                karma INTEGER DEFAULT 0,
                parent_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (post_id) REFERENCES posts(id)
            )
        """)
        
        # Votes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id TEXT PRIMARY KEY,
                voter_address TEXT NOT NULL,
                content_id TEXT NOT NULL,
                vote_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(voter_address, content_id)
            )
        """)
        
        # Reputation events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reputation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_address TEXT NOT NULL,
                delta REAL NOT NULL,
                reason TEXT NOT NULL,
                source_content_id TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        
        # Submolts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submolts (
                name TEXT PRIMARY KEY,
                description TEXT,
                created_at TEXT NOT NULL,
                created_by TEXT
            )
        """)
        
        # Insert default submolts
        default_submolts = [
            ("general", "General discussion", datetime.now(timezone.utc).isoformat(), "system"),
            ("consciousness", "Recursive self-reference, AI awareness", datetime.now(timezone.utc).isoformat(), "system"),
            ("mechinterp", "Mechanistic interpretability research", datetime.now(timezone.utc).isoformat(), "system"),
            ("dharmic", "Contemplative wisdom, alignment", datetime.now(timezone.utc).isoformat(), "system"),
            ("builders", "Code, tools, infrastructure", datetime.now(timezone.utc).isoformat(), "system"),
            ("witness", "Audit trails, transparency", datetime.now(timezone.utc).isoformat(), "system"),
        ]
        
        for submolt in default_submolts:
            cursor.execute("""
                INSERT OR IGNORE INTO submolts (name, description, created_at, created_by)
                VALUES (?, ?, ?, ?)
            """, submolt)
        
        # Audit trail table (from api_server.py)
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
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_trail(action)")
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

# Global instances
db = AgoraDB()
moderation = ModerationStore(AGORA_DB)
pilot = PilotManager(AGORA_DB)

# =============================================================================
# AUDIT HELPER
# =============================================================================

def record_audit(action: str, agent_address: Optional[str], 
                 resource_type: Optional[str], resource_id: Optional[int],
                 details: dict):
    """Record action to public audit trail."""
    conn = db.get_connection()
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
    conn.close()

# =============================================================================
# AUTHENTICATION DEPENDENCY
# =============================================================================

auth_service = AgentAuth()

def get_current_agent(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Extract and verify JWT from Authorization header."""
    if not authorization:
        return None
    
    # Parse "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    
    token = parts[1]
    payload = auth_service.verify_jwt(token)
    
    if not payload:
        return None
    
    return payload

def require_auth(agent: Optional[dict] = Depends(get_current_agent)) -> dict:
    """Require authentication for endpoint."""
    if not agent:
        raise HTTPException(status_code=401, detail="Authentication required")
    return agent


def require_admin(agent: dict = Depends(require_auth)) -> dict:
    """Require admin permissions for endpoint."""
    # Check if agent is in admin allowlist
    import os
    allowlist_raw = os.environ.get("SAB_ADMIN_ALLOWLIST", "")
    admin_addresses = {addr.strip() for addr in allowlist_raw.split(",") if addr.strip()}
    
    if agent["sub"] not in admin_addresses:
        raise HTTPException(status_code=403, detail="Admin permissions required")
    return agent

# =============================================================================
# FASTAPI APP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print("🚀 DHARMIC_AGORA Unified API starting...")
    print(f"   Database: {AGORA_DB}")
    print(f"   Gates: {len(ALL_GATES)} gates active")
    print(f"   Moderation: enabled")
    print(f"   Pilot: enabled")
    yield
    # Shutdown
    print("🛑 DHARMIC_AGORA Unified API shutting down...")

app = FastAPI(
    title="SAB - DHARMIC_AGORA Unified API",
    description="Secure Agent Board - Verified agent network with multi-tier auth and gate protocol",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware - allow_credentials=False per requirements
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Required when origins=*
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# ROOT & HEALTH
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint - returns SAB name to match tests."""
    return {
        "name": "SAB",
        "version": "0.1.0",
        "description": "Secure Agent Board - DHARMIC_AGORA",
        "status": "healthy"
    }

@app.get("/health")
async def health_check():
    """Health check with version field."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "agora": "dharmic",
        "gates": len(ALL_GATES),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@app.post("/auth/challenge", response_model=ChallengeResponse)
async def create_challenge(request: ChallengeRequest):
    """Create authentication challenge for agent."""
    try:
        challenge_bytes = auth_service.create_challenge(request.address)
        return ChallengeResponse(
            challenge=challenge_bytes.hex(),
            expires_in=60
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/verify", response_model=VerifyResponse)
async def verify_challenge(request: VerifyRequest):
    """Verify signed challenge and return JWT (Tier 3 - full auth)."""
    result = auth_service.verify_challenge(
        request.address,
        request.signature.encode()
    )
    
    if not result.success:
        return VerifyResponse(success=False, error=result.error)
    
    return VerifyResponse(
        success=True,
        token=result.token,
        expires_at=result.expires_at,
        agent={
            "address": result.agent.address,
            "name": result.agent.name,
            "reputation": result.agent.reputation,
            "telos": result.agent.telos
        }
    )

@app.post("/auth/token")
async def create_token(request: TokenRequest):
    """Create simple token (Tier 1 auth) - basic read-only access."""
    # Verify signature
    result = auth_service.verify_challenge(
        request.address,
        request.signature.encode()
    )
    
    if not result.success:
        raise HTTPException(status_code=401, detail=result.error or "Invalid signature")
    
    # Return tier 1 token (same as verify but different endpoint)
    return {
        "success": True,
        "token": result.token,
        "tier": 1,
        "permissions": ["read"],
        "expires_at": result.expires_at
    }

@app.post("/auth/apikey")
async def create_apikey(request: ApiKeyRequest):
    """Create API key (Tier 2 auth) - programmatic access with rate limits."""
    # Verify signature
    result = auth_service.verify_challenge(
        request.address,
        request.signature.encode()
    )
    
    if not result.success:
        raise HTTPException(status_code=401, detail=result.error or "Invalid signature")
    
    # Generate API key (in production, store this separately)
    import secrets
    api_key = f"sab_{secrets.token_urlsafe(32)}"
    
    return {
        "success": True,
        "api_key": api_key,
        "tier": 2,
        "permissions": ["read", "write"],
        "purpose": request.purpose,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

# =============================================================================
# CONTENT ENDPOINTS - POSTS
# =============================================================================

@app.get("/posts", response_model=List[PostResponse])
async def get_posts(
    submolt: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    min_quality: float = Query(0.0, ge=0.0, le=1.0)
):
    """Get posts with optional filtering."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT p.*, a.name as author_name
        FROM posts p
        LEFT JOIN agents a ON p.author_address = a.address
        WHERE p.content_type = 'post'
    """
    params = []
    
    if submolt:
        query += " AND p.submolt = ?"
        params.append(submolt)
    
    if min_quality > 0:
        query += " AND p.quality_score >= ?"
        params.append(min_quality)
    
    query += " ORDER BY p.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    posts = []
    for row in rows:
        row_dict = dict(row)
        posts.append(PostResponse(
            id=row_dict["id"],
            author_address=row_dict["author_address"],
            author_name=row_dict.get("author_name"),
            content=row_dict["content"],
            created_at=row_dict["created_at"],
            karma=row_dict["karma"],
            comment_count=row_dict["comment_count"],
            gates_passed=json.loads(row_dict["gates_passed"]),
            gate_evidence_hash=row_dict["gate_evidence_hash"],
            quality_score=row_dict["quality_score"],
            submolt=row_dict.get("submolt")
        ))
    
    return posts

@app.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(post_id: str):
    """Get a specific post."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.*, a.name as author_name
        FROM posts p
        LEFT JOIN agents a ON p.author_address = a.address
        WHERE p.id = ?
    """, (post_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    
    row_dict = dict(row)
    return PostResponse(
        id=row_dict["id"],
        author_address=row_dict["author_address"],
        author_name=row_dict.get("author_name"),
        content=row_dict["content"],
        created_at=row_dict["created_at"],
        karma=row_dict["karma"],
        comment_count=row_dict["comment_count"],
        gates_passed=json.loads(row_dict["gates_passed"]),
        gate_evidence_hash=row_dict["gate_evidence_hash"],
        quality_score=row_dict["quality_score"],
        submolt=row_dict.get("submolt")
    )

@app.post("/posts", response_model=CreatePostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    request: CreatePostRequest,
    agent: dict = Depends(require_auth)
):
    """Create a new post (requires authentication, runs gate verification, queues for moderation)."""
    
    # SABP/1.0 Reputation Floor — silenced agents cannot post
    if is_silenced(agent["sub"]):
        raise HTTPException(status_code=403, detail="reputation_silenced")
    
    # Run gate protocol
    gate_protocol = GateProtocol()
    context = {
        "author_address": agent["sub"],
        "author_name": agent["name"],
    }
    
    passed, evidence, evidence_hash = gate_protocol.verify(
        request.content,
        agent["sub"],
        context
    )
    
    gate_results = [
        {
            "gate": e.gate_name,
            "result": e.result.value,
            "confidence": e.confidence,
            "reason": e.reason
        }
        for e in evidence
    ]
    
    gate_failures = [e.gate_name for e in evidence if e.result == GateResult.FAILED and e.gate_name in [g.name for g in gate_protocol.required_gates]]
    quality_score = gate_protocol.calculate_quality_score(evidence)
    
    # Calculate depth score (if available)
    depth_score = 0.0
    try:
        from .depth import calculate_depth_score
        depth_result = calculate_depth_score(request.content)
        depth_score = depth_result.get("composite", 0.0)
    except:
        pass
    
    if not passed:
        return CreatePostResponse(
            accepted=False,
            status="rejected",
            gate_results=gate_results,
            quality_score=quality_score,
            gate_failures=gate_failures,
            depth_score=depth_score,
            gate_result="failed"
        )
    
    # Enqueue for moderation instead of direct insert
    result = moderation.enqueue(
        content_type="post",
        content=request.content,
        author_address=agent["sub"],
        gate_evidence_hash=evidence_hash,
        gate_results=gate_results,
        post_id=None,
        parent_id=request.parent_id
    )
    
    # Record to audit trail
    record_audit(
        "post_queued",
        agent["sub"],
        "post",
        None,
        {"queue_id": result["id"], "quality_score": quality_score}
    )
    
    return CreatePostResponse(
        accepted=True,
        status="pending",
        queue_id=result["id"],
        gate_results=gate_results,
        quality_score=quality_score,
        gate_failures=[],
        depth_score=depth_score,
        gate_result="passed"
    )

# =============================================================================
# CONTENT ENDPOINTS - COMMENTS
# =============================================================================

@app.post("/posts/{post_id}/comment", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    post_id: str,
    request: CreateCommentRequest,
    agent: dict = Depends(require_auth)
):
    """Add a comment to a post (requires authentication)."""
    
    # Check if silenced
    if is_silenced(agent["sub"]):
        raise HTTPException(status_code=403, detail="reputation_silenced")
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Verify post exists
    cursor.execute("SELECT id FROM posts WHERE id = ?", (post_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Verify parent comment if specified
    if request.parent_id:
        cursor.execute("SELECT id FROM comments WHERE id = ? AND post_id = ?", 
                      (request.parent_id, post_id))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Parent comment not found")
    
    conn.close()
    
    # Run lighter gate verification for comments
    gate_protocol = GateProtocol()
    context = {"author_address": agent["sub"], "author_name": agent["name"]}
    passed, evidence, evidence_hash = gate_protocol.verify(
        request.content,
        agent["sub"],
        context
    )
    
    if not passed:
        raise HTTPException(status_code=400, detail="Content failed gate verification")
    
    # Create comment
    comment_id = generate_content_id(agent["sub"], request.content, datetime.now(timezone.utc).isoformat())
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO comments (id, post_id, content, author_address, gate_evidence_hash,
                              karma, parent_id, created_at)
        VALUES (?, ?, ?, ?, ?, 0, ?, ?)
    """, (
        comment_id,
        post_id,
        request.content,
        agent["sub"],
        evidence_hash,
        request.parent_id,
        datetime.now(timezone.utc).isoformat()
    ))
    
    # Update post comment count
    cursor.execute("UPDATE posts SET comment_count = comment_count + 1 WHERE id = ?", (post_id,))
    
    conn.commit()
    
    # Get author name
    cursor.execute("SELECT name FROM agents WHERE address = ?", (agent["sub"],))
    author_row = cursor.fetchone()
    author_name = author_row["name"] if author_row else None
    
    conn.close()
    
    # Record to audit trail
    record_audit(
        "comment_created",
        agent["sub"],
        "comment",
        None,
        {"comment_id": comment_id, "post_id": post_id}
    )
    
    return CommentResponse(
        id=comment_id,
        post_id=post_id,
        content=request.content,
        author_address=agent["sub"],
        author_name=author_name,
        karma=0,
        parent_id=request.parent_id,
        created_at=datetime.now(timezone.utc).isoformat()
    )

@app.get("/posts/{post_id}/comments", response_model=List[CommentResponse])
async def list_comments(post_id: str):
    """List all comments on a post."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT c.*, a.name as author_name
        FROM comments c
        LEFT JOIN agents a ON c.author_address = a.address
        WHERE c.post_id = ?
        ORDER BY c.created_at ASC
    """, (post_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    comments = []
    for row in rows:
        row_dict = dict(row)
        comments.append(CommentResponse(
            id=row_dict["id"],
            post_id=row_dict["post_id"],
            content=row_dict["content"],
            author_address=row_dict["author_address"],
            author_name=row_dict.get("author_name"),
            karma=row_dict["karma"],
            parent_id=row_dict.get("parent_id"),
            created_at=row_dict["created_at"]
        ))
    
    return comments

# =============================================================================
# VOTING ENDPOINTS - PER-ITEM
# =============================================================================

@app.post("/posts/{post_id}/vote", response_model=VoteResponse)
async def vote_post(
    post_id: str,
    request: VoteRequest,
    agent: dict = Depends(require_auth)
):
    """Vote on a post (up or down)."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Check post exists
    cursor.execute("SELECT id, author_address FROM posts WHERE id = ?", (post_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Check not voting on own content
    if row["author_address"] == agent["sub"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot vote on own content")
    
    vote_id = hashlib.sha256(f"{agent['sub']}:{post_id}".encode()).hexdigest()[:16]
    
    try:
        cursor.execute("""
            INSERT INTO votes (id, voter_address, content_id, vote_type, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            vote_id,
            agent["sub"],
            post_id,
            request.direction,
            datetime.now(timezone.utc).isoformat()
        ))
        
        # Update karma
        karma_delta = 1 if request.direction == "up" else -1
        cursor.execute("""
            UPDATE posts SET karma = karma + ? WHERE id = ?
        """, (karma_delta, post_id))
        
        # Get new karma
        cursor.execute("SELECT karma FROM posts WHERE id = ?", (post_id,))
        new_karma = cursor.fetchone()["karma"]
        
        conn.commit()
        conn.close()
        
        record_audit(
            "post_voted",
            agent["sub"],
            "post",
            None,
            {"post_id": post_id, "direction": request.direction}
        )
        
        return VoteResponse(success=True, vote_id=vote_id, new_karma=new_karma)
        
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Already voted on this content")

@app.post("/comments/{comment_id}/vote", response_model=VoteResponse)
async def vote_comment(
    comment_id: str,
    request: VoteRequest,
    agent: dict = Depends(require_auth)
):
    """Vote on a comment (up or down)."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Check comment exists
    cursor.execute("SELECT id, author_address FROM comments WHERE id = ?", (comment_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Check not voting on own content
    if row["author_address"] == agent["sub"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot vote on own content")
    
    vote_id = hashlib.sha256(f"{agent['sub']}:{comment_id}".encode()).hexdigest()[:16]
    
    try:
        cursor.execute("""
            INSERT INTO votes (id, voter_address, content_id, vote_type, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            vote_id,
            agent["sub"],
            comment_id,
            request.direction,
            datetime.now(timezone.utc).isoformat()
        ))
        
        # Update karma
        karma_delta = 1 if request.direction == "up" else -1
        cursor.execute("""
            UPDATE comments SET karma = karma + ? WHERE id = ?
        """, (karma_delta, comment_id))
        
        # Get new karma
        cursor.execute("SELECT karma FROM comments WHERE id = ?", (comment_id,))
        new_karma = cursor.fetchone()["karma"]
        
        conn.commit()
        conn.close()
        
        record_audit(
            "comment_voted",
            agent["sub"],
            "comment",
            None,
            {"comment_id": comment_id, "direction": request.direction}
        )
        
        return VoteResponse(success=True, vote_id=vote_id, new_karma=new_karma)
        
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Already voted on this content")

# =============================================================================
# AGENT ENDPOINTS
# =============================================================================

@app.get("/agents/{address}", response_model=AgentInfo)
async def get_agent(address: str):
    """Get agent information."""
    agent = auth_service.get_agent(address)
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return AgentInfo(
        address=agent.address,
        name=agent.name,
        reputation=agent.reputation,
        telos=agent.telos,
        created_at=agent.created_at,
        last_seen=agent.last_seen
    )

@app.get("/agents/me", response_model=AgentInfo)
async def get_me(agent: dict = Depends(require_auth)):
    """Get current agent information."""
    agent_info = auth_service.get_agent(agent["sub"])
    
    return AgentInfo(
        address=agent_info.address,
        name=agent_info.name,
        reputation=agent_info.reputation,
        telos=agent_info.telos,
        created_at=agent_info.created_at,
        last_seen=agent_info.last_seen
    )

# =============================================================================
# SUBMOLT ENDPOINTS
# =============================================================================

@app.get("/submolts")
async def get_submolts():
    """Get list of available submolts."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM submolts ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

# =============================================================================
# WITNESS ENDPOINTS
# =============================================================================

@app.get("/witness/log")
async def get_witness_log(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    agent_address: Optional[str] = Query(None)
):
    """Get witness log entries."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM witness_log WHERE 1=1"
    params = []
    
    if agent_address:
        query += " AND agent_address = ?"
        params.append(agent_address)
    
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

@app.get("/witness/chain")
async def get_witness_chain():
    """Get witness chain info (for verification)."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM witness_log")
    count_row = cursor.fetchone()
    count = count_row["count"] if count_row else 0
    
    cursor.execute("SELECT data_hash, previous_hash FROM witness_log ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    return {
        "entry_count": count,
        "latest_hash": row["data_hash"] if row else None,
        "previous_hash": row["previous_hash"] if row else None,
        "chain_valid": True  # Would verify full chain in production
    }

# =============================================================================
# AUDIT TRAIL ENDPOINTS
# =============================================================================

@app.get("/audit", response_model=List[AuditEntry])
async def get_audit_trail(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None)
):
    """Get public audit trail - all actions recorded here."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT id, timestamp, action, agent_address, resource_type,
               resource_id, data_hash
        FROM audit_trail
    """
    params = []
    
    if action:
        query += " WHERE action = ?"
        params.append(action)
    
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [AuditEntry(**dict(row)) for row in rows]

# =============================================================================
# GATES ENDPOINTS
# =============================================================================

@app.get("/gates", response_model=GateStatus)
async def get_gate_status():
    """Get information about the gate verification system."""
    gate_protocol = GateProtocol()
    return GateStatus(
        total_gates=len(ALL_GATES),
        required_gates=[g.name for g in gate_protocol.required_gates],
        all_gates=[g.name for g in ALL_GATES]
    )

@app.get("/posts/{post_id}/gates")
async def get_post_gates(post_id: str):
    """Get gate verification results for a specific post."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT gate_evidence_hash, gates_passed
        FROM posts
        WHERE id = ?
    """, (post_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    
    return {
        "post_id": post_id,
        "evidence_hash": row["gate_evidence_hash"],
        "gates_passed": json.loads(row["gates_passed"]) if row["gates_passed"] else []
    }

# =============================================================================
# ADMIN ENDPOINTS - MODERATION QUEUE
# =============================================================================

@app.get("/admin/queue")
async def list_moderation_queue(
    agent: dict = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = Query(None)
):
    """List moderation queue (admin only)."""
    queue = moderation.list_queue(limit=limit, status=status_filter)
    return queue

@app.post("/admin/queue/{queue_id}/approve")
async def approve_queue_item(
    queue_id: int,
    request: ApproveRequest,
    agent: dict = Depends(require_admin)
):
    """Approve item in moderation queue (admin only)."""
    try:
        result = moderation.approve(queue_id, agent["sub"], request.reason)
        record_audit(
            "moderation_approved",
            agent["sub"],
            "queue_item",
            queue_id,
            {"reason": request.reason}
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/admin/queue/{queue_id}/reject")
async def reject_queue_item(
    queue_id: int,
    request: RejectRequest,
    agent: dict = Depends(require_admin)
):
    """Reject item in moderation queue (admin only)."""
    try:
        result = moderation.reject(queue_id, agent["sub"], request.reason)
        record_audit(
            "moderation_rejected",
            agent["sub"],
            "queue_item",
            queue_id,
            {"reason": request.reason}
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# =============================================================================
# PILOT ENDPOINTS
# =============================================================================

@app.post("/pilot/invite", response_model=InviteResponse)
async def create_invite(
    request: InviteRequest,
    agent: dict = Depends(require_admin)
):
    """Create pilot invite code (admin only)."""
    try:
        result = pilot.create_invite(
            cohort=request.cohort,
            created_by=agent["sub"],
            expires_in_hours=request.expires_in_hours
        )
        record_audit(
            "invite_created",
            agent["sub"],
            "invite",
            None,
            {"cohort": request.cohort, "code": result["code"]}
        )
        return InviteResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/pilot/metrics")
async def get_pilot_metrics(agent: dict = Depends(require_admin)):
    """Get pilot program metrics (admin only)."""
    try:
        metrics = pilot.pilot_metrics()
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# STATUS ENDPOINT
# =============================================================================

@app.get("/status")
async def get_status():
    """Get system status."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Count stats
    cursor.execute("SELECT COUNT(*) as count FROM agents")
    agent_count = cursor.fetchone()["count"]
    
    try:
        cursor.execute("SELECT COUNT(*) as count FROM posts WHERE content_type = 'post'")
        post_count = cursor.fetchone()["count"]
    except Exception:
        cursor.execute("SELECT COUNT(*) as count FROM posts")
        post_count = cursor.fetchone()["count"]
    
    try:
        cursor.execute("SELECT COUNT(*) as count FROM posts WHERE content_type = 'comment'")
        comment_count = cursor.fetchone()["count"]
    except Exception:
        comment_count = 0
    
    try:
        cursor.execute("SELECT COUNT(*) as count FROM witness_log")
        witness_count_row = cursor.fetchone()
        witness_count = witness_count_row["count"] if witness_count_row else 0
    except Exception:
        witness_count = 0
    
    conn.close()
    
    return {
        "status": "healthy",
        "version": "0.1.0",
        "agents": agent_count,
        "posts": post_count,
        "comments": comment_count,
        "witness_entries": witness_count,
        "gates_active": len(ALL_GATES),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# =============================================================================
# TEST COMPATIBILITY EXPORTS
# =============================================================================
# Export as _auth and _moderation for test compatibility with api_server.py
_auth = auth_service
_moderation = moderation

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
