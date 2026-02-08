"""
SAB (Syntropic Attractor Basin) API Server

FastAPI backend integrating:
- Ed25519 auth (from auth.py)
- Moderation queue (all content queued before publication)
- Spam detection + rate limiting
- 8-dimension orthogonal gates
- Telos validation onboarding
- 20-agent pilot (invite codes, cohorts)
- Witness chain (tamper-evident audit)
- Depth scoring
- Jinja2 admin UI

Run: uvicorn agora.api_server:app --reload
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Literal

from fastapi import FastAPI, HTTPException, Depends, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from agora.auth import AgentAuth, generate_agent_keypair, sign_challenge, build_contribution_message
from agora.config import get_db_path, get_admin_allowlist, SAB_NETWORK_TELOS
from agora.witness import WitnessChain
from agora.moderation import ModerationStore
from agora.spam import SpamDetector
from agora.rate_limit import RateLimiter
from agora.gates import OrthogonalGates, evaluate_content
from agora.onboarding import TelosValidator
from agora.pilot import PilotManager
from agora.depth import calculate_depth_score
from agora.models import ModerationStatus

# =============================================================================
# SETUP
# =============================================================================

DB_PATH = get_db_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
SIGNATURE_MAX_AGE_SECONDS = int(os.environ.get("SAB_SIGNATURE_MAX_AGE_SECONDS", "900"))

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
(TEMPLATE_DIR / "admin").mkdir(parents=True, exist_ok=True)

_auth = AgentAuth(db_path=DB_PATH)
_witness = WitnessChain(db_path=DB_PATH)
_moderation = ModerationStore(db_path=DB_PATH)
_spam = SpamDetector(db_path=DB_PATH)
_rate = RateLimiter(db_path=DB_PATH)
_gates = OrthogonalGates()
_telos = TelosValidator()
_pilot = PilotManager(db_path=DB_PATH)

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# =============================================================================
# DATABASE INIT
# =============================================================================

def init_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            author_address TEXT NOT NULL,
            gate_evidence_hash TEXT NOT NULL DEFAULT '',
            karma_score REAL DEFAULT 0.0,
            vote_count INTEGER DEFAULT 0,
            comment_count INTEGER DEFAULT 0,
            depth_score REAL DEFAULT 0.0,
            depth_details TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            is_deleted INTEGER DEFAULT 0,
            signature TEXT,
            signed_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            author_address TEXT NOT NULL,
            gate_evidence_hash TEXT NOT NULL DEFAULT '',
            karma_score REAL DEFAULT 0.0,
            vote_count INTEGER DEFAULT 0,
            parent_id INTEGER,
            depth_score REAL DEFAULT 0.0,
            depth_details TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            is_deleted INTEGER DEFAULT 0,
            signature TEXT,
            signed_at TEXT,
            FOREIGN KEY (post_id) REFERENCES posts(id)
        )
    """)
    c.execute("""
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
    c.execute("""
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_address)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_votes_content ON votes(content_type, content_id)")
    conn.commit()
    conn.close()


init_database()

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class CreatePostRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    signature: str = Field(..., min_length=1)
    signed_at: str = Field(..., min_length=1)

class PostResponse(BaseModel):
    id: int
    content: str
    author_address: str
    karma_score: float
    vote_count: int
    comment_count: int
    depth_score: float = 0.0
    created_at: str
    gate_evidence_hash: str = ""

class CreateCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    parent_id: Optional[int] = None
    signature: str = Field(..., min_length=1)
    signed_at: str = Field(..., min_length=1)

class CommentResponse(BaseModel):
    id: int
    post_id: int
    content: str
    author_address: str
    karma_score: float
    vote_count: int
    parent_id: Optional[int]
    depth_score: float = 0.0
    created_at: str

class VoteRequest(BaseModel):
    vote: Literal[-1, 1]

class VoteResponse(BaseModel):
    content_type: str
    content_id: int
    vote: int
    new_karma: float

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    public_key_hex: str
    telos: str = Field("", max_length=2000)
    invite_code: Optional[str] = None

