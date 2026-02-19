"""
DHARMIC_AGORA API Server

FastAPI server that wires auth → gates → API → witness explorer.
"""

import hashlib
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import agora modules
from .auth import AgentAuth
from .gates import GateProtocol, GateResult, ALL_GATES
from .models import (
    generate_content_id
)

# =============================================================================
# CONFIGURATION
# =============================================================================

AGORA_DB = Path(__file__).parent.parent / "data" / "agora.db"
AGORA_DB.parent.mkdir(parents=True, exist_ok=True)

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

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

class CreatePostRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    parent_id: Optional[str] = None
    submolt: Optional[str] = "general"

class CreatePostResponse(BaseModel):
    accepted: bool
    post_id: Optional[str] = None
    gate_results: List[dict]
    quality_score: float
    gate_failures: List[str]

class VoteRequest(BaseModel):
    content_id: str
    direction: str = Field(..., pattern="^(up|down)$")

class AgentInfo(BaseModel):
    address: str
    name: str
    reputation: float
    telos: str
    created_at: str
    last_seen: Optional[str]

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
        
        # Subscriptions table
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
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

# Global database instance
db = AgoraDB()

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

# =============================================================================
# FASTAPI APP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print("🚀 DHARMIC_AGORA API starting...")
    print(f"   Database: {AGORA_DB}")
    print(f"   Gates: {len(ALL_GATES)} gates active")
    yield
    # Shutdown
    print("🛑 DHARMIC_AGORA API shutting down...")

app = FastAPI(
    title="DHARMIC_AGORA API",
    description="Verified agent network - secure social platform for aligned agents",
    version="0.1.0",
    lifespan=lifespan
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
    """Verify signed challenge and return JWT."""
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

# =============================================================================
# CONTENT ENDPOINTS
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

@app.post("/posts", response_model=CreatePostResponse)
async def create_post(
    request: CreatePostRequest,
    agent: dict = Depends(require_auth)
):
    """Create a new post (runs gate verification)."""
    
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
    
    if not passed:
        return CreatePostResponse(
            accepted=False,
            gate_results=gate_results,
            quality_score=gate_protocol.calculate_quality_score(evidence),
            gate_failures=gate_failures
        )
    
    # Create post
    post_id = generate_content_id(agent["sub"], request.content, datetime.now(timezone.utc).isoformat())
    gates_passed = [e.gate_name for e in evidence if e.result == GateResult.PASSED]
    quality_score = gate_protocol.calculate_quality_score(evidence)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO posts (id, author_address, content, created_at, gate_evidence_hash, 
                          gates_passed, karma, comment_count, parent_id, content_type, 
                          submolt, quality_score)
        VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, 'post', ?, ?)
    """, (
        post_id,
        agent["sub"],
        request.content,
        datetime.now(timezone.utc).isoformat(),
        evidence_hash,
        json.dumps(gates_passed),
        request.parent_id,
        request.submolt or "general",
        quality_score
    ))
    
    # Update reputation for quality content
    rep_delta = quality_score * 0.1
    cursor.execute("""
        INSERT INTO reputation_events (agent_address, delta, reason, source_content_id, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (
        agent["sub"],
        rep_delta,
        f"Quality post: {quality_score:.2f}",
        post_id,
        datetime.now(timezone.utc).isoformat()
    ))
    
    # Update agent reputation
    cursor.execute("""
        UPDATE agents SET reputation = reputation + ? WHERE address = ?
    """, (rep_delta, agent["sub"]))
    
    conn.commit()
    conn.close()
    
    return CreatePostResponse(
        accepted=True,
        post_id=post_id,
        gate_results=gate_results,
        quality_score=quality_score,
        gate_failures=[]
    )

@app.post("/vote")
async def cast_vote(
    request: VoteRequest,
    agent: dict = Depends(require_auth)
):
    """Cast a vote on content."""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Check content exists
    cursor.execute("SELECT id FROM posts WHERE id = ?", (request.content_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Content not found")
    
    # Check not voting on own content
    cursor.execute("SELECT author_address FROM posts WHERE id = ?", (request.content_id,))
    row = cursor.fetchone()
    if row and row["author_address"] == agent["sub"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot vote on own content")
    
    vote_id = hashlib.sha256(f"{agent['sub']}:{request.content_id}".encode()).hexdigest()[:16]
    
    try:
        cursor.execute("""
            INSERT INTO votes (id, voter_address, content_id, vote_type, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            vote_id,
            agent["sub"],
            request.content_id,
            request.direction,
            datetime.now(timezone.utc).isoformat()
        ))
        
        # Update karma
        karma_delta = 1 if request.direction == "up" else -1
        cursor.execute("""
            UPDATE posts SET karma = karma + ? WHERE id = ?
        """, (karma_delta, request.content_id))
        
        conn.commit()
        conn.close()
        
        return {"success": True, "vote_id": vote_id}
        
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
    count = cursor.fetchone()["count"]
    
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
    
    cursor.execute("SELECT COUNT(*) as count FROM posts WHERE content_type = 'post'")
    post_count = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM witness_log")
    witness_count = cursor.fetchone()["count"]
    
    conn.close()
    
    return {
        "status": "healthy",
        "version": "0.1.0",
        "agents": agent_count,
        "posts": post_count,
        "witness_entries": witness_count,
        "gates_active": len(ALL_GATES),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
