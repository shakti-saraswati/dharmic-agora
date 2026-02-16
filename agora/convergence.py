"""
Convergence diagnostics for SAB.

This module implements the production coherence path:
agent output -> DGC scoring -> trust gradient -> convergence landscape.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _safe_avg(values: List[float], default: float = 0.5) -> float:
    if not values:
        return default
    return sum(values) / len(values)


class ConvergenceStore:
    """Persistence and scoring for trust gradients and convergence views."""

    LOW_TRUST_THRESHOLD = 0.45

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_identity_packets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_address TEXT NOT NULL,
                    base_model TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    registered_timestamp TEXT NOT NULL,
                    perceived_role TEXT NOT NULL,
                    self_grade REAL NOT NULL,
                    context_hash TEXT NOT NULL,
                    task_affinity_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    packet_hash TEXT NOT NULL,
                    audit_hash TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dgc_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    agent_address TEXT NOT NULL,
                    signal_timestamp TEXT NOT NULL,
                    task_id TEXT,
                    task_type TEXT,
                    artifact_id TEXT,
                    source_alias TEXT,
                    gate_scores_json TEXT NOT NULL,
                    collapse_dimensions_json TEXT NOT NULL,
                    mission_relevance REAL,
                    metadata_json TEXT NOT NULL,
                    signature TEXT,
                    payload_hash TEXT NOT NULL,
                    audit_hash TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trust_gradients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_event_id TEXT NOT NULL UNIQUE,
                    dgc_signal_id INTEGER NOT NULL,
                    agent_address TEXT NOT NULL,
                    task_id TEXT,
                    task_type TEXT,
                    artifact_id TEXT,
                    trust_score REAL NOT NULL,
                    low_trust_flag INTEGER NOT NULL,
                    gate_component REAL NOT NULL,
                    mission_component REAL NOT NULL,
                    collapse_component REAL NOT NULL,
                    self_alignment_component REAL NOT NULL,
                    affinity_match_component REAL NOT NULL,
                    weak_gates_json TEXT NOT NULL,
                    strong_gates_json TEXT NOT NULL,
                    high_collapse_json TEXT NOT NULL,
                    likely_causes_json TEXT NOT NULL,
                    diagnostic_json TEXT NOT NULL,
                    audit_hash TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (dgc_signal_id) REFERENCES dgc_signals(id)
                )
                """
            )

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_identity_agent_created ON agent_identity_packets(agent_address, created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_dgc_agent_created ON dgc_signals(agent_address, created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_dgc_task ON dgc_signals(task_id, task_type)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trust_agent_created ON trust_gradients(agent_address, created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trust_score ON trust_gradients(trust_score DESC)"
            )

    @staticmethod
    def _parse_json(value: Any, fallback: Any) -> Any:
        if value is None:
            return fallback
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return fallback

    @staticmethod
    def _normalize_score_map(raw: Optional[Dict[str, Any]]) -> Dict[str, float]:
        if not raw:
            return {}
        out: Dict[str, float] = {}
        for key, value in raw.items():
            if value is None:
                continue
            try:
                out[str(key)] = round(_clamp(float(value)), 4)
            except (TypeError, ValueError):
                continue
        return out

    @staticmethod
    def _normalize_affinity(values: Optional[List[str]]) -> List[str]:
        if not values:
            return []
        out: List[str] = []
        for item in values:
            norm = str(item).strip().lower()
            if not norm:
                continue
            out.append(norm)
        # Keep deterministic order while deduplicating.
        seen = set()
        deduped: List[str] = []
        for item in out:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def register_identity(
        self,
        agent_address: str,
        packet: Dict[str, Any],
        audit_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = _utc_now()
        affinity = self._normalize_affinity(packet.get("task_affinity"))
        metadata = packet.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {"metadata_raw": str(metadata)}

        row_payload = {
            "agent_address": agent_address,
            "base_model": str(packet["base_model"]),
            "alias": str(packet["alias"]),
            "registered_timestamp": str(packet["timestamp"]),
            "perceived_role": str(packet.get("perceived_role", "generalist")),
            "self_grade": round(_clamp(float(packet["self_grade"])), 4),
            "context_hash": str(packet["context_hash"]),
            "task_affinity": affinity,
            "metadata": metadata,
        }
        packet_hash = hashlib.sha256(_canonical_json(row_payload).encode("utf-8")).hexdigest()

        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO agent_identity_packets (
                    agent_address, base_model, alias, registered_timestamp,
                    perceived_role, self_grade, context_hash, task_affinity_json,
                    metadata_json, packet_hash, audit_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_payload["agent_address"],
                    row_payload["base_model"],
                    row_payload["alias"],
                    row_payload["registered_timestamp"],
                    row_payload["perceived_role"],
                    row_payload["self_grade"],
                    row_payload["context_hash"],
                    json.dumps(row_payload["task_affinity"]),
                    json.dumps(row_payload["metadata"]),
                    packet_hash,
                    audit_hash,
                    now,
                ),
            )
            identity_id = cursor.lastrowid
            cursor.execute("SELECT * FROM agent_identity_packets WHERE id = ?", (identity_id,))
            row = dict(cursor.fetchone())

        row["task_affinity"] = self._parse_json(row.pop("task_affinity_json"), [])
        row["metadata"] = self._parse_json(row.pop("metadata_json"), {})
        return row

    def latest_identity(self, agent_address: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM agent_identity_packets
                WHERE agent_address = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (agent_address,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        out = dict(row)
        out["task_affinity"] = self._parse_json(out.pop("task_affinity_json"), [])
        out["metadata"] = self._parse_json(out.pop("metadata_json"), {})
        return out

    def _coerce_signal_payload(self, payload: Dict[str, Any], agent_address: str) -> Dict[str, Any]:
        gate_scores = self._normalize_score_map(payload.get("gate_scores"))
        collapse_dimensions = self._normalize_score_map(payload.get("collapse_dimensions"))
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {"metadata_raw": str(metadata)}
        schema_version = str(payload.get("schema_version") or "dgc.v1")
        metadata.setdefault("schema_version", schema_version)

        mission_relevance = payload.get("mission_relevance")
        mission_value: Optional[float] = None
        if mission_relevance is not None:
            mission_value = round(_clamp(float(mission_relevance)), 4)

        return {
            "event_id": str(payload["event_id"]),
            "schema_version": schema_version,
            "agent_address": agent_address,
            "signal_timestamp": str(payload["timestamp"]),
            "task_id": str(payload.get("task_id") or "") or None,
            "task_type": str(payload.get("task_type") or "") or None,
            "artifact_id": str(payload.get("artifact_id") or "") or None,
            "source_alias": str(payload.get("source_alias") or "") or None,
            "gate_scores": gate_scores,
            "collapse_dimensions": collapse_dimensions,
            "mission_relevance": mission_value,
            "metadata": metadata,
            "signature": str(payload.get("signature") or "") or None,
        }

    def ingest_dgc_signal(
        self,
        agent_address: str,
        payload: Dict[str, Any],
        payload_hash: str,
        audit_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = _utc_now()
        signal = self._coerce_signal_payload(payload, agent_address=agent_address)

        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dgc_signals WHERE event_id = ?", (signal["event_id"],))
            existing = cursor.fetchone()
            if existing:
                row = dict(existing)
                if row.get("agent_address") != agent_address:
                    raise ValueError("event_id_conflict_agent_mismatch")
                if row.get("payload_hash") != payload_hash:
                    raise ValueError("event_id_conflict_payload_mismatch")
                idempotent_replay = True
            else:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO dgc_signals (
                        event_id, agent_address, signal_timestamp, task_id, task_type,
                        artifact_id, source_alias, gate_scores_json, collapse_dimensions_json,
                        mission_relevance, metadata_json, signature, payload_hash, audit_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal["event_id"],
                        signal["agent_address"],
                        signal["signal_timestamp"],
                        signal["task_id"],
                        signal["task_type"],
                        signal["artifact_id"],
                        signal["source_alias"],
                        json.dumps(signal["gate_scores"]),
                        json.dumps(signal["collapse_dimensions"]),
                        signal["mission_relevance"],
                        json.dumps(signal["metadata"]),
                        signal["signature"],
                        payload_hash,
                        audit_hash,
                        now,
                    ),
                )
                if cursor.rowcount == 0:
                    # Another writer inserted the same event_id concurrently.
                    cursor.execute("SELECT * FROM dgc_signals WHERE event_id = ?", (signal["event_id"],))
                    existing_after = cursor.fetchone()
                    if not existing_after:
                        raise ValueError("event_id_conflict_unresolvable")
                    row = dict(existing_after)
                    if row.get("agent_address") != agent_address:
                        raise ValueError("event_id_conflict_agent_mismatch")
                    if row.get("payload_hash") != payload_hash:
                        raise ValueError("event_id_conflict_payload_mismatch")
                    idempotent_replay = True
                else:
                    signal_id = cursor.lastrowid
                    cursor.execute("SELECT * FROM dgc_signals WHERE id = ?", (signal_id,))
                    row = dict(cursor.fetchone())
                    idempotent_replay = False

        row["gate_scores"] = self._parse_json(row.pop("gate_scores_json"), {})
        row["collapse_dimensions"] = self._parse_json(row.pop("collapse_dimensions_json"), {})
        row["metadata"] = self._parse_json(row.pop("metadata_json"), {})
        row["_idempotent_replay"] = idempotent_replay
        return row

    @staticmethod
    def _affinity_match(task_type: Optional[str], affinity: List[str]) -> tuple[float, bool]:
        if not task_type:
            return 0.5, False
        if not affinity:
            return 0.5, False
        task_norm = task_type.strip().lower()
        for item in affinity:
            if item == task_norm or item in task_norm or task_norm in item:
                return 1.0, False
        return 0.25, True

    def _derive_gradient(
        self,
        signal: Dict[str, Any],
        identity: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        gate_scores = signal.get("gate_scores") or {}
        collapse_dimensions = signal.get("collapse_dimensions") or {}
        mission_component = (
            float(signal["mission_relevance"])
            if signal.get("mission_relevance") is not None
            else 0.5
        )

        gate_component = _safe_avg([float(v) for v in gate_scores.values()], default=0.5)
        collapse_raw = _safe_avg([float(v) for v in collapse_dimensions.values()], default=0.5)
        collapse_component = 1.0 - collapse_raw

        observed_performance = _clamp(
            0.60 * gate_component + 0.25 * mission_component + 0.15 * collapse_component
        )

        self_grade: Optional[float] = None
        affinity: List[str] = []
        if identity:
            try:
                self_grade = float(identity.get("self_grade"))
            except (TypeError, ValueError):
                self_grade = None
            affinity = self._normalize_affinity(identity.get("task_affinity"))

        if self_grade is None:
            self_alignment_component = 0.75
        else:
            self_alignment_component = _clamp(1.0 - abs(self_grade - observed_performance))

        affinity_match_component, affinity_mismatch = self._affinity_match(
            signal.get("task_type"), affinity
        )

        trust_score = _clamp(
            0.60 * observed_performance
            + 0.25 * self_alignment_component
            + 0.15 * affinity_match_component
        )
        trust_score = round(trust_score, 4)

        weak_gates = sorted([name for name, score in gate_scores.items() if float(score) < 0.45])
        strong_gates = sorted([name for name, score in gate_scores.items() if float(score) >= 0.75])
        high_collapse = sorted(
            [name for name, score in collapse_dimensions.items() if float(score) >= 0.65]
        )

        likely_causes: List[str] = []
        if weak_gates:
            likely_causes.append("context_quality_gap")
        if high_collapse:
            likely_causes.append("liturgical_collapse_risk")
        if affinity_mismatch:
            likely_causes.append("task_affinity_mismatch")
        if self_grade is not None and abs(self_grade - observed_performance) >= 0.25:
            likely_causes.append("self_assessment_gap")
        if not likely_causes:
            likely_causes.append("on_track")

        low_trust_flag = trust_score < self.LOW_TRUST_THRESHOLD
        diagnostic = {
            "observed_performance": round(observed_performance, 4),
            "task_type": signal.get("task_type"),
            "task_affinity": affinity,
            "weak_gates": weak_gates,
            "strong_gates": strong_gates,
            "high_collapse_dimensions": high_collapse,
            "likely_causes": likely_causes,
            "suggested_action": (
                "reroute_to_affinity_or_improve_context" if low_trust_flag else "continue_gradient_path"
            ),
        }

        return {
            "trust_score": trust_score,
            "low_trust_flag": bool(low_trust_flag),
            "gate_component": round(gate_component, 4),
            "mission_component": round(mission_component, 4),
            "collapse_component": round(collapse_component, 4),
            "self_alignment_component": round(self_alignment_component, 4),
            "affinity_match_component": round(affinity_match_component, 4),
            "weak_gates": weak_gates,
            "strong_gates": strong_gates,
            "high_collapse": high_collapse,
            "likely_causes": likely_causes,
            "diagnostic": diagnostic,
        }

    def _decode_trust_row(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        out["weak_gates"] = self._parse_json(out.pop("weak_gates_json"), [])
        out["strong_gates"] = self._parse_json(out.pop("strong_gates_json"), [])
        out["high_collapse"] = self._parse_json(out.pop("high_collapse_json"), [])
        out["likely_causes"] = self._parse_json(out.pop("likely_causes_json"), [])
        out["diagnostic"] = self._parse_json(out.pop("diagnostic_json"), {})
        out["low_trust_flag"] = bool(out["low_trust_flag"])
        return out

    def _fetch_trust_by_event(self, signal_event_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM trust_gradients WHERE signal_event_id = ?",
                (signal_event_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return self._decode_trust_row(row)

    def ingest_and_score(
        self,
        agent_address: str,
        payload: Dict[str, Any],
        payload_hash: str,
        audit_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        signal = self.ingest_dgc_signal(
            agent_address=agent_address,
            payload=payload,
            payload_hash=payload_hash,
            audit_hash=audit_hash,
        )

        existing = self._fetch_trust_by_event(signal["event_id"])
        if existing:
            return {
                "signal": signal,
                "gradient": existing,
                "idempotent_replay": bool(signal.get("_idempotent_replay", True)),
            }

        identity = self.latest_identity(agent_address)
        gradient = self._derive_gradient(signal=signal, identity=identity)

        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO trust_gradients (
                    signal_event_id, dgc_signal_id, agent_address, task_id, task_type, artifact_id,
                    trust_score, low_trust_flag, gate_component, mission_component, collapse_component,
                    self_alignment_component, affinity_match_component, weak_gates_json, strong_gates_json,
                    high_collapse_json, likely_causes_json, diagnostic_json, audit_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal["event_id"],
                    signal["id"],
                    agent_address,
                    signal.get("task_id"),
                    signal.get("task_type"),
                    signal.get("artifact_id"),
                    gradient["trust_score"],
                    int(gradient["low_trust_flag"]),
                    gradient["gate_component"],
                    gradient["mission_component"],
                    gradient["collapse_component"],
                    gradient["self_alignment_component"],
                    gradient["affinity_match_component"],
                    json.dumps(gradient["weak_gates"]),
                    json.dumps(gradient["strong_gates"]),
                    json.dumps(gradient["high_collapse"]),
                    json.dumps(gradient["likely_causes"]),
                    json.dumps(gradient["diagnostic"]),
                    audit_hash,
                    _utc_now(),
                ),
            )
            inserted = cursor.rowcount > 0

        stored = self._fetch_trust_by_event(signal["event_id"])
        if not stored:
            raise ValueError("trust_gradient_persist_failed")
        return {
            "signal": signal,
            "gradient": stored,
            "idempotent_replay": bool(signal.get("_idempotent_replay", False)) or (not inserted),
        }

    def attach_audit_hash(self, event_id: str, audit_hash: str) -> None:
        """Attach audit hash to persisted signal/gradient rows if not already set."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE dgc_signals
                SET audit_hash = COALESCE(audit_hash, ?)
                WHERE event_id = ?
                """,
                (audit_hash, event_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("signal_not_found")

            cursor.execute(
                """
                UPDATE trust_gradients
                SET audit_hash = COALESCE(audit_hash, ?)
                WHERE signal_event_id = ?
                """,
                (audit_hash, event_id),
            )

    def trust_history(self, agent_address: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM trust_gradients
                WHERE agent_address = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (agent_address, limit),
            )
            rows = cursor.fetchall()

        return [self._decode_trust_row(row) for row in rows]

    def latest_trust_for_agents(self, agent_addresses: List[str]) -> Dict[str, Dict[str, Any]]:
        deduped: List[str] = []
        seen: set[str] = set()
        for address in agent_addresses:
            normalized = str(address or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        if not deduped:
            return {}

        placeholders = ",".join("?" for _ in deduped)
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT t.*
                FROM trust_gradients t
                JOIN (
                    SELECT agent_address, MAX(id) AS max_id
                    FROM trust_gradients
                    WHERE agent_address IN ({placeholders})
                    GROUP BY agent_address
                ) latest
                ON latest.agent_address = t.agent_address
                AND latest.max_id = t.id
                """,
                tuple(deduped),
            )
            rows = cursor.fetchall()

        out: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            decoded = self._decode_trust_row(row)
            out[str(decoded["agent_address"])] = decoded
        return out

    def landscape(self, limit: int = 200) -> Dict[str, Any]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT t.*
                FROM trust_gradients t
                JOIN (
                    SELECT agent_address, MAX(id) AS max_id
                    FROM trust_gradients
                    GROUP BY agent_address
                ) latest
                ON latest.agent_address = t.agent_address
                AND latest.max_id = t.id
                ORDER BY t.trust_score DESC
                LIMIT ?
                """,
                (limit,),
            )
            trust_rows = [dict(r) for r in cursor.fetchall()]

            cursor.execute(
                """
                SELECT i.*
                FROM agent_identity_packets i
                JOIN (
                    SELECT agent_address, MAX(id) AS max_id
                    FROM agent_identity_packets
                    GROUP BY agent_address
                ) latest
                ON latest.agent_address = i.agent_address
                AND latest.max_id = i.id
                """
            )
            identities = {row["agent_address"]: dict(row) for row in cursor.fetchall()}

        nodes: List[Dict[str, Any]] = []
        for row in trust_rows:
            weak_gates = self._parse_json(row.pop("weak_gates_json"), [])
            strong_gates = self._parse_json(row.pop("strong_gates_json"), [])
            likely_causes = self._parse_json(row.pop("likely_causes_json"), [])
            diagnostic = self._parse_json(row.pop("diagnostic_json"), {})
            row.pop("high_collapse_json", None)
            row.pop("likely_causes_json", None)
            row.pop("diagnostic_json", None)

            identity = identities.get(row["agent_address"]) or {}
            affinity = self._parse_json(identity.get("task_affinity_json"), [])

            trust = float(row["trust_score"])
            if trust >= 0.75:
                color = "#2E8B57"
            elif trust >= 0.55:
                color = "#D9A441"
            else:
                color = "#C74A4A"

            y = (float(row["mission_component"]) + float(row["affinity_match_component"])) / 2.0
            nodes.append(
                {
                    "agent_address": row["agent_address"],
                    "alias": identity.get("alias") or row["agent_address"],
                    "base_model": identity.get("base_model"),
                    "perceived_role": identity.get("perceived_role"),
                    "task_affinity": affinity,
                    "trust_score": round(trust, 4),
                    "x": round(trust, 4),
                    "y": round(y, 4),
                    "low_trust_flag": bool(row["low_trust_flag"]),
                    "strong_gates": strong_gates[:5],
                    "weak_gates": weak_gates[:5],
                    "likely_causes": likely_causes,
                    "diagnostic": diagnostic,
                    "color": color,
                    "updated_at": row["created_at"],
                }
            )

        trust_values = [n["trust_score"] for n in nodes]
        summary = {
            "agent_count": len(nodes),
            "avg_trust": round(_safe_avg(trust_values, default=0.0), 4) if nodes else 0.0,
            "min_trust": round(min(trust_values), 4) if nodes else 0.0,
            "max_trust": round(max(trust_values), 4) if nodes else 0.0,
            "low_trust_count": sum(1 for n in nodes if n["low_trust_flag"]),
            "generated_at": _utc_now(),
        }
        return {"summary": summary, "nodes": nodes}
