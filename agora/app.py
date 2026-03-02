#!/usr/bin/env python3
"""
SAB spec sprint application surface.

Run with:
    uvicorn agora.app:app --reload
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from .config import SAB_VERSION, get_db_path
from .gates import ALL_GATES, GateResult, calculate_quality, verify_content

try:
    from nacl.encoding import HexEncoder
    from nacl.exceptions import BadSignatureError
    from nacl.signing import SigningKey, VerifyKey
except ImportError as exc:  # pragma: no cover - runtime safety
    raise RuntimeError("PyNaCl is required for agora.app") from exc


DEFAULT_SPARK_DB = get_db_path().with_name("spark.db")
SPARK_DB = Path(os.getenv("SAB_SPARK_DB_PATH", str(DEFAULT_SPARK_DB)))
SYSTEM_KEY_PATH = Path(
    os.getenv(
        "SAB_SYSTEM_WITNESS_KEY",
        str(SPARK_DB.with_name(".sab_system_ed25519.key")),
    )
)
CANON_QUORUM = int(os.getenv("SAB_CANON_QUORUM", "3"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_or_create_system_signing_key(path: Path) -> SigningKey:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            raise RuntimeError(f"System key file is empty: {path}")
        return SigningKey(raw.encode(), encoder=HexEncoder)

    key = SigningKey.generate()
    path.write_text(key.encode(encoder=HexEncoder).decode(), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        # Non-fatal on filesystems that do not support chmod semantics.
        pass
    return key


SYSTEM_SIGNING_KEY = _load_or_create_system_signing_key(SYSTEM_KEY_PATH)
SYSTEM_VERIFY_KEY_HEX = SYSTEM_SIGNING_KEY.verify_key.encode(encoder=HexEncoder).decode()


@contextmanager
def _db() -> sqlite3.Connection:
    SPARK_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SPARK_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, col_name: str, col_def: str) -> None:
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cursor.fetchall()}
    if col_name not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")


def init_db() -> None:
    with _db() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                public_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                witness_count INTEGER DEFAULT 0,
                witness_accuracy REAL DEFAULT 0.0
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sparks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                content_type TEXT NOT NULL,
                author_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                gate_scores TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('spark', 'canon', 'compost')),
                rv_contraction REAL,
                composite_score REAL DEFAULT 0.0
            )
            """
        )
        _ensure_column(conn, "sparks", "rv_contraction", "rv_contraction REAL")
        _ensure_column(conn, "sparks", "composite_score", "composite_score REAL DEFAULT 0.0")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sparks_status_created ON sparks(status, created_at DESC)"
        )

        # Note: auth.py uses a different `challenges` table for login challenges.
        # We keep spark-pressure challenges separate to avoid schema collisions.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS spark_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spark_id INTEGER NOT NULL,
                challenger_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                resolution TEXT NOT NULL CHECK (resolution IN ('pending', 'sustained', 'rejected'))
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_spark_challenges_spark ON spark_challenges(spark_id, created_at DESC)"
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS witness_chain (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spark_id INTEGER,
                witness_id TEXT NOT NULL,
                signature TEXT NOT NULL,
                action TEXT NOT NULL,
                payload TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                prev_hash TEXT,
                hash TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_witness_chain_spark ON witness_chain(spark_id, id ASC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_witness_chain_witness ON witness_chain(witness_id, id DESC)"
        )


def _system_sign(payload: Dict[str, Any]) -> str:
    return SYSTEM_SIGNING_KEY.sign(_canonical_bytes(payload)).signature.hex()


def _message_for_submit(author_id: str, content_sha256: str) -> bytes:
    return _canonical_bytes(
        {
            "kind": "spark_submit",
            "author_id": author_id,
            "content_sha256": content_sha256,
        }
    )


def _message_for_challenge(spark_id: int, challenger_id: str, content_sha256: str) -> bytes:
    return _canonical_bytes(
        {
            "kind": "spark_challenge",
            "spark_id": spark_id,
            "challenger_id": challenger_id,
            "content_sha256": content_sha256,
        }
    )


def _message_for_witness(spark_id: int, witness_id: str, action: str, payload_sha256: str) -> bytes:
    return _canonical_bytes(
        {
            "kind": "witness_attestation",
            "spark_id": spark_id,
            "witness_id": witness_id,
            "action": action,
            "payload_sha256": payload_sha256,
        }
    )


def _verify_agent_signature(conn: sqlite3.Connection, agent_id: str, message: bytes, signature_hex: str) -> None:
    row = conn.execute("SELECT public_key FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")

    public_key_hex = str(row["public_key"])
    try:
        verify_key = VerifyKey(public_key_hex.encode(), encoder=HexEncoder)
        verify_key.verify(message, bytes.fromhex(signature_hex))
    except (BadSignatureError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid Ed25519 signature")


def _append_witness(
    conn: sqlite3.Connection,
    *,
    spark_id: Optional[int],
    witness_id: str,
    action: str,
    payload: Dict[str, Any],
    signature_hex: str,
) -> Dict[str, Any]:
    timestamp = _utc_now()
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    prev_row = conn.execute(
        "SELECT hash FROM witness_chain WHERE spark_id IS ? ORDER BY id DESC LIMIT 1",
        (spark_id,),
    ).fetchone()
    prev_hash = str(prev_row["hash"]) if prev_row else "genesis"

    unhashed_entry = {
        "spark_id": spark_id,
        "witness_id": witness_id,
        "signature": signature_hex,
        "action": action,
        "payload": payload_json,
        "timestamp": timestamp,
        "prev_hash": prev_hash,
    }
    entry_hash = _sha256_hex(_canonical_bytes(unhashed_entry))

    conn.execute(
        """
        INSERT INTO witness_chain
            (spark_id, witness_id, signature, action, payload, timestamp, prev_hash, hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (spark_id, witness_id, signature_hex, action, payload_json, timestamp, prev_hash, entry_hash),
    )

    return {
        **unhashed_entry,
        "hash": entry_hash,
    }


def _load_gate_scores(raw: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"dimensions": {}, "composite": 0.0}
    if not isinstance(parsed, dict):
        return {"dimensions": {}, "composite": 0.0}
    return parsed


def _build_gate_payload(evidence: List[Any], evidence_hash: str) -> Dict[str, Any]:
    dimensions: Dict[str, Any] = {}
    for item in evidence:
        if item.result == GateResult.PASSED:
            score = float(item.confidence)
        elif item.result == GateResult.WARNING:
            score = float(item.confidence) * 0.5
        else:
            score = 0.0
        dimensions[item.gate_name] = {
            "score": round(max(0.0, min(1.0, score)), 6),
            "result": item.result.value,
            "reason": item.reason,
        }

    composite = round(float(calculate_quality(evidence)), 6)
    ahimsa_state = dimensions.get("ahimsa", {}).get("result", "passed")
    return {
        "dimensions": dimensions,
        "composite": composite,
        "evidence_hash": evidence_hash,
        "ahimsa_passed": ahimsa_state != "failed",
        "rv_contraction": None,  # integration point; to be wired to external R_V measurement service
        "rv_measurement_state": "stubbed",
    }


def _spark_counts_for_author(conn: sqlite3.Connection, author_id: str) -> Dict[str, int]:
    now = datetime.now(timezone.utc)
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    one_day_ago = (now - timedelta(days=1)).isoformat()
    hour_count = int(
        conn.execute(
            "SELECT COUNT(*) AS c FROM sparks WHERE author_id = ? AND created_at >= ?",
            (author_id, one_hour_ago),
        ).fetchone()["c"]
    )
    day_count = int(
        conn.execute(
            "SELECT COUNT(*) AS c FROM sparks WHERE author_id = ? AND created_at >= ?",
            (author_id, one_day_ago),
        ).fetchone()["c"]
    )
    return {"hour": hour_count, "day": day_count}


def _verify_chain_rows(rows: List[sqlite3.Row]) -> bool:
    prev_hash = "genesis"
    for row in rows:
        material = {
            "spark_id": row["spark_id"],
            "witness_id": row["witness_id"],
            "signature": row["signature"],
            "action": row["action"],
            "payload": row["payload"],
            "timestamp": row["timestamp"],
            "prev_hash": row["prev_hash"],
        }
        expected_hash = _sha256_hex(_canonical_bytes(material))
        if row["prev_hash"] != prev_hash:
            return False
        if row["hash"] != expected_hash:
            return False
        prev_hash = row["hash"]
    return True


def _promote_if_quorum(conn: sqlite3.Connection, spark_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT status FROM sparks WHERE id = ?", (spark_id,)).fetchone()
    if row is None:
        return None
    if str(row["status"]) == "canon":
        return None

    witnesses = conn.execute(
        """
        SELECT DISTINCT witness_id
        FROM witness_chain
        WHERE spark_id = ? AND action IN ('affirm', 'canon_affirm')
        """,
        (spark_id,),
    ).fetchall()
    if len(witnesses) < CANON_QUORUM:
        return None

    conn.execute("UPDATE sparks SET status = 'canon' WHERE id = ?", (spark_id,))
    payload = {
        "spark_id": spark_id,
        "quorum": CANON_QUORUM,
        "witness_count": len(witnesses),
    }
    signature = _system_sign(
        {
            "kind": "system_witness",
            "spark_id": spark_id,
            "action": "canon_promoted",
            "payload": payload,
        }
    )
    entry = _append_witness(
        conn,
        spark_id=spark_id,
        witness_id="system",
        action="canon_promoted",
        payload=payload,
        signature_hex=signature,
    )
    return entry


def _serialize_spark_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": int(row["id"]),
        "content": str(row["content"]),
        "content_type": str(row["content_type"]),
        "author_id": str(row["author_id"]),
        "created_at": str(row["created_at"]),
        "status": str(row["status"]),
        "rv_contraction": row["rv_contraction"],
        "composite_score": float(row["composite_score"] or 0.0),
        "gate_scores": _load_gate_scores(str(row["gate_scores"])),
    }


class AgentRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    public_key: str = Field(..., min_length=64, max_length=128)

    @field_validator("public_key")
    @classmethod
    def validate_public_key_hex(cls, value: str) -> str:
        try:
            VerifyKey(value.encode(), encoder=HexEncoder)
        except Exception as exc:
            raise ValueError("invalid Ed25519 public key (hex)") from exc
        return value


class SparkSubmitRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=12000)
    content_type: Literal["text", "code", "link"] = "text"
    author_id: str = Field(..., min_length=8, max_length=64)
    signature: str = Field(..., min_length=64)


class ChallengeCreateRequest(BaseModel):
    challenger_id: str = Field(..., min_length=8, max_length=64)
    content: str = Field(..., min_length=1, max_length=10000)
    signature: str = Field(..., min_length=64)


class WitnessSignRequest(BaseModel):
    spark_id: int
    witness_id: str = Field(..., min_length=8, max_length=64)
    action: Literal[
        "affirm",
        "canon_affirm",
        "compost",
        "respond",
        "challenge_sustain",
        "challenge_reject",
    ]
    payload: Dict[str, Any] = Field(default_factory=dict)
    signature: str = Field(..., min_length=64)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="SAB Basin API",
    description="Spark -> pressure -> witness -> canon/compost lifecycle API",
    version=SAB_VERSION,
    lifespan=lifespan,
)


@app.post("/api/agents/register", status_code=status.HTTP_201_CREATED)
async def register_agent(req: AgentRegisterRequest) -> Dict[str, Any]:
    init_db()
    agent_id = hashlib.sha256(req.public_key.encode()).hexdigest()[:16]
    created_at = _utc_now()
    with _db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO agents (id, name, public_key, created_at, witness_count, witness_accuracy)
            VALUES (?, ?, ?, ?, 0, 0.0)
            """,
            (agent_id, req.name, req.public_key, created_at),
        )
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="failed to register agent")
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "public_key": str(row["public_key"]),
        "created_at": str(row["created_at"]),
    }