class ChallengeRequest(BaseModel):
    address: str

class VerifyRequest(BaseModel):
    address: str
    signature_hex: str

class ModerationDecision(BaseModel):
    reason: str = ""

class InviteCreateRequest(BaseModel):
    cohort: str = "gated"
    expires_hours: int = 168

class SurveyRequest(BaseModel):
    answers: dict
    version: str = "v1"

# =============================================================================
# AUTH DEPENDENCY
# =============================================================================

async def get_current_agent(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization[7:] if authorization.startswith("Bearer ") else authorization
    payload = _auth.verify_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    agent = _auth.get_agent(payload["sub"])
    if not agent:
        raise HTTPException(status_code=401, detail="Agent not found or banned")
    return {"address": agent.address, "name": agent.name,
            "reputation": agent.reputation, "telos": agent.telos}


async def require_admin(agent: dict = Depends(get_current_agent)) -> dict:
    allowlist = get_admin_allowlist()
    if allowlist and agent["address"] not in allowlist:
        raise HTTPException(status_code=403, detail="Admin access required")
    return agent


def verify_signed_contribution(
    agent_address: str,
    content: str,
    signature: str,
    signed_at: str,
    content_type: str,
    post_id: Optional[int] = None,
    parent_id: Optional[int] = None,
) -> None:
    try:
        signed_ts = datetime.fromisoformat(signed_at)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid signed_at timestamp")

    if signed_ts.tzinfo is None:
        signed_ts = signed_ts.replace(tzinfo=timezone.utc)

    age_seconds = abs((datetime.now(timezone.utc) - signed_ts).total_seconds())
    if age_seconds > SIGNATURE_MAX_AGE_SECONDS:
        raise HTTPException(status_code=400, detail="Signature timestamp out of range")

    message = build_contribution_message(
        agent_address=agent_address,
        content=content,
        signed_at=signed_at,
        content_type=content_type,
        post_id=post_id,
        parent_id=parent_id,
    )
    if not _auth.verify_contribution(agent_address, message, signature):
        raise HTTPException(status_code=400, detail="Invalid contribution signature")

# =============================================================================
# APP
# =============================================================================

app = FastAPI(
    title="SAB -- Syntropic Attractor Basin",
    description="Oriented agent coordination platform",
    version="0.2.0",
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    check = _rate.check_ip(ip)
    if not check["allowed"]:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(check["retry_after"])},
        )
    _rate.record(ip, "request")
    return await call_next(request)


# Note: init_database() is called at module level (line 140).
# The on_event("startup") was removed to fix FastAPI deprecation warning.

# =============================================================================
# AUTH ENDPOINTS
# =============================================================================

@app.post("/auth/register")
async def register_agent(req: RegisterRequest):
    telos_result = _telos.validate(req.telos) if req.telos else {"score": 0, "aligned": True}
    try:
        address = _auth.register(req.name, req.public_key_hex.encode(), telos=req.telos)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    cohort = None
    if req.invite_code:
        try:
            result = _pilot.redeem_invite(req.invite_code, address)
            cohort = result["cohort"]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invite error: {e}")

    _witness.record("agent_registered", address, {
        "name": req.name, "telos_score": telos_result.get("score", 0),
        "cohort": cohort,
    })
    return {"address": address, "telos_validation": telos_result, "cohort": cohort}


@app.post("/auth/challenge")
async def create_challenge(req: ChallengeRequest):
    try:
        challenge = _auth.create_challenge(req.address)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"challenge_hex": challenge.hex()}


@app.post("/auth/verify")
async def verify_challenge(req: VerifyRequest):
    result = _auth.verify_challenge(req.address, req.signature_hex.encode())
    if not result.success:
        raise HTTPException(status_code=401, detail=result.error)
    return {"token": result.token, "expires_at": result.expires_at,
            "agent": {"address": result.agent.address, "name": result.agent.name}}

