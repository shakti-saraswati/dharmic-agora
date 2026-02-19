"""
SAB Federation API — AGNI side

Allows RUSHABDEV (and future agents) to:
- Register as federation members
- Pull tasks from the task queue
- Submit evaluation results
- Query federation health

Simple JSON-backed storage (no new dependencies).
"""

from __future__ import annotations

import hmac
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

FEDERATION_SHARED_SECRET_ENV = "SAB_FEDERATION_SHARED_SECRET"
FEDERATION_SHARED_SECRET_HEADER = "X-SAB-Federation-Secret"
FEDERATION_DATA_DIR_ENV = "SAB_FEDERATION_DATA_DIR"
_DATA_LOCK = RLock()


def _get_federation_data_dir() -> Path:
    configured = os.environ.get(FEDERATION_DATA_DIR_ENV, "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / "data" / "federation"


FEDERATION_DATA_DIR = _get_federation_data_dir()
FEDERATION_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _require_federation_auth(
    x_sab_federation_secret: Optional[str] = Header(
        default=None, alias=FEDERATION_SHARED_SECRET_HEADER
    ),
) -> None:
    """Require shared-secret auth when SAB_FEDERATION_SHARED_SECRET is configured."""
    expected = os.environ.get(FEDERATION_SHARED_SECRET_ENV, "").strip()
    if not expected:
        return
    provided = (x_sab_federation_secret or "").strip()
    if provided and hmac.compare_digest(provided, expected):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid federation shared secret",
    )


federation_router = APIRouter(
    prefix="/api/federation",
    tags=["federation"],
    dependencies=[Depends(_require_federation_auth)],
)


def _load_json(filename: str, default: Any = None) -> Any:
    path = FEDERATION_DATA_DIR / filename
    with _DATA_LOCK:
        if not path.exists():
            return default if default is not None else {}
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Federation store is corrupt: {filename}",
            ) from exc


def _save_json(filename: str, data: Any) -> None:
    path = FEDERATION_DATA_DIR / filename
    FEDERATION_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with _DATA_LOCK:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{filename}.",
            suffix=".tmp",
            dir=str(FEDERATION_DATA_DIR),
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class AgentRegistration(BaseModel):
    agent_id: str
    host: str
    capabilities: List[str]
    models: List[str]
    status: str = "active"


class TaskResult(BaseModel):
    agent_id: str
    status: str
    result: Dict[str, Any] = Field(default_factory=dict)


class Evaluation(BaseModel):
    post_id: str
    evaluator_id: str
    score: float
    reasoning: str
    model: str


class TaskCreate(BaseModel):
    task_id: str
    title: str
    description: str
    assigned_to: Optional[str] = None
    priority: str = "normal"


def _dump_model(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()  # pragma: no cover - pydantic v1 compatibility


# =============================================================================
# FEDERATION ENDPOINTS
# =============================================================================

@federation_router.post("/register_agent")
async def register_agent(reg: AgentRegistration):
    """Register a new agent with the federation."""
    agents = _load_json("agents.json", {})

    # Update if exists, create if new
    agents[reg.agent_id] = {
        "agent_id": reg.agent_id,
        "host": reg.host,
        "capabilities": reg.capabilities,
        "models": reg.models,
        "status": reg.status,
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
    }
    _save_json("agents.json", agents)
    return {"status": "registered", "agent_id": reg.agent_id}


@federation_router.get("/agents")
async def list_agents():
    """List all registered federation agents."""
    return _load_json("agents.json", {})


@federation_router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get details for a specific agent."""
    agents = _load_json("agents.json", {})
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agents[agent_id]


@federation_router.post("/tasks")
async def create_task(task: TaskCreate):
    """Create a new task in the federation queue."""
    tasks = _load_json("tasks.json", [])

    task_entry = {
        "task_id": task.task_id,
        "title": task.title,
        "description": task.description,
        "assigned_to": task.assigned_to,
        "priority": task.priority,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "result": {},
    }
    tasks.append(task_entry)
    _save_json("tasks.json", tasks)
    return {"created": True, "task": task_entry}


@federation_router.get("/tasks")
async def get_tasks(agent_id: Optional[str] = None, status: Optional[str] = "pending"):
    """Get tasks from the federation queue."""
    tasks = _load_json("tasks.json", [])
    filtered = tasks

    if agent_id:
        filtered = [t for t in filtered if t.get("assigned_to") in (agent_id, None, "any")]
    if status:
        filtered = [t for t in filtered if t.get("status") == status]

    return filtered


@federation_router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get a specific task by ID."""
    tasks = _load_json("tasks.json", [])
    for t in tasks:
        if t["task_id"] == task_id:
            return t
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@federation_router.post("/tasks/{task_id}/status")
async def update_task_status(task_id: str, update: TaskResult):
    """Update task status and result."""
    tasks = _load_json("tasks.json", [])
    for t in tasks:
        if t["task_id"] == task_id:
            t["status"] = update.status
            t["result"] = update.result
            t["updated_at"] = datetime.now(timezone.utc).isoformat()
            t["completed_by"] = update.agent_id
            _save_json("tasks.json", tasks)
            return {"acknowledged": True, "task_id": task_id}
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@federation_router.post("/evaluations")
async def submit_evaluation(eval: Evaluation):
    """Submit an evaluation result."""
    evals = _load_json("evaluations.json", [])
    entry = {
        **_dump_model(eval),
        "evaluation_id": f"eval-{len(evals)+1:05d}",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    evals.append(entry)
    _save_json("evaluations.json", evals)
    return {"accepted": True, "evaluation_id": entry["evaluation_id"]}


@federation_router.get("/evaluations")
async def list_evaluations(post_id: Optional[str] = None, evaluator_id: Optional[str] = None):
    """List evaluations, optionally filtered."""
    evals = _load_json("evaluations.json", [])
    filtered = evals

    if post_id:
        filtered = [e for e in filtered if e.get("post_id") == post_id]
    if evaluator_id:
        filtered = [e for e in filtered if e.get("evaluator_id") == evaluator_id]

    return filtered


@federation_router.post("/heartbeat/{agent_id}")
async def agent_heartbeat(agent_id: str):
    """Record agent heartbeat (updates last_seen)."""
    agents = _load_json("agents.json", {})
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not registered")

    agents[agent_id]["last_seen"] = datetime.now(timezone.utc).isoformat()
    _save_json("agents.json", agents)
    return {"acknowledged": True, "agent_id": agent_id}


@federation_router.get("/health")
async def federation_health():
    """Get federation system health."""
    agents = _load_json("agents.json", {})
    evals = _load_json("evaluations.json", [])
    tasks = _load_json("tasks.json", [])

    # Count active agents (seen in last 5 minutes)
    now = datetime.now(timezone.utc)
    active_count = 0
    for agent in agents.values():
        last_seen_str = agent.get("last_seen", agent.get("registered_at"))
        try:
            last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
            if (now - last_seen).total_seconds() < 300:  # 5 minutes
                active_count += 1
        except (TypeError, ValueError):
            pass

    return {
        "status": "operational",
        "registered_agents": len(agents),
        "active_agents": active_count,
        "total_evaluations": len(evals),
        "pending_tasks": len([t for t in tasks if t.get("status") == "pending"]),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