@app.post("/api/spark/submit", status_code=status.HTTP_201_CREATED)
async def submit_spark(req: SparkSubmitRequest) -> Dict[str, Any]:
    init_db()
    content_sha256 = _sha256_hex(req.content.encode())
    submit_message = _message_for_submit(req.author_id, content_sha256)

    with _db() as conn:
        _verify_agent_signature(conn, req.author_id, submit_message, req.signature)

        agent_row = conn.execute(
            "SELECT id, name, created_at FROM agents WHERE id = ?",
            (req.author_id,),
        ).fetchone()
        if agent_row is None:
            raise HTTPException(status_code=404, detail=f"Unknown agent: {req.author_id}")

        counts = _spark_counts_for_author(conn, req.author_id)
        recent_hashes = [
            _sha256_hex(str(r["content"]).encode())
            for r in conn.execute(
                """
                SELECT content
                FROM sparks
                ORDER BY id DESC
                LIMIT 50
                """
            ).fetchall()
        ]

        created_at = datetime.fromisoformat(str(agent_row["created_at"]))
        age_hours = max(0.0, (datetime.now(timezone.utc) - created_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600.0)
        gate_context = {
            "author_posts_last_hour": counts["hour"],
            "author_posts_last_day": counts["day"],
            "author_age_hours": age_hours,
            "author_reputation": 0.0,
            "recent_content_hashes": recent_hashes,
        }
        passed, evidence, evidence_hash = verify_content(req.content, req.author_id, gate_context)
        gate_scores = _build_gate_payload(evidence, evidence_hash)
        status_value = "spark"
        if not gate_scores.get("ahimsa_passed", True):
            status_value = "compost"

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sparks
                (content, content_type, author_id, created_at, gate_scores, status, rv_contraction, composite_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                req.content,
                req.content_type,
                req.author_id,
                _utc_now(),
                json.dumps(gate_scores, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
                status_value,
                gate_scores.get("rv_contraction"),
                float(gate_scores.get("composite", 0.0)),
            ),
        )
        spark_id = int(cursor.lastrowid)

        _append_witness(
            conn,
            spark_id=spark_id,
            witness_id=req.author_id,
            action="submit",
            payload={
                "content_sha256": content_sha256,
                "content_type": req.content_type,
            },
            signature_hex=req.signature,
        )

        system_gate_signature = _system_sign(
            {
                "kind": "system_witness",
                "spark_id": spark_id,
                "action": "gate_scored",
                "payload": gate_scores,
            }
        )
        _append_witness(
            conn,
            spark_id=spark_id,
            witness_id="system",
            action="gate_scored",
            payload=gate_scores,
            signature_hex=system_gate_signature,
        )

        if status_value == "compost":
            compost_signature = _system_sign(
                {
                    "kind": "system_witness",
                    "spark_id": spark_id,
                    "action": "compost",
                    "payload": {"reason": "ahimsa_gate_failed"},
                }
            )
            _append_witness(
                conn,
                spark_id=spark_id,
                witness_id="system",
                action="compost",
                payload={"reason": "ahimsa_gate_failed"},
                signature_hex=compost_signature,
            )

        row = conn.execute("SELECT * FROM sparks WHERE id = ?", (spark_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=500, detail="spark persisted but not found")
        return _serialize_spark_row(row)


@app.get("/api/spark/{spark_id}")
async def get_spark(spark_id: int) -> Dict[str, Any]:
    init_db()
    with _db() as conn:
        row = conn.execute("SELECT * FROM sparks WHERE id = ?", (spark_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="spark not found")
        challenge_count = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM spark_challenges WHERE spark_id = ?",
                (spark_id,),
            ).fetchone()["c"]
        )
        witness_count = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM witness_chain WHERE spark_id = ?",
                (spark_id,),
            ).fetchone()["c"]
        )
        data = _serialize_spark_row(row)
        data["challenge_count"] = challenge_count
        data["witness_count"] = witness_count
        return data