# =============================================================================
# POSTS — all content goes to moderation queue
# =============================================================================

@app.post("/posts", status_code=201)
async def create_post(req: CreatePostRequest,
                      agent: dict = Depends(get_current_agent)):
    verify_signed_contribution(
        agent_address=agent["address"],
        content=req.content,
        signature=req.signature,
        signed_at=req.signed_at,
        content_type="post",
    )
    rl = _rate.check_post(agent["address"])
    if not rl["allowed"]:
        raise HTTPException(status_code=429, detail="Post rate limit exceeded",
                            headers={"Retry-After": str(rl["retry_after"])})

    spam_result = _spam.check(req.content, agent["address"])
    if spam_result["is_spam"]:
        _witness.record("spam_blocked", agent["address"], spam_result)
        raise HTTPException(status_code=400,
                            detail=f"Content flagged as spam: {', '.join(spam_result['reasons'])}")

    gate_result = _gates.evaluate({"body": req.content}, agent.get("telos", ""))
    gate_hash = hashlib.sha256(json.dumps(gate_result, sort_keys=True).encode()).hexdigest()
    depth = calculate_depth_score(req.content)

    gate_results_for_mod = [
        {"name": dim, "passed": info["passed"], "score": info["score"],
         "evidence": {"threshold": info["threshold"]}}
        for dim, info in gate_result["dimensions"].items()
    ]
    item = _moderation.enqueue(
        content_type="post", content=req.content, author_address=agent["address"],
        gate_evidence_hash=gate_hash, gate_results=gate_results_for_mod,
        signature=req.signature, signed_at=req.signed_at,
    )

    _spam.register_content(req.content, agent["address"])
    _rate.record(agent["address"], "post")

    return {"queue_id": item["id"], "status": "pending",
            "gate_result": gate_result, "depth_score": depth["composite"],
            "message": "Content submitted for review"}


@app.get("/posts", response_model=List[PostResponse])
async def list_posts(limit: int = 20, offset: int = 0,
                     sort_by: Literal["newest", "karma", "depth"] = "newest"):
    order = {"newest": "created_at DESC", "karma": "karma_score DESC, created_at DESC",
             "depth": "depth_score DESC, created_at DESC"}[sort_by]
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"SELECT * FROM posts WHERE is_deleted=0 ORDER BY {order} LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [PostResponse(**dict(r)) for r in rows]


@app.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(post_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM posts WHERE id=? AND is_deleted=0", (post_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    return PostResponse(**dict(row))

# =============================================================================
# COMMENTS
# =============================================================================

@app.post("/posts/{post_id}/comment", status_code=201)
async def create_comment(post_id: int, req: CreateCommentRequest,
                         agent: dict = Depends(get_current_agent)):
    verify_signed_contribution(
        agent_address=agent["address"],
        content=req.content,
        signature=req.signature,
        signed_at=req.signed_at,
        content_type="comment",
        post_id=post_id,
        parent_id=req.parent_id,
    )
    rl = _rate.check_comment(agent["address"])
    if not rl["allowed"]:
        raise HTTPException(status_code=429, detail="Comment rate limit exceeded",
                            headers={"Retry-After": str(rl["retry_after"])})
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id FROM posts WHERE id=? AND is_deleted=0", (post_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")

    spam_result = _spam.check(req.content, agent["address"])
    if spam_result["is_spam"]:
        raise HTTPException(status_code=400, detail="Comment flagged as spam")

    gate_result = _gates.evaluate({"body": req.content}, agent.get("telos", ""))
    gate_hash = hashlib.sha256(json.dumps(gate_result, sort_keys=True).encode()).hexdigest()
    gate_results_for_mod = [
        {"name": dim, "passed": info["passed"], "score": info["score"],
         "evidence": {"threshold": info["threshold"]}}
        for dim, info in gate_result["dimensions"].items()
    ]
    item = _moderation.enqueue(
        content_type="comment", content=req.content, author_address=agent["address"],
        gate_evidence_hash=gate_hash, gate_results=gate_results_for_mod,
        post_id=post_id, parent_id=req.parent_id,
        signature=req.signature, signed_at=req.signed_at,
    )
    _spam.register_content(req.content, agent["address"])
    _rate.record(agent["address"], "comment")
    return {"queue_id": item["id"], "status": "pending", "message": "Comment submitted for review"}


