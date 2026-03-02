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
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from .config import SAB_VERSION, get_db_path
from .gates import ALL_GATES, GateResult, calculate_quality, verify_content
from .rv_signal import measure_rv_signal

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
APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
WEB_SESSION_COOKIE = os.getenv("SAB_WEB_SESSION_COOKIE_NAME", "sab_web_session")
WEB_SESSION_MAX_AGE_SECONDS = int(os.getenv("SAB_WEB_SESSION_MAX_AGE_SECONDS", str(7 * 24 * 3600)))
WEB_CACHE_TTL_SECONDS = int(os.getenv("SAB_WEB_CACHE_TTL_SECONDS", "15"))
WEB_SESSION_COOKIE_SECURE = os.getenv("SAB_WEB_SESSION_COOKIE_SECURE", "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
WEB_SESSION_COOKIE_HTTPONLY = os.getenv("SAB_WEB_SESSION_COOKIE_HTTPONLY", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
WEB_SESSION_COOKIE_SAMESITE = os.getenv("SAB_WEB_SESSION_COOKIE_SAMESITE", "lax").lower()
if WEB_SESSION_COOKIE_SAMESITE not in ("lax", "strict", "none"):
    WEB_SESSION_COOKIE_SAMESITE = "lax"

# Canonical 17-dimension profile used for UI visualization.
SAB_17_DIMENSIONS: List[Dict[str, str]] = [
    {"id": "SATYA", "label": "Satya", "source_gate": "satya"},
    {"id": "AHIMSA", "label": "Ahimsa", "source_gate": "ahimsa"},
    {"id": "ASTEYA", "label": "Asteya", "source_gate": "originality"},
    {"id": "BRAHMACHARYA", "label": "Brahmacharya", "source_gate": "relevance"},
    {"id": "APARIGRAHA", "label": "Aparigraha", "source_gate": ""},
    {"id": "SHAUCHA", "label": "Shaucha", "source_gate": "substance"},
    {"id": "SANTOSHA", "label": "Santosha", "source_gate": ""},
    {"id": "TAPAS", "label": "Tapas", "source_gate": "rate_limit"},
    {"id": "SVADHYAYA", "label": "Svadhyaya", "source_gate": "svadhyaya"},
    {"id": "ISHVARA", "label": "Ishvara", "source_gate": "isvara"},
    {"id": "WITNESS", "label": "Witness", "source_gate": "witness"},
    {"id": "CONSENT", "label": "Consent", "source_gate": ""},
    {"id": "NONVIOLENCE", "label": "Nonviolence", "source_gate": "ahimsa"},
    {"id": "TRANSPARENCY", "label": "Transparency", "source_gate": ""},
    {"id": "RECIPROCITY", "label": "Reciprocity", "source_gate": ""},
    {"id": "HUMILITY", "label": "Humility", "source_gate": ""},
    {"id": "INTEGRITY", "label": "Integrity", "source_gate": "telos_alignment"},
]

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_WEB_SESSIONS: Dict[str, Dict[str, Any]] = {}
_WEB_CACHE: Dict[str, Dict[str, Any]] = {}


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


def _band_for_score(score: Optional[float]) -> str:
    if score is None:
        return "pending"
    if score >= 0.75:
        return "green"
    if score >= 0.45:
        return "yellow"
    return "red"


def _dimension_profile(gate_scores: Dict[str, Any]) -> List[Dict[str, Any]]:
    dimensions = gate_scores.get("dimensions", {})
    profile: List[Dict[str, Any]] = []
    for dim in SAB_17_DIMENSIONS:
        gate_key = dim.get("source_gate", "")
        gate_data = dimensions.get(gate_key, {}) if gate_key else {}
        score = gate_data.get("score")
        score_val = float(score) if isinstance(score, (int, float)) else None
        profile.append(
            {
                "id": dim["id"],
                "label": dim["label"],
                "score": score_val,
                "percent": int(round((score_val or 0.0) * 100)),
                "band": _band_for_score(score_val),
                "result": str(gate_data.get("result", "pending")),
                "reason": str(
                    gate_data.get("reason")
                    or ("Pending instrumentation in sprint runtime." if not gate_data else "Scored")
                ),
                "source_gate": gate_key or "pending",
                "is_measured": bool(gate_data),
            }
        )
    return profile


def _rv_card(gate_scores: Dict[str, Any]) -> Dict[str, Any]:
    rv_signal = gate_scores.get("rv_signal", {})
    rv_val_raw = rv_signal.get("rv")
    rv_val = float(rv_val_raw) if isinstance(rv_val_raw, (int, float)) else None
    warnings = [str(w) for w in rv_signal.get("warnings", []) if isinstance(w, str)]
    status_text = "measured"
    if rv_val is None:
        status_text = "not measured (requires GPU sidecar)"
    if "measurement_failed_status" in warnings or "measurement_failed_http" in warnings:
        status_text = "measurement unavailable (sidecar error)"
    return {
        "label": "R_V",
        "score": rv_val,
        "percent": int(round((rv_val or 0.0) * 100)),
        "mode": str(rv_signal.get("mode", "uncertain")),
        "tier": str(rv_signal.get("signal_label", "experimental")),
        "scope": str(rv_signal.get("claim_scope", "icl_adaptation_only")),
        "status_text": status_text,
        "measurement_version": str(rv_signal.get("measurement_version", "unknown")),
        "warnings": warnings,
    }


def _cache_get(key: str) -> Optional[Any]:
    entry = _WEB_CACHE.get(key)
    if not entry:
        return None
    if float(entry.get("expires_at", 0.0)) <= time.time():
        _WEB_CACHE.pop(key, None)
        return None
    return entry.get("value")


def _cache_set(key: str, value: Any) -> None:
    _WEB_CACHE[key] = {"value": value, "expires_at": time.time() + WEB_CACHE_TTL_SECONDS}


def _invalidate_web_cache() -> None:
    _WEB_CACHE.clear()


def _cleanup_web_sessions() -> None:
    now = time.time()
    expired = [
        token
        for token, session in _WEB_SESSIONS.items()
        if float(session.get("created_at_epoch", 0.0)) + WEB_SESSION_MAX_AGE_SECONDS < now
    ]
    for token in expired:
        _WEB_SESSIONS.pop(token, None)


def _read_web_session(request: Request) -> Optional[Dict[str, Any]]:
    _cleanup_web_sessions()
    token = request.cookies.get(WEB_SESSION_COOKIE)
    if not token:
        return None
    return _WEB_SESSIONS.get(token)


def _session_for_template(request: Request) -> Optional[Dict[str, Any]]:
    session = _read_web_session(request)
    if not session:
        return None
    return {
        "token": str(session["token"]),
        "agent_id": str(session["agent_id"]),
        "name": str(session["name"]),
        "public_key_hex": str(session["public_key_hex"]),
        "created_at_epoch": float(session["created_at_epoch"]),
    }


def _signing_key_from_session(session: Dict[str, Any]) -> SigningKey:
    return SigningKey(str(session["private_key_hex"]).encode(), encoder=HexEncoder)


def _create_web_session(conn: sqlite3.Connection, display_name: str) -> Dict[str, Any]:
    clean_name = (display_name or "").strip()[:80] or "anonymous"
    signing_key = SigningKey.generate()
    private_key_hex = signing_key.encode(encoder=HexEncoder).decode()
    public_key_hex = signing_key.verify_key.encode(encoder=HexEncoder).decode()
    agent_id = hashlib.sha256(public_key_hex.encode()).hexdigest()[:16]
    conn.execute(
        """
        INSERT OR IGNORE INTO agents (id, name, public_key, created_at, witness_count, witness_accuracy)
        VALUES (?, ?, ?, ?, 0, 0.0)
        """,
        (agent_id, clean_name, public_key_hex, _utc_now()),
    )
    token = secrets.token_urlsafe(24)
    session = {
        "token": token,
        "agent_id": agent_id,
        "name": clean_name,
        "private_key_hex": private_key_hex,
        "public_key_hex": public_key_hex,
        "created_at_epoch": time.time(),
    }
    _WEB_SESSIONS[token] = session
    return session


def _resolve_or_create_web_session(
    request: Request,
    conn: sqlite3.Connection,
    display_name: str,
) -> Dict[str, Any]:
    existing = _read_web_session(request)
    if existing:
        return existing
    return _create_web_session(conn, display_name)


def _set_web_session_cookie(response: RedirectResponse, session: Dict[str, Any]) -> None:
    response.set_cookie(
        key=WEB_SESSION_COOKIE,
        value=str(session["token"]),
        httponly=WEB_SESSION_COOKIE_HTTPONLY,
        secure=WEB_SESSION_COOKIE_SECURE,
        max_age=WEB_SESSION_MAX_AGE_SECONDS,
        samesite=WEB_SESSION_COOKIE_SAMESITE,
    )


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


def _build_gate_payload(
    evidence: List[Any],
    evidence_hash: str,
    rv_signal: Dict[str, Any],
) -> Dict[str, Any]:
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
    rv_value = rv_signal.get("rv")
    warning_set = {str(w) for w in rv_signal.get("warnings", []) if isinstance(w, str)}
    if rv_value is not None:
        rv_state = "measured"
    elif "measurement_disabled" in warning_set:
        rv_state = "disabled"
    elif any(w.startswith("measurement_failed") for w in warning_set):
        rv_state = "failed"
    else:
        rv_state = "uncertain"
    return {
        "dimensions": dimensions,
        "composite": composite,
        "evidence_hash": evidence_hash,
        "ahimsa_passed": ahimsa_state != "failed",
        "rv_contraction": rv_value,
        "rv_measurement_state": rv_state,
        "rv_signal": rv_signal,
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


def _compost_why_card(conn: sqlite3.Connection, spark_id: int, gate_scores: Dict[str, Any]) -> Dict[str, str]:
    witness_row = conn.execute(
        """
        SELECT payload
        FROM witness_chain
        WHERE spark_id = ? AND action = 'compost'
        ORDER BY id DESC
        LIMIT 1
        """,
        (spark_id,),
    ).fetchone()
    challenge_row = conn.execute(
        """
        SELECT content
        FROM spark_challenges
        WHERE spark_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (spark_id,),
    ).fetchone()

    reason = "Composted by witness action."
    source = "witness"
    if witness_row:
        try:
            payload = json.loads(str(witness_row["payload"]))
            payload_reason = str(payload.get("reason", "")).strip()
            if payload_reason == "ahimsa_gate_failed":
                reason = "Failed Ahimsa safety gate."
                source = "safety"
            elif payload_reason:
                reason = payload_reason.replace("_", " ")
        except json.JSONDecodeError:
            pass

    if challenge_row is not None and source != "safety":
        excerpt = str(challenge_row["content"]).strip().replace("\n", " ")
        if excerpt:
            reason = f"Challenge pressure: {excerpt[:180]}"
            source = "challenge"

    rv = _rv_card(gate_scores)
    return {
        "title": "WHY this is compost",
        "reason": reason,
        "source": source,
        "rv_note": rv["status_text"],
    }


def _web_feed_items(
    conn: sqlite3.Connection,
    *,
    status_filter: str,
    sort_mode: str,
    limit: int,
) -> List[Dict[str, Any]]:
    where = ""
    params: List[Any] = []
    if status_filter != "all":
        where = "WHERE s.status = ?"
        params.append(status_filter)

    rows = conn.execute(
        f"""
        SELECT
            s.*,
            (SELECT COUNT(*) FROM spark_challenges c WHERE c.spark_id = s.id) AS challenge_count,
            (SELECT COUNT(*) FROM witness_chain w WHERE w.spark_id = s.id) AS witness_count
        FROM sparks s
        {where}
        ORDER BY s.created_at DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    items: List[Dict[str, Any]] = []
    for row in rows:
        item = _serialize_spark_row(row)
        item["challenge_count"] = int(row["challenge_count"] or 0)
        item["witness_count"] = int(row["witness_count"] or 0)
        item["dimensions_17"] = _dimension_profile(item["gate_scores"])
        item["rv_card"] = _rv_card(item["gate_scores"])
        if item["status"] == "compost":
            item["compost_why"] = _compost_why_card(conn, item["id"], item["gate_scores"])
        items.append(item)

    if sort_mode == "most-challenged":
        items.sort(
            key=lambda item: (int(item.get("challenge_count", 0)), str(item.get("created_at", ""))),
            reverse=True,
        )
    return items


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
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
        rv_signal = measure_rv_signal(req.content)
        gate_scores = _build_gate_payload(evidence, evidence_hash, rv_signal)
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
        _invalidate_web_cache()
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
        _invalidate_web_cache()
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
        _invalidate_web_cache()

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


def _render_template(
    request: Request,
    template_name: str,
    context: Dict[str, Any],
    *,
    status_code: int = 200,
) -> HTMLResponse:
    payload = {"request": request, **context}
    return templates.TemplateResponse(request, template_name, payload, status_code=status_code)


def _spark_with_details(conn: sqlite3.Connection, spark_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """
        SELECT
            s.*,
            (SELECT COUNT(*) FROM spark_challenges c WHERE c.spark_id = s.id) AS challenge_count,
            (SELECT COUNT(*) FROM witness_chain w WHERE w.spark_id = s.id) AS witness_count
        FROM sparks s
        WHERE s.id = ?
        """,
        (spark_id,),
    ).fetchone()
    if row is None:
        return None
    data = _serialize_spark_row(row)
    data["challenge_count"] = int(row["challenge_count"] or 0)
    data["witness_count"] = int(row["witness_count"] or 0)
    data["dimensions_17"] = _dimension_profile(data["gate_scores"])
    data["rv_card"] = _rv_card(data["gate_scores"])
    if data["status"] == "compost":
        data["compost_why"] = _compost_why_card(conn, data["id"], data["gate_scores"])
    return data


def _web_feed_context(
    conn: sqlite3.Connection,
    *,
    status_filter: str,
    sort_mode: str,
    limit: int,
) -> Dict[str, Any]:
    cache_key = f"{status_filter}:{sort_mode}:{limit}"
    cached = _cache_get(cache_key)
    if cached is None:
        items = _web_feed_items(conn, status_filter=status_filter, sort_mode=sort_mode, limit=limit)
        _cache_set(cache_key, items)
    else:
        items = cached
    return {
        "items": items,
        "status_filter": status_filter,
        "sort_mode": sort_mode,
        "limit": limit,
    }


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
        "web_cache": {
            "entries": len(_WEB_CACHE),
            "ttl_seconds": WEB_CACHE_TTL_SECONDS,
        },
        "recent_witness": recent_witness,
        "timestamp": _utc_now(),
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    """
    Legacy-compatible health endpoint.

    Kept intentionally lightweight so existing scripts that probe `/health`
    continue to work when running `agora.app`.
    """
    return {
        "status": "healthy",
        "service": "sab-basin-app",
        "version": SAB_VERSION,
        "timestamp": _utc_now(),
    }


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "sab-basin-app",
        "version": SAB_VERSION,
        "timestamp": _utc_now(),
    }


@app.get("/readyz")
async def readyz() -> Dict[str, Any]:
    checks: Dict[str, Any] = {
        "db": {"ok": False},
        "system_key": {"ok": False},
    }
    errors: List[str] = []

    try:
        init_db()
        with _db() as conn:
            conn.execute("SELECT 1").fetchone()
        checks["db"] = {"ok": True, "path": str(SPARK_DB)}
    except Exception as exc:  # pragma: no cover - protective catch
        errors.append(f"db_check_failed:{exc.__class__.__name__}")

    try:
        checks["system_key"] = {
            "ok": bool(SYSTEM_VERIFY_KEY_HEX),
            "key_path": str(SYSTEM_KEY_PATH),
        }
        if not SYSTEM_VERIFY_KEY_HEX:
            errors.append("system_key_missing")
    except Exception as exc:  # pragma: no cover - protective catch
        errors.append(f"system_key_check_failed:{exc.__class__.__name__}")

    ready = len(errors) == 0
    return {
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "checks": checks,
        "errors": errors,
        "timestamp": _utc_now(),
    }


@app.get("/api/web/cache/status")
async def web_cache_status(verbose: bool = Query(False)) -> Dict[str, Any]:
    _cleanup_web_sessions()
    payload: Dict[str, Any] = {
        "status": "ok",
        "cache_entries": len(_WEB_CACHE),
        "cache_ttl_seconds": WEB_CACHE_TTL_SECONDS,
        "session_entries": len(_WEB_SESSIONS),
        "timestamp": _utc_now(),
    }
    if verbose:
        payload["cache_keys"] = sorted(list(_WEB_CACHE.keys()))
    return payload


@app.get("/", response_class=HTMLResponse)
async def web_home(
    request: Request,
    mode: str = Query("newest", pattern="^(newest|most-challenged|canon|compost)$"),
    limit: int = Query(30, ge=1, le=100),
) -> HTMLResponse:
    init_db()
    status_filter = "spark"
    sort_mode = "newest"
    if mode == "most-challenged":
        sort_mode = "most-challenged"
    elif mode == "canon":
        status_filter = "canon"
    elif mode == "compost":
        status_filter = "compost"

    with _db() as conn:
        feed_context = _web_feed_context(
            conn,
            status_filter=status_filter,
            sort_mode=sort_mode,
            limit=limit,
        )

    session = _read_web_session(request)
    return _render_template(
        request,
        "web_feed.html",
        {
            **feed_context,
            "title": "SAB Feed",
            "mode": mode,
            "path_name": "/",
            "session": session,
        },
    )


@app.get("/canon", response_class=HTMLResponse)
async def web_canon(
    request: Request,
    sort: str = Query("newest", pattern="^(newest|most-challenged)$"),
    limit: int = Query(30, ge=1, le=100),
) -> HTMLResponse:
    init_db()
    with _db() as conn:
        feed_context = _web_feed_context(
            conn,
            status_filter="canon",
            sort_mode=sort,
            limit=limit,
        )
    return _render_template(
        request,
        "web_feed.html",
        {
            **feed_context,
            "title": "Canon",
            "mode": "canon",
            "path_name": "/canon",
            "session": _session_for_template(request),
        },
    )


@app.get("/compost", response_class=HTMLResponse)
async def web_compost(
    request: Request,
    sort: str = Query("newest", pattern="^(newest|most-challenged)$"),
    limit: int = Query(30, ge=1, le=100),
) -> HTMLResponse:
    init_db()
    with _db() as conn:
        feed_context = _web_feed_context(
            conn,
            status_filter="compost",
            sort_mode=sort,
            limit=limit,
        )
    return _render_template(
        request,
        "web_feed.html",
        {
            **feed_context,
            "title": "Compost",
            "mode": "compost",
            "path_name": "/compost",
            "session": _session_for_template(request),
        },
    )


@app.get("/submit", response_class=HTMLResponse)
async def web_submit_get(request: Request) -> HTMLResponse:
    return _render_template(
        request,
        "web_submit.html",
        {"session": _session_for_template(request), "error": "", "content": ""},
    )


@app.post("/submit", response_class=HTMLResponse)
async def web_submit_post(
    request: Request,
    content: str = Form(...),
    display_name: str = Form(""),
    content_type: Literal["text", "code", "link"] = Form("text"),
) -> HTMLResponse:
    body = (content or "").strip()
    if not body:
        return _render_template(
            request,
            "web_submit.html",
            {"session": _session_for_template(request), "error": "Content is required.", "content": body},
            status_code=400,
        )

    init_db()
    with _db() as conn:
        session = _resolve_or_create_web_session(request, conn, display_name)

    signing_key = _signing_key_from_session(session)
    content_sha256 = _sha256_hex(body.encode())
    signature = signing_key.sign(_message_for_submit(str(session["agent_id"]), content_sha256)).signature.hex()
    submit_req = SparkSubmitRequest(
        content=body,
        content_type=content_type,
        author_id=str(session["agent_id"]),
        signature=signature,
    )
    spark = await submit_spark(submit_req)

    response = RedirectResponse(url=f"/spark/{int(spark['id'])}?submitted=1", status_code=303)
    if request.cookies.get(WEB_SESSION_COOKIE) != session["token"]:
        _set_web_session_cookie(response, session)
    return response


@app.get("/spark/{spark_id}", response_class=HTMLResponse)
async def web_spark_detail(
    request: Request,
    spark_id: int,
    submitted: int = Query(0, ge=0, le=1),
) -> HTMLResponse:
    init_db()
    with _db() as conn:
        spark = _spark_with_details(conn, spark_id)
        if spark is None:
            raise HTTPException(status_code=404, detail="spark not found")
        challenge_rows = conn.execute(
            """
            SELECT id, spark_id, challenger_id, content, created_at, resolution
            FROM spark_challenges
            WHERE spark_id = ?
            ORDER BY id ASC
            """,
            (spark_id,),
        ).fetchall()
        challenges = [dict(row) for row in challenge_rows]

        chain_rows = conn.execute(
            """
            SELECT id, spark_id, witness_id, action, payload, timestamp, prev_hash, hash
            FROM witness_chain
            WHERE spark_id = ?
            ORDER BY id ASC
            """,
            (spark_id,),
        ).fetchall()
        timeline: List[Dict[str, Any]] = []
        for row in chain_rows:
            payload_obj: Any = {}
            try:
                payload_obj = json.loads(str(row["payload"]))
            except json.JSONDecodeError:
                payload_obj = {"raw": str(row["payload"])}
            timeline.append(
                {
                    "id": int(row["id"]),
                    "witness_id": str(row["witness_id"]),
                    "action": str(row["action"]),
                    "payload": payload_obj,
                    "timestamp": str(row["timestamp"]),
                    "hash": str(row["hash"]),
                    "prev_hash": str(row["prev_hash"]),
                }
            )

    return _render_template(
        request,
        "web_spark_detail.html",
        {
            "spark": spark,
            "challenges": challenges,
            "timeline": timeline,
            "submitted": bool(submitted),
            "session": _session_for_template(request),
        },
    )


@app.post("/spark/{spark_id}/challenge", response_class=HTMLResponse)
async def web_challenge_post(
    request: Request,
    spark_id: int,
    content: str = Form(...),
    display_name: str = Form(""),
) -> HTMLResponse:
    body = (content or "").strip()
    if not body:
        return RedirectResponse(url=f"/spark/{spark_id}?challenge_error=1", status_code=303)

    init_db()
    with _db() as conn:
        session = _resolve_or_create_web_session(request, conn, display_name)

    signing_key = _signing_key_from_session(session)
    content_sha256 = _sha256_hex(body.encode())
    signature = signing_key.sign(
        _message_for_challenge(spark_id, str(session["agent_id"]), content_sha256)
    ).signature.hex()
    challenge_req = ChallengeCreateRequest(
        challenger_id=str(session["agent_id"]),
        content=body,
        signature=signature,
    )
    await challenge_spark(spark_id, challenge_req)

    response = RedirectResponse(url=f"/spark/{spark_id}#challenges", status_code=303)
    if request.cookies.get(WEB_SESSION_COOKIE) != session["token"]:
        _set_web_session_cookie(response, session)
    return response


@app.post("/spark/{spark_id}/witness", response_class=HTMLResponse)
async def web_witness_post(
    request: Request,
    spark_id: int,
    action: Literal["affirm", "canon_affirm", "compost"] = Form("affirm"),
    note: str = Form(""),
    display_name: str = Form(""),
) -> HTMLResponse:
    init_db()
    with _db() as conn:
        session = _resolve_or_create_web_session(request, conn, display_name)

    payload = {
        "note": (note or "").strip()[:500],
        "source": "web_surface",
    }
    signing_key = _signing_key_from_session(session)
    payload_sha = _sha256_hex(_canonical_bytes(payload))
    signature = signing_key.sign(
        _message_for_witness(spark_id, str(session["agent_id"]), action, payload_sha)
    ).signature.hex()
    witness_req = WitnessSignRequest(
        spark_id=spark_id,
        witness_id=str(session["agent_id"]),
        action=action,
        payload=payload,
        signature=signature,
    )
    await witness_sign(witness_req)

    response = RedirectResponse(url=f"/spark/{spark_id}#timeline", status_code=303)
    if request.cookies.get(WEB_SESSION_COOKIE) != session["token"]:
        _set_web_session_cookie(response, session)
    return response


@app.get("/register", response_class=HTMLResponse)
async def web_register_get(request: Request) -> HTMLResponse:
    return _render_template(
        request,
        "web_register.html",
        {"session": _session_for_template(request), "error": ""},
    )


@app.post("/register", response_class=HTMLResponse)
async def web_register_post(request: Request, display_name: str = Form(...)) -> HTMLResponse:
    init_db()
    with _db() as conn:
        session = _create_web_session(conn, display_name)
    response = RedirectResponse(url=f"/agent/{session['agent_id']}", status_code=303)
    _set_web_session_cookie(response, session)
    return response


@app.get("/agent/{agent_id}", response_class=HTMLResponse)
async def web_agent_profile(request: Request, agent_id: str) -> HTMLResponse:
    init_db()
    with _db() as conn:
        agent = conn.execute(
            "SELECT id, name, public_key, created_at, witness_count, witness_accuracy FROM agents WHERE id = ?",
            (agent_id,),
        ).fetchone()
        if agent is None:
            raise HTTPException(status_code=404, detail="agent not found")

        submitted_count = int(
            conn.execute("SELECT COUNT(*) AS c FROM sparks WHERE author_id = ?", (agent_id,)).fetchone()["c"]
        )
        canon_count = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM sparks WHERE author_id = ? AND status = 'canon'",
                (agent_id,),
            ).fetchone()["c"]
        )
        compost_count = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM sparks WHERE author_id = ? AND status = 'compost'",
                (agent_id,),
            ).fetchone()["c"]
        )
        challenge_made = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM spark_challenges WHERE challenger_id = ?",
                (agent_id,),
            ).fetchone()["c"]
        )
        challenged_total = int(
            conn.execute(
                """
                SELECT COUNT(DISTINCT c.spark_id) AS c
                FROM spark_challenges c
                JOIN sparks s ON s.id = c.spark_id
                WHERE s.author_id = ?
                """,
                (agent_id,),
            ).fetchone()["c"]
        )
        challenged_survived = int(
            conn.execute(
                """
                SELECT COUNT(DISTINCT c.spark_id) AS c
                FROM spark_challenges c
                JOIN sparks s ON s.id = c.spark_id
                WHERE s.author_id = ? AND s.status != 'compost'
                """,
                (agent_id,),
            ).fetchone()["c"]
        )
        attestation_total = int(
            conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM witness_chain
                WHERE witness_id = ? AND action IN ('affirm', 'canon_affirm')
                """,
                (agent_id,),
            ).fetchone()["c"]
        )
        attestation_on_canon = int(
            conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM witness_chain w
                JOIN sparks s ON s.id = w.spark_id
                WHERE w.witness_id = ? AND w.action IN ('affirm', 'canon_affirm') AND s.status = 'canon'
                """,
                (agent_id,),
            ).fetchone()["c"]
        )

    canon_rate = (canon_count / submitted_count) if submitted_count else None
    challenge_survival = (challenged_survived / challenged_total) if challenged_total else None
    witness_accuracy = (attestation_on_canon / attestation_total) if attestation_total else None
    reliability = [
        {"label": "Canonization Rate", "value": canon_rate},
        {"label": "Challenge Survival", "value": challenge_survival},
        {"label": "Witness Accuracy", "value": witness_accuracy},
    ]
    return _render_template(
        request,
        "web_agent_profile.html",
        {
            "agent": dict(agent),
            "stats": {
                "submitted_count": submitted_count,
                "canon_count": canon_count,
                "compost_count": compost_count,
                "challenge_made": challenge_made,
                "challenged_total": challenged_total,
                "challenged_survived": challenged_survived,
                "attestation_total": attestation_total,
                "attestation_on_canon": attestation_on_canon,
            },
            "reliability": reliability,
            "session": _session_for_template(request),
        },
    )


@app.get("/about", response_class=HTMLResponse)
async def web_about(request: Request) -> HTMLResponse:
    return _render_template(
        request,
        "web_about.html",
        {"session": _session_for_template(request), "dimensions_count": len(SAB_17_DIMENSIONS)},
    )