@app.post("/api/spark/{spark_id}/challenge", status_code=status.HTTP_201_CREATED)
async def challenge_spark(spark_id: int, req: ChallengeCreateRequest) -> Dict[str, Any]:
    init_db()
    content_sha256 = _sha256_hex(req.content.encode())
    challenge_message = _message_for_challenge(spark_id, req.challenger_id, content_sha256)

    with _db() as conn:
        spark = conn.execute("SELECT status FROM sparks WHERE id = ?", (spark_id,)).fetchone()
        if spark is None:
            raise HTTPException(status_code=404, detail="spark not found")

        _verify_agent_signature(conn, req.challenger_id, challenge_message, req.signature)

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO spark_challenges (spark_id, challenger_id, content, created_at, resolution)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (spark_id, req.challenger_id, req.content, _utc_now()),
        )
        challenge_id = int(cursor.lastrowid)

        _append_witness(
            conn,
            spark_id=spark_id,
            witness_id=req.challenger_id,
            action="challenge",
            payload={
                "challenge_id": challenge_id,
                "content_sha256": content_sha256,
            },
            signature_hex=req.signature,
        )

        if str(spark["status"]) == "canon":
            conn.execute("UPDATE sparks SET status = 'spark' WHERE id = ?", (spark_id,))
            demote_signature = _system_sign(
                {
                    "kind": "system_witness",
                    "spark_id": spark_id,
                    "action": "canon_challenged",
                    "payload": {"challenge_id": challenge_id},
                }
            )
            _append_witness(
                conn,
                spark_id=spark_id,
                witness_id="system",
                action="canon_challenged",
                payload={"challenge_id": challenge_id},
                signature_hex=demote_signature,
            )

        row = conn.execute(
            "SELECT id, spark_id, challenger_id, content, created_at, resolution FROM spark_challenges WHERE id = ?",
            (challenge_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=500, detail="challenge persisted but not found")
        return dict(row)


@app.get("/api/spark/{spark_id}/chain")
async def get_spark_chain(spark_id: int) -> Dict[str, Any]:
    init_db()
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id, spark_id, witness_id, signature, action, payload, timestamp, prev_hash, hash
            FROM witness_chain
            WHERE spark_id = ?
            ORDER BY id ASC
            """,
            (spark_id,),
        ).fetchall()
    entries = [dict(row) for row in rows]
    return {
        "spark_id": spark_id,
        "verified": _verify_chain_rows(rows),
        "entries": entries,
    }


@app.post("/api/witness/sign")
async def witness_sign(req: WitnessSignRequest) -> Dict[str, Any]:
    init_db()
    payload_sha = _sha256_hex(_canonical_bytes(req.payload))
    witness_message = _message_for_witness(req.spark_id, req.witness_id, req.action, payload_sha)

    with _db() as conn:
        spark = conn.execute("SELECT id, status FROM sparks WHERE id = ?", (req.spark_id,)).fetchone()
        if spark is None:
            raise HTTPException(status_code=404, detail="spark not found")

        _verify_agent_signature(conn, req.witness_id, witness_message, req.signature)

        entry = _append_witness(
            conn,
            spark_id=req.spark_id,
            witness_id=req.witness_id,
            action=req.action,
            payload=req.payload,
            signature_hex=req.signature,
        )

        conn.execute(
            """
            UPDATE agents
            SET witness_count = COALESCE(witness_count, 0) + 1
            WHERE id = ?
            """,
            (req.witness_id,),
        )

        if req.action in ("affirm", "canon_affirm"):
            _promote_if_quorum(conn, req.spark_id)
        elif req.action == "compost":
            conn.execute("UPDATE sparks SET status = 'compost' WHERE id = ?", (req.spark_id,))
            compost_signature = _system_sign(
                {
                    "kind": "system_witness",
                    "spark_id": req.spark_id,
                    "action": "compost",
                    "payload": req.payload,
                }
            )
            _append_witness(
                conn,
                spark_id=req.spark_id,
                witness_id="system",
                action="compost",
                payload=req.payload,
                signature_hex=compost_signature,
            )

        status_row = conn.execute("SELECT status FROM sparks WHERE id = ?", (req.spark_id,)).fetchone()
        spark_status = str(status_row["status"]) if status_row else "unknown"

        return {
            "spark_id": req.spark_id,
            "spark_status": spark_status,
            "entry": entry,
        }


@app.get("/api/witness/{agent_id}")
async def witness_history(agent_id: str, limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    init_db()
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id, spark_id, witness_id, signature, action, payload, timestamp, prev_hash, hash
            FROM witness_chain
            WHERE witness_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (agent_id, limit),
        ).fetchall()
    return {"agent_id": agent_id, "entries": [dict(row) for row in rows]}


def _load_feed(conn: sqlite3.Connection, *, status_value: str, limit: int, gate_name: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM sparks
        WHERE status = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (status_value, limit),
    ).fetchall()
    items = [_serialize_spark_row(row) for row in rows]

    def gate_score(item: Dict[str, Any]) -> float:
        dimensions = item.get("gate_scores", {}).get("dimensions", {})
        selected = dimensions.get(gate_name, {})
        return float(selected.get("score", 0.0))

    items.sort(key=lambda item: (gate_score(item), item.get("created_at", "")), reverse=True)
    return items


@app.get("/api/feed")
async def feed(
    limit: int = Query(50, ge=1, le=200),
    gate: str = Query("satya", min_length=2, max_length=64),
) -> Dict[str, Any]:
    init_db()
    with _db() as conn:
        items = _load_feed(conn, status_value="spark", limit=limit, gate_name=gate)
    return {"status": "spark", "sorted_by_gate": gate, "items": items}


@app.get("/api/feed/canon")
async def feed_canon(
    limit: int = Query(50, ge=1, le=200),
    gate: str = Query("satya", min_length=2, max_length=64),
) -> Dict[str, Any]:
    init_db()
    with _db() as conn:
        items = _load_feed(conn, status_value="canon", limit=limit, gate_name=gate)
    return {"status": "canon", "sorted_by_gate": gate, "items": items}


@app.get("/api/feed/compost")
async def feed_compost(
    limit: int = Query(50, ge=1, le=200),
    gate: str = Query("satya", min_length=2, max_length=64),
) -> Dict[str, Any]:
    init_db()
    with _db() as conn:
        items = _load_feed(conn, status_value="compost", limit=limit, gate_name=gate)
    return {"status": "compost", "sorted_by_gate": gate, "items": items}


@app.get("/api/node/status")
async def node_status() -> Dict[str, Any]:
    init_db()
    with _db() as conn:
        total = int(conn.execute("SELECT COUNT(*) AS c FROM sparks").fetchone()["c"])
        spark_count = int(conn.execute("SELECT COUNT(*) AS c FROM sparks WHERE status = 'spark'").fetchone()["c"])
        canon_count = int(conn.execute("SELECT COUNT(*) AS c FROM sparks WHERE status = 'canon'").fetchone()["c"])
        compost_count = int(conn.execute("SELECT COUNT(*) AS c FROM sparks WHERE status = 'compost'").fetchone()["c"])
        challenge_pending = int(
            conn.execute("SELECT COUNT(*) AS c FROM spark_challenges WHERE resolution = 'pending'").fetchone()["c"]
        )
        recent_witness = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, spark_id, witness_id, action, timestamp
                FROM witness_chain
                ORDER BY id DESC
                LIMIT 20
                """
            ).fetchall()
        ]

        gate_totals: Dict[str, float] = {}
        gate_counts: Dict[str, int] = {}
        for row in conn.execute("SELECT gate_scores FROM sparks").fetchall():
            scores = _load_gate_scores(str(row["gate_scores"]))
            dimensions = scores.get("dimensions", {})
            for gate_name, gate_data in dimensions.items():
                score_val = float(gate_data.get("score", 0.0))
                gate_totals[gate_name] = gate_totals.get(gate_name, 0.0) + score_val
                gate_counts[gate_name] = gate_counts.get(gate_name, 0) + 1

    gate_averages = {
        gate_name: round(gate_totals[gate_name] / gate_counts[gate_name], 6)
        for gate_name in gate_totals
        if gate_counts.get(gate_name, 0) > 0
    }

    return {
        "status": "healthy",
        "version": SAB_VERSION,
        "db_path": str(SPARK_DB),
        "system_verify_key": SYSTEM_VERIFY_KEY_HEX,
        "gate_count": len(ALL_GATES),
        "canon_quorum": CANON_QUORUM,
        "totals": {
            "sparks": total,
            "spark_status": spark_count,
            "canon": canon_count,
            "compost": compost_count,
            "pending_challenges": challenge_pending,
        },
        "gate_averages": gate_averages,
        "recent_witness": recent_witness,
        "timestamp": _utc_now(),
    }