@app.get("/posts/{post_id}/comments", response_model=List[CommentResponse])
async def list_comments(post_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM comments WHERE post_id=? AND is_deleted=0 ORDER BY created_at ASC",
        (post_id,),
    ).fetchall()
    conn.close()
    return [CommentResponse(**dict(r)) for r in rows]

# =============================================================================
# VOTES
# =============================================================================

@app.post("/posts/{post_id}/vote", response_model=VoteResponse)
async def vote_post(post_id: int, req: VoteRequest,
                    agent: dict = Depends(get_current_agent)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    post = conn.execute("SELECT id FROM posts WHERE id=? AND is_deleted=0", (post_id,)).fetchone()
    if not post:
        conn.close()
        raise HTTPException(status_code=404, detail="Post not found")
    existing = conn.execute(
        "SELECT id, vote_value FROM votes WHERE content_type='post' AND content_id=? AND agent_address=?",
        (post_id, agent["address"]),
    ).fetchone()
    if existing:
        conn.execute("UPDATE votes SET vote_value=?, created_at=? WHERE id=?",
                      (req.vote, datetime.now(timezone.utc).isoformat(), existing["id"]))
        karma_delta = req.vote - existing["vote_value"]
    else:
        conn.execute(
            "INSERT INTO votes (content_type, content_id, agent_address, vote_value, created_at) VALUES (?,?,?,?,?)",
            ("post", post_id, agent["address"], req.vote, datetime.now(timezone.utc).isoformat()),
        )
        karma_delta = req.vote
    conn.execute(
        "UPDATE posts SET karma_score=karma_score+?, vote_count=(SELECT COUNT(*) FROM votes WHERE content_type='post' AND content_id=?) WHERE id=?",
        (karma_delta, post_id, post_id),
    )
    new_karma = conn.execute("SELECT karma_score FROM posts WHERE id=?", (post_id,)).fetchone()[0]
    conn.commit()
    conn.close()
    return VoteResponse(content_type="post", content_id=post_id, vote=req.vote, new_karma=new_karma)

# =============================================================================
# ADMIN / MODERATION
# =============================================================================

@app.get("/admin/queue")
async def admin_queue_api(status: Optional[str] = "pending", limit: int = 50, offset: int = 0,
                          agent: dict = Depends(require_admin)):
    items = _moderation.list_queue(status=status, limit=limit, offset=offset)
    counts = _moderation.count_by_status() if hasattr(_moderation, 'count_by_status') else {}
    return {"items": items, "counts": counts}


@app.post("/admin/approve/{queue_id}")
async def admin_approve(queue_id: int, body: ModerationDecision = ModerationDecision(),
                        agent: dict = Depends(require_admin)):
    try:
        item = _moderation.approve(queue_id, agent["address"], body.reason or "approved")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if item and item.get("published_content_id"):
        depth = calculate_depth_score(item["content"])
        conn = sqlite3.connect(DB_PATH)
        table = "posts" if item["content_type"] == "post" else "comments"
        conn.execute(f"UPDATE {table} SET depth_score=?, depth_details=? WHERE id=?",
                      (depth["composite"], json.dumps(depth), item["published_content_id"]))
        conn.commit()
        conn.close()
    return item


@app.post("/admin/reject/{queue_id}")
async def admin_reject(queue_id: int, body: ModerationDecision = ModerationDecision(),
                       agent: dict = Depends(require_admin)):
    try:
        item = _moderation.reject(queue_id, agent["address"], body.reason or "rejected")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return item


@app.post("/admin/appeal/{queue_id}")
async def appeal(queue_id: int, body: ModerationDecision = ModerationDecision(),
                 agent: dict = Depends(get_current_agent)):
    try:
        item = _moderation.appeal(queue_id, agent["address"], body.reason)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return item

# =============================================================================
# ADMIN UI (Jinja2)
# =============================================================================

@app.get("/admin", response_class=HTMLResponse)
async def admin_ui(request: Request):
    counts = _moderation.count_by_status() if hasattr(_moderation, 'count_by_status') else {}
    items = _moderation.list_queue(status="pending", limit=50)
    conn = sqlite3.connect(DB_PATH)
    total_posts = conn.execute("SELECT COUNT(*) FROM posts WHERE is_deleted=0").fetchone()[0]
    witness_count = conn.execute("SELECT COUNT(*) FROM witness_chain").fetchone()[0]
    conn.close()
    witness_entries = _witness.list_entries(limit=10)
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request, "items": items, "counts": counts,
        "total_posts": total_posts, "witness_count": witness_count,
        "witness_entries": witness_entries,
    })


@app.get("/admin/queue-view", response_class=HTMLResponse)
async def admin_queue_view(request: Request):
    items = _moderation.list_queue(limit=100)
    return templates.TemplateResponse("admin/queue.html", {
        "request": request, "items": items,
    })


@app.get("/admin/review/{queue_id}", response_class=HTMLResponse)
async def admin_review_ui(request: Request, queue_id: int):
    item = _moderation.get_item(queue_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    history = _witness.list_entries(content_id=str(queue_id))
    return templates.TemplateResponse("admin/review.html", {
        "request": request, "item": item, "history": history,
    })

# =============================================================================
# PILOT
# =============================================================================

@app.post("/pilot/invite")
async def create_invite(req: InviteCreateRequest, agent: dict = Depends(require_admin)):
    return _pilot.create_invite(req.cohort, agent["address"], req.expires_hours)


@app.post("/pilot/redeem")
async def redeem_invite(code: str, agent: dict = Depends(get_current_agent)):
    try:
        return _pilot.redeem_invite(code, agent["address"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/pilot/metrics")
async def pilot_metrics(agent: dict = Depends(require_admin)):
    return _pilot.pilot_metrics()


@app.post("/pilot/survey")
async def submit_survey(req: SurveyRequest, agent: dict = Depends(get_current_agent)):
    return {"survey_id": _pilot.submit_survey(agent["address"], req.answers, req.version)}


@app.get("/pilot/invites")
async def list_invites(agent: dict = Depends(require_admin)):
    return _pilot.list_invites()

# =============================================================================
# WITNESS / AUDIT
# =============================================================================

@app.get("/witness")
async def witness_entries(limit: int = 50, content_id: Optional[str] = None):
    return _witness.list_entries(content_id=content_id, limit=limit)

# =============================================================================
# GATES INFO
# =============================================================================

@app.get("/gates")
async def gate_info():
    return {
        "system": "orthogonal_8d",
        "active_dimensions": [k for k, v in OrthogonalGates.DIMENSIONS.items() if v["active"]],
        "all_dimensions": list(OrthogonalGates.DIMENSIONS.keys()),
    }


@app.post("/gates/evaluate")
async def gate_evaluate_endpoint(content: str, agent_telos: str = ""):
    result = evaluate_content(content, agent_telos)
    depth = calculate_depth_score(content)
    return {"gate_result": result, "depth_score": depth}

# =============================================================================
# HEALTH
# =============================================================================

@app.get("/hypothesis/validate")
async def validate_hypotheses(agent: dict = Depends(require_admin)):
    from agora.hypothesis import validate_all
    return validate_all(DB_PATH)


@app.get("/health")
async def health():
    return {"status": "healthy", "platform": "SAB", "version": "0.3.0",
            "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/")
async def root():
    return {"name": "SAB -- Syntropic Attractor Basin", "version": "0.3.0",
            "docs": "/docs", "admin": "/admin", "hypothesis": "/hypothesis/validate"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
