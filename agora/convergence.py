"""
Convergence diagnostics for SAB.

This module implements the production coherence path:
agent output -> DGC scoring -> trust gradient -> convergence landscape.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
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
    MAX_TRUST_ADJUSTMENT_ABS = 0.60
    REPLAY_PENALTY = -0.12
    CROSS_AGENT_REPLAY_PENALTY = -0.18
    COLLUSION_PENALTY = -0.08
    ANTI_GAMING_SCAN_LIMIT = 500
    MAX_AFFINITY_ITEMS = 32
    MAX_AFFINITY_LEN = 80
    MAX_IDENTITY_METADATA_ITEMS = 64
    MAX_SIGNAL_METADATA_ITEMS = 96
    MAX_METADATA_KEY_LEN = 80
    MAX_IDENTITY_METADATA_JSON_BYTES = 16_384
    MAX_SIGNAL_METADATA_JSON_BYTES = 24_576
    DEFAULT_POLICY = {
        "version": 1,
        "replay_penalty": -0.12,
        "cross_agent_replay_penalty": -0.18,
        "collusion_penalty": -0.08,
        "outcome_pass_bonus": 0.05,
        "outcome_fail_penalty": -0.10,
        "human_acceptance_bonus": 0.08,
        "max_adjustment_abs": 0.60,
    }
    MIN_POLICY_VALUE = -0.60
    MAX_POLICY_VALUE = 0.60

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
        def ensure_column(cursor: sqlite3.Cursor, table: str, column_name: str, column_def: str) -> None:
            cursor.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in cursor.fetchall()}
            if column_name not in existing:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")

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
                    base_trust_score REAL NOT NULL DEFAULT 0.0,
                    trust_score REAL NOT NULL,
                    trust_adjustment REAL NOT NULL DEFAULT 0.0,
                    low_trust_flag INTEGER NOT NULL,
                    gate_component REAL NOT NULL,
                    mission_component REAL NOT NULL,
                    collapse_component REAL NOT NULL,
                    self_alignment_component REAL NOT NULL,
                    affinity_match_component REAL NOT NULL,
                    anti_gaming_flags_json TEXT NOT NULL DEFAULT '[]',
                    weak_gates_json TEXT NOT NULL,
                    strong_gates_json TEXT NOT NULL,
                    high_collapse_json TEXT NOT NULL,
                    likely_causes_json TEXT NOT NULL,
                    diagnostic_json TEXT NOT NULL,
                    adjustment_reviewer TEXT,
                    adjustment_reason TEXT,
                    adjusted_at TEXT,
                    audit_hash TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (dgc_signal_id) REFERENCES dgc_signals(id)
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS outcome_witness (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    agent_address TEXT NOT NULL,
                    recorded_by TEXT NOT NULL,
                    outcome_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS darwin_policy (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_json TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    updated_reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS darwin_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    dry_run INTEGER NOT NULL,
                    baseline_policy_json TEXT NOT NULL,
                    candidate_policy_json TEXT NOT NULL,
                    baseline_objective REAL NOT NULL,
                    candidate_objective REAL NOT NULL,
                    accepted INTEGER NOT NULL,
                    validation_json TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

            ensure_column(cursor, "trust_gradients", "base_trust_score", "base_trust_score REAL NOT NULL DEFAULT 0.0")
            ensure_column(cursor, "trust_gradients", "trust_adjustment", "trust_adjustment REAL NOT NULL DEFAULT 0.0")
            ensure_column(
                cursor,
                "trust_gradients",
                "anti_gaming_flags_json",
                "anti_gaming_flags_json TEXT NOT NULL DEFAULT '[]'",
            )
            ensure_column(cursor, "trust_gradients", "adjustment_reviewer", "adjustment_reviewer TEXT")
            ensure_column(cursor, "trust_gradients", "adjustment_reason", "adjustment_reason TEXT")
            ensure_column(cursor, "trust_gradients", "adjusted_at", "adjusted_at TEXT")
            cursor.execute(
                """
                UPDATE trust_gradients
                SET base_trust_score = trust_score
                WHERE base_trust_score = 0.0 AND trust_score != 0.0
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
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_outcome_event_created ON outcome_witness(event_id, created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_outcome_agent_created ON outcome_witness(agent_address, created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_darwin_runs_created ON darwin_runs(created_at DESC)"
            )

            cursor.execute("SELECT COUNT(*) FROM darwin_policy")
            if int(cursor.fetchone()[0] or 0) == 0:
                cursor.execute(
                    """
                    INSERT INTO darwin_policy (policy_json, updated_by, updated_reason, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        _canonical_json(self.DEFAULT_POLICY),
                        "system_bootstrap",
                        "initialize_default_policy",
                        _utc_now(),
                    ),
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

    def _normalize_affinity(self, values: Optional[List[str]]) -> List[str]:
        if not values:
            return []
        if len(values) > self.MAX_AFFINITY_ITEMS:
            raise ValueError("task_affinity_exceeds_max_entries")
        out: List[str] = []
        for item in values:
            norm = str(item).strip().lower()
            if not norm:
                continue
            if len(norm) > self.MAX_AFFINITY_LEN:
                raise ValueError("task_affinity_item_too_long")
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

    def _sanitize_metadata(
        self,
        raw: Any,
        *,
        max_items: int,
        max_json_bytes: int,
        error_prefix: str,
    ) -> Dict[str, Any]:
        metadata = raw if isinstance(raw, dict) else {"metadata_raw": str(raw)}
        if len(metadata) > max_items:
            raise ValueError(f"{error_prefix}_metadata_exceeds_max_entries")
        for key in metadata.keys():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{error_prefix}_metadata_key_invalid")
            if len(key) > self.MAX_METADATA_KEY_LEN:
                raise ValueError(f"{error_prefix}_metadata_key_too_long")
        try:
            encoded = _canonical_json(metadata).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{error_prefix}_metadata_not_json_serializable") from exc
        if len(encoded) > max_json_bytes:
            raise ValueError(f"{error_prefix}_metadata_exceeds_max_size")
        return metadata

    def _validate_policy(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        policy = dict(self.DEFAULT_POLICY)
        policy.update(raw or {})

        if "version" in policy:
            try:
                policy["version"] = int(policy["version"])
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid_policy_version") from exc
        else:
            policy["version"] = int(self.DEFAULT_POLICY["version"])

        for key in (
            "replay_penalty",
            "cross_agent_replay_penalty",
            "collusion_penalty",
            "outcome_pass_bonus",
            "outcome_fail_penalty",
            "human_acceptance_bonus",
            "max_adjustment_abs",
        ):
            try:
                value = float(policy[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid_policy_value_{key}") from exc
            if value < self.MIN_POLICY_VALUE or value > self.MAX_POLICY_VALUE:
                raise ValueError(f"policy_value_out_of_bounds_{key}")
            policy[key] = round(value, 4)
        policy["max_adjustment_abs"] = max(0.0, policy["max_adjustment_abs"])
        return policy

    def get_policy(self) -> Dict[str, Any]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM darwin_policy
                ORDER BY id DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
        if not row:
            return dict(self.DEFAULT_POLICY)
        raw = self._parse_json(row["policy_json"], {})
        policy = self._validate_policy(raw if isinstance(raw, dict) else {})
        policy["updated_by"] = row["updated_by"]
        policy["updated_reason"] = row["updated_reason"]
        policy["updated_at"] = row["created_at"]
        return policy

    def update_policy(
        self,
        policy: Dict[str, Any],
        *,
        updated_by: str,
        updated_reason: str,
    ) -> Dict[str, Any]:
        validated = self._validate_policy(policy)
        now = _utc_now()
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO darwin_policy (policy_json, updated_by, updated_reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    _canonical_json(validated),
                    updated_by,
                    updated_reason,
                    now,
                ),
            )
        out = dict(validated)
        out["updated_by"] = updated_by
        out["updated_reason"] = updated_reason
        out["updated_at"] = now
        return out

    def register_identity(
        self,
        agent_address: str,
        packet: Dict[str, Any],
        audit_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = _utc_now()
        affinity = self._normalize_affinity(packet.get("task_affinity"))
        metadata = self._sanitize_metadata(
            packet.get("metadata", {}),
            max_items=self.MAX_IDENTITY_METADATA_ITEMS,
            max_json_bytes=self.MAX_IDENTITY_METADATA_JSON_BYTES,
            error_prefix="identity",
        )

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
        if not gate_scores:
            raise ValueError("gate_scores_required")
        collapse_dimensions = self._normalize_score_map(payload.get("collapse_dimensions"))
        metadata = self._sanitize_metadata(
            payload.get("metadata", {}),
            max_items=self.MAX_SIGNAL_METADATA_ITEMS,
            max_json_bytes=self.MAX_SIGNAL_METADATA_JSON_BYTES,
            error_prefix="signal",
        )
        schema_version = str(payload.get("schema_version") or "dgc.v1")
        metadata.setdefault("schema_version", schema_version)

        mission_relevance = payload.get("mission_relevance")
        mission_value: Optional[float] = None
        if mission_relevance is not None:
            try:
                mission_value = round(_clamp(float(mission_relevance)), 4)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid_mission_relevance") from exc

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

    @staticmethod
    def _signal_fingerprint(payload: Dict[str, Any]) -> str:
        material = {
            "task_type": payload.get("task_type"),
            "artifact_id": payload.get("artifact_id"),
            "source_alias": payload.get("source_alias"),
            "gate_scores": payload.get("gate_scores") or {},
            "collapse_dimensions": payload.get("collapse_dimensions") or {},
            "mission_relevance": payload.get("mission_relevance"),
        }
        return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()

    def _detect_anti_gaming_flags(self, signal: Dict[str, Any], recent_limit: int = 200) -> List[str]:
        fingerprint = self._signal_fingerprint(signal)
        same_agent_replay_count = 0
        cross_agent_replay_count = 0
        artifact_cross_agent_count = 0
        alias_agent_set: set[str] = set()

        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT event_id, agent_address, artifact_id, source_alias,
                       gate_scores_json, collapse_dimensions_json, mission_relevance, task_type
                FROM dgc_signals
                ORDER BY id DESC
                LIMIT ?
                """,
                (recent_limit,),
            )
            rows = cursor.fetchall()

        for row in rows:
            if row["event_id"] == signal["event_id"]:
                continue
            row_gate = self._parse_json(row["gate_scores_json"], {})
            row_collapse = self._parse_json(row["collapse_dimensions_json"], {})
            row_payload = {
                "task_type": row["task_type"],
                "artifact_id": row["artifact_id"],
                "source_alias": row["source_alias"],
                "gate_scores": row_gate,
                "collapse_dimensions": row_collapse,
                "mission_relevance": row["mission_relevance"],
            }
            row_fp = self._signal_fingerprint(row_payload)
            row_agent = str(row["agent_address"])

            if row_fp == fingerprint:
                if row_agent == signal["agent_address"]:
                    same_agent_replay_count += 1
                else:
                    cross_agent_replay_count += 1

            if signal.get("artifact_id") and row["artifact_id"] == signal["artifact_id"] and row_agent != signal["agent_address"]:
                artifact_cross_agent_count += 1

            if signal.get("source_alias") and row["source_alias"] == signal["source_alias"]:
                alias_agent_set.add(row_agent)

        flags: List[str] = []
        if same_agent_replay_count >= 1:
            flags.append("replay_laundering_risk")
        if cross_agent_replay_count >= 1 or artifact_cross_agent_count >= 1:
            flags.append("cross_agent_replay_risk")
        alias_other_agents = alias_agent_set.difference({str(signal["agent_address"])})
        if signal.get("source_alias") and len(alias_other_agents) >= 2:
            flags.append("source_alias_collusion_risk")

        return sorted(set(flags))

    def _default_trust_adjustment(self, anti_gaming_flags: List[str]) -> float:
        policy = self.get_policy()
        max_abs = float(policy.get("max_adjustment_abs", self.MAX_TRUST_ADJUSTMENT_ABS))
        adjustment = 0.0
        if "replay_laundering_risk" in anti_gaming_flags:
            adjustment += float(policy.get("replay_penalty", self.REPLAY_PENALTY))
        if "cross_agent_replay_risk" in anti_gaming_flags:
            adjustment += float(policy.get("cross_agent_replay_penalty", self.CROSS_AGENT_REPLAY_PENALTY))
        if "source_alias_collusion_risk" in anti_gaming_flags:
            adjustment += float(policy.get("collusion_penalty", self.COLLUSION_PENALTY))
        return round(_clamp(adjustment, -max_abs, max_abs), 4)

    @staticmethod
    def _normalize_outcome_status(status: str) -> str:
        norm = str(status or "").strip().lower()
        if norm not in {"pass", "fail"}:
            raise ValueError("invalid_outcome_status")
        return norm

    @staticmethod
    def _normalize_outcome_type(outcome_type: str) -> str:
        norm = str(outcome_type or "").strip().lower()
        if norm not in {"tests", "smoke", "human_acceptance", "user_feedback"}:
            raise ValueError("invalid_outcome_type")
        return norm

    def _outcome_delta_for_record(self, policy: Dict[str, Any], outcome_type: str, status: str) -> float:
        status_norm = self._normalize_outcome_status(status)
        kind = self._normalize_outcome_type(outcome_type)
        if status_norm == "pass":
            bonus = float(policy.get("outcome_pass_bonus", self.DEFAULT_POLICY["outcome_pass_bonus"]))
            if kind == "human_acceptance":
                bonus += float(
                    policy.get("human_acceptance_bonus", self.DEFAULT_POLICY["human_acceptance_bonus"])
                )
            return round(bonus, 4)
        return round(float(policy.get("outcome_fail_penalty", self.DEFAULT_POLICY["outcome_fail_penalty"])), 4)

    def _outcome_adjustment_for_event(self, event_id: str, policy: Dict[str, Any]) -> float:
        outcomes = self.outcomes_for_event(event_id)
        if not outcomes:
            return 0.0
        adjustment = 0.0
        for outcome in outcomes:
            adjustment += self._outcome_delta_for_record(
                policy,
                str(outcome.get("outcome_type", "")),
                str(outcome.get("status", "")),
            )
        max_abs = float(policy.get("max_adjustment_abs", self.MAX_TRUST_ADJUSTMENT_ABS))
        return round(_clamp(adjustment, -max_abs, max_abs), 4)

    def _component_adjustments(self, gradient: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, float]:
        diagnostic = dict(gradient.get("diagnostic") or {})
        anti = diagnostic.get("anti_gaming_auto_adjustment")
        if anti is None:
            anti = self._default_trust_adjustment(list(gradient.get("anti_gaming_flags") or []))
        outcome = diagnostic.get("outcome_adjustment", 0.0)
        manual = diagnostic.get("manual_adjustment")
        total_existing = float(gradient.get("trust_adjustment") or 0.0)
        if manual is None:
            manual = total_existing - float(anti) - float(outcome)
        max_abs = float(policy.get("max_adjustment_abs", self.MAX_TRUST_ADJUSTMENT_ABS))
        return {
            "anti": round(float(anti), 4),
            "outcome": round(float(outcome), 4),
            "manual": round(float(_clamp(float(manual), -max_abs, max_abs)), 4),
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
        anti_gaming_flags: Optional[List[str]] = None,
        trust_adjustment: float = 0.0,
    ) -> Dict[str, Any]:
        anti_flags = sorted(set(anti_gaming_flags or []))
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
        base_trust_score = round(trust_score, 4)
        trust_adjustment = round(
            _clamp(float(trust_adjustment), -self.MAX_TRUST_ADJUSTMENT_ABS, self.MAX_TRUST_ADJUSTMENT_ABS), 4
        )
        trust_score = round(_clamp(base_trust_score + trust_adjustment), 4)

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
        if anti_flags:
            likely_causes.append("anti_gaming_review_required")
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
            "anti_gaming_flags": anti_flags,
            "base_trust_score": base_trust_score,
            "anti_gaming_auto_adjustment": trust_adjustment,
            "outcome_adjustment": 0.0,
            "manual_adjustment": 0.0,
            "trust_adjustment": trust_adjustment,
            "effective_trust_score": trust_score,
            "likely_causes": likely_causes,
            "suggested_action": (
                "reroute_to_affinity_or_improve_context" if low_trust_flag else "continue_gradient_path"
            ),
        }

        return {
            "trust_score": trust_score,
            "base_trust_score": base_trust_score,
            "trust_adjustment": trust_adjustment,
            "low_trust_flag": bool(low_trust_flag),
            "gate_component": round(gate_component, 4),
            "mission_component": round(mission_component, 4),
            "collapse_component": round(collapse_component, 4),
            "self_alignment_component": round(self_alignment_component, 4),
            "affinity_match_component": round(affinity_match_component, 4),
            "anti_gaming_flags": anti_flags,
            "weak_gates": weak_gates,
            "strong_gates": strong_gates,
            "high_collapse": high_collapse,
            "likely_causes": likely_causes,
            "diagnostic": diagnostic,
        }

    def _decode_trust_row(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        out["weak_gates"] = self._parse_json(out.pop("weak_gates_json", "[]"), [])
        out["strong_gates"] = self._parse_json(out.pop("strong_gates_json", "[]"), [])
        out["high_collapse"] = self._parse_json(out.pop("high_collapse_json", "[]"), [])
        out["anti_gaming_flags"] = self._parse_json(out.pop("anti_gaming_flags_json", "[]"), [])
        out["likely_causes"] = self._parse_json(out.pop("likely_causes_json", "[]"), [])
        out["diagnostic"] = self._parse_json(out.pop("diagnostic_json", "{}"), {})
        out["low_trust_flag"] = bool(out.get("low_trust_flag"))
        out["trust_adjustment"] = round(float(out.get("trust_adjustment") or 0.0), 4)
        base = out.get("base_trust_score")
        if base is None:
            base = float(out.get("trust_score") or 0.0) - out["trust_adjustment"]
        out["base_trust_score"] = round(float(base), 4)
        out["trust_score"] = round(float(out.get("trust_score") or 0.0), 4)
        out["effective_trust_score"] = out["trust_score"]
        if out["anti_gaming_flags"] and "anti_gaming_review_required" not in out["likely_causes"]:
            out["likely_causes"] = sorted(set(out["likely_causes"] + ["anti_gaming_review_required"]))
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

        anti_gaming_flags = self._detect_anti_gaming_flags(signal)
        default_adjustment = self._default_trust_adjustment(anti_gaming_flags)
        identity = self.latest_identity(agent_address)
        gradient = self._derive_gradient(
            signal=signal,
            identity=identity,
            anti_gaming_flags=anti_gaming_flags,
            trust_adjustment=default_adjustment,
        )

        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO trust_gradients (
                    signal_event_id, dgc_signal_id, agent_address, task_id, task_type, artifact_id,
                    base_trust_score, trust_score, trust_adjustment, low_trust_flag,
                    gate_component, mission_component, collapse_component,
                    self_alignment_component, affinity_match_component, anti_gaming_flags_json,
                    weak_gates_json, strong_gates_json, high_collapse_json,
                    likely_causes_json, diagnostic_json, audit_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal["event_id"],
                    signal["id"],
                    agent_address,
                    signal.get("task_id"),
                    signal.get("task_type"),
                    signal.get("artifact_id"),
                    gradient["base_trust_score"],
                    gradient["trust_score"],
                    gradient["trust_adjustment"],
                    int(gradient["low_trust_flag"]),
                    gradient["gate_component"],
                    gradient["mission_component"],
                    gradient["collapse_component"],
                    gradient["self_alignment_component"],
                    gradient["affinity_match_component"],
                    json.dumps(gradient["anti_gaming_flags"]),
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

    def set_trust_adjustment(
        self,
        event_id: str,
        reviewer_address: str,
        trust_adjustment: float,
        reason: str,
    ) -> Dict[str, Any]:
        policy = self.get_policy()
        max_abs = float(policy.get("max_adjustment_abs", self.MAX_TRUST_ADJUSTMENT_ABS))
        target_total = round(_clamp(float(trust_adjustment), -max_abs, max_abs), 4)
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM trust_gradients
                WHERE signal_event_id = ?
                LIMIT 1
                """,
                (event_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("trust_event_not_found")
            current = self._decode_trust_row(row)
            components = self._component_adjustments(current, policy)

            base = float(current.get("base_trust_score") or 0.0)
            manual = round(target_total - components["anti"] - components["outcome"], 4)
            total = round(_clamp(components["anti"] + components["outcome"] + manual, -max_abs, max_abs), 4)
            effective = round(_clamp(base + total), 4)
            low_trust = int(effective < self.LOW_TRUST_THRESHOLD)

            likely = list(current.get("likely_causes") or [])
            if manual < 0.0:
                likely = sorted(set(likely + ["manual_clawback"]))
            else:
                likely = [x for x in likely if x != "manual_clawback"]

            diagnostic = dict(current.get("diagnostic") or {})
            diagnostic["base_trust_score"] = base
            diagnostic["anti_gaming_auto_adjustment"] = components["anti"]
            diagnostic["outcome_adjustment"] = components["outcome"]
            diagnostic["manual_adjustment"] = manual
            diagnostic["trust_adjustment"] = total
            diagnostic["effective_trust_score"] = effective
            diagnostic["reviewer_address"] = reviewer_address
            diagnostic["adjustment_reason"] = reason

            cursor.execute(
                """
                UPDATE trust_gradients
                SET trust_adjustment = ?,
                    trust_score = ?,
                    low_trust_flag = ?,
                    likely_causes_json = ?,
                    diagnostic_json = ?,
                    adjustment_reviewer = ?,
                    adjustment_reason = ?,
                    adjusted_at = ?
                WHERE signal_event_id = ?
                """,
                (
                    total,
                    effective,
                    low_trust,
                    json.dumps(likely),
                    json.dumps(diagnostic),
                    reviewer_address,
                    reason,
                    _utc_now(),
                    event_id,
                ),
            )

        updated = self._fetch_trust_by_event(event_id)
        if not updated:
            raise ValueError("trust_event_not_found")
        return updated

    def apply_clawback(
        self,
        event_id: str,
        reviewer_address: str,
        penalty: float,
        reason: str,
    ) -> Dict[str, Any]:
        existing = self._fetch_trust_by_event(event_id)
        if not existing:
            raise ValueError("trust_event_not_found")
        current_adjustment = float(existing.get("trust_adjustment") or 0.0)
        target_adjustment = current_adjustment - abs(float(penalty))
        return self.set_trust_adjustment(
            event_id=event_id,
            reviewer_address=reviewer_address,
            trust_adjustment=target_adjustment,
            reason=reason,
        )

    def outcomes_for_event(self, event_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM outcome_witness
                WHERE event_id = ?
                ORDER BY id ASC
                """,
                (event_id,),
            )
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["evidence"] = self._parse_json(row.pop("evidence_json"), {})
        return rows

    def record_outcome(
        self,
        event_id: str,
        *,
        recorded_by: str,
        outcome_type: str,
        status: str,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        outcome_type_norm = self._normalize_outcome_type(outcome_type)
        status_norm = self._normalize_outcome_status(status)
        evidence_obj = evidence if isinstance(evidence, dict) else {"note": str(evidence or "")}

        existing = self._fetch_trust_by_event(event_id)
        if not existing:
            raise ValueError("trust_event_not_found")

        now = _utc_now()
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO outcome_witness (
                    event_id, agent_address, recorded_by, outcome_type, status, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    existing["agent_address"],
                    recorded_by,
                    outcome_type_norm,
                    status_norm,
                    json.dumps(evidence_obj),
                    now,
                ),
            )
            outcome_id = cursor.lastrowid

        policy = self.get_policy()
        outcomes = self.outcomes_for_event(event_id)
        outcome_adjustment = self._outcome_adjustment_for_event(event_id, policy)
        current = self._fetch_trust_by_event(event_id)
        if not current:
            raise ValueError("trust_event_not_found")
        components = self._component_adjustments(current, policy)
        max_abs = float(policy.get("max_adjustment_abs", self.MAX_TRUST_ADJUSTMENT_ABS))
        total_adjustment = round(
            _clamp(components["anti"] + outcome_adjustment + components["manual"], -max_abs, max_abs), 4
        )
        base = float(current.get("base_trust_score") or 0.0)
        trust_score = round(_clamp(base + total_adjustment), 4)
        low_trust = int(trust_score < self.LOW_TRUST_THRESHOLD)

        likely = list(current.get("likely_causes") or [])
        if status_norm == "pass":
            likely = sorted(set([x for x in likely if x != "verified_failure"] + ["verified_outcome"]))
        else:
            likely = sorted(set([x for x in likely if x != "verified_outcome"] + ["verified_failure"]))

        diagnostic = dict(current.get("diagnostic") or {})
        diagnostic["base_trust_score"] = base
        diagnostic["anti_gaming_auto_adjustment"] = components["anti"]
        diagnostic["outcome_adjustment"] = outcome_adjustment
        diagnostic["manual_adjustment"] = components["manual"]
        diagnostic["trust_adjustment"] = total_adjustment
        diagnostic["effective_trust_score"] = trust_score
        diagnostic["outcomes_seen"] = len(outcomes)
        diagnostic["latest_outcome"] = {
            "outcome_type": outcome_type_norm,
            "status": status_norm,
            "recorded_by": recorded_by,
            "recorded_at": now,
        }

        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE trust_gradients
                SET trust_adjustment = ?,
                    trust_score = ?,
                    low_trust_flag = ?,
                    likely_causes_json = ?,
                    diagnostic_json = ?,
                    adjusted_at = ?
                WHERE signal_event_id = ?
                """,
                (
                    total_adjustment,
                    trust_score,
                    low_trust,
                    json.dumps(likely),
                    json.dumps(diagnostic),
                    now,
                    event_id,
                ),
            )

        updated = self._fetch_trust_by_event(event_id)
        if not updated:
            raise ValueError("trust_event_not_found")
        return {
            "outcome": {
                "id": outcome_id,
                "event_id": event_id,
                "outcome_type": outcome_type_norm,
                "status": status_norm,
                "recorded_by": recorded_by,
                "evidence": evidence_obj,
                "created_at": now,
            },
            "gradient": updated,
        }

    def _events_with_outcomes(self, limit: int = 400) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT t.*
                FROM trust_gradients t
                WHERE EXISTS (
                    SELECT 1 FROM outcome_witness o WHERE o.event_id = t.signal_event_id
                )
                ORDER BY t.id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = [self._decode_trust_row(row) for row in cursor.fetchall()]
        for row in rows:
            outcomes = self.outcomes_for_event(row["signal_event_id"])
            row["outcomes"] = outcomes
        return rows

    def _simulate_adjustment_for_row(self, row: Dict[str, Any], policy: Dict[str, Any]) -> float:
        anti = self._default_trust_adjustment(list(row.get("anti_gaming_flags") or []))
        manual = float((row.get("diagnostic") or {}).get("manual_adjustment", 0.0) or 0.0)
        outcome_adj = 0.0
        for outcome in row.get("outcomes", []):
            outcome_adj += self._outcome_delta_for_record(
                policy,
                str(outcome.get("outcome_type", "")),
                str(outcome.get("status", "")),
            )
        max_abs = float(policy.get("max_adjustment_abs", self.MAX_TRUST_ADJUSTMENT_ABS))
        return round(_clamp(anti + manual + outcome_adj, -max_abs, max_abs), 4)

    def evaluate_policy_objective(self, policy: Dict[str, Any], *, limit: int = 400) -> Dict[str, Any]:
        validated = self._validate_policy(policy)
        rows = self._events_with_outcomes(limit=limit)
        if not rows:
            return {"objective": 0.0, "coverage": 0, "false_positive_rate": 0.0}

        scores: List[float] = []
        flagged_total = 0
        flagged_pass = 0
        for row in rows:
            outcomes = row.get("outcomes") or []
            if not outcomes:
                continue
            pass_ratio = _safe_avg(
                [1.0 if str(o.get("status")) == "pass" else 0.0 for o in outcomes],
                default=0.0,
            )
            base = float(row.get("base_trust_score") or 0.0)
            adjustment = self._simulate_adjustment_for_row(row, validated)
            effective = _clamp(base + adjustment)
            scores.append(1.0 - abs(effective - pass_ratio))

            flags = list(row.get("anti_gaming_flags") or [])
            if flags:
                flagged_total += 1
                if pass_ratio >= 0.66:
                    flagged_pass += 1

        objective = round(_safe_avg(scores, default=0.0), 6)
        false_positive_rate = round((flagged_pass / flagged_total), 6) if flagged_total else 0.0
        return {
            "objective": objective,
            "coverage": len(scores),
            "false_positive_rate": false_positive_rate,
        }

    def _propose_policy_candidate(self, policy: Dict[str, Any], *, limit: int = 400) -> Dict[str, Any]:
        baseline = self._validate_policy(policy)
        rows = self._events_with_outcomes(limit=limit)
        if not rows:
            candidate = dict(baseline)
            candidate["version"] = int(baseline["version"]) + 1
            return candidate

        flagged = 0
        false_positive = 0
        true_positive = 0
        all_pass_ratios: List[float] = []
        for row in rows:
            outcomes = row.get("outcomes") or []
            if not outcomes:
                continue
            pass_ratio = _safe_avg(
                [1.0 if str(o.get("status")) == "pass" else 0.0 for o in outcomes],
                default=0.0,
            )
            all_pass_ratios.append(pass_ratio)
            if row.get("anti_gaming_flags"):
                flagged += 1
                if pass_ratio >= 0.66:
                    false_positive += 1
                elif pass_ratio <= 0.33:
                    true_positive += 1

        candidate = dict(baseline)
        step_penalty = 0.02
        if false_positive > true_positive:
            candidate["replay_penalty"] = round(candidate["replay_penalty"] + step_penalty, 4)
            candidate["cross_agent_replay_penalty"] = round(
                candidate["cross_agent_replay_penalty"] + step_penalty,
                4,
            )
            candidate["collusion_penalty"] = round(candidate["collusion_penalty"] + step_penalty, 4)
        elif true_positive > false_positive:
            candidate["replay_penalty"] = round(candidate["replay_penalty"] - step_penalty, 4)
            candidate["cross_agent_replay_penalty"] = round(
                candidate["cross_agent_replay_penalty"] - step_penalty,
                4,
            )
            candidate["collusion_penalty"] = round(candidate["collusion_penalty"] - step_penalty, 4)

        avg_pass = _safe_avg(all_pass_ratios, default=0.5)
        if avg_pass >= 0.70:
            candidate["outcome_pass_bonus"] = round(candidate["outcome_pass_bonus"] + 0.01, 4)
            candidate["outcome_fail_penalty"] = round(candidate["outcome_fail_penalty"] + 0.01, 4)
        elif avg_pass <= 0.40:
            candidate["outcome_pass_bonus"] = round(candidate["outcome_pass_bonus"] - 0.01, 4)
            candidate["outcome_fail_penalty"] = round(candidate["outcome_fail_penalty"] - 0.01, 4)

        candidate["version"] = int(baseline["version"]) + 1
        return self._validate_policy(candidate)

    @staticmethod
    def _run_validation_commands(commands: List[str], cwd: Path) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        ok = True
        for command in commands:
            proc = subprocess.run(
                command,
                cwd=str(cwd),
                shell=True,
                check=False,
                capture_output=True,
                text=True,
            )
            entry = {
                "command": command,
                "returncode": int(proc.returncode),
                "stdout_tail": proc.stdout[-1200:],
                "stderr_tail": proc.stderr[-1200:],
            }
            results.append(entry)
            if proc.returncode != 0:
                ok = False
                break
        return {"ok": ok, "results": results}

    def run_darwin_cycle(
        self,
        *,
        reviewer: str,
        reason: str,
        dry_run: bool = True,
        run_validation: bool = False,
        validation_commands: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        baseline_policy = self.get_policy()
        candidate_policy = self._propose_policy_candidate(baseline_policy)

        baseline_eval = self.evaluate_policy_objective(baseline_policy)
        candidate_eval = self.evaluate_policy_objective(candidate_policy)

        validation = {"ok": True, "results": []}
        if run_validation:
            default_commands = [
                "python3 -m pytest tests/test_convergence.py -q",
                "bash scripts/smoke_test.sh",
            ]
            validation = self._run_validation_commands(
                validation_commands or default_commands,
                cwd=self.db_path.parent.parent if self.db_path.name else Path("."),
            )

        improvement = float(candidate_eval["objective"]) - float(baseline_eval["objective"])
        accepted = improvement > 0.002 and bool(validation.get("ok", True))

        active_policy = baseline_policy
        if accepted and not dry_run:
            active_policy = self.update_policy(
                candidate_policy,
                updated_by=reviewer,
                updated_reason=reason,
            )

        run_id = hashlib.sha256(
            _canonical_json(
                {
                    "baseline": baseline_policy,
                    "candidate": candidate_policy,
                    "reason": reason,
                    "reviewer": reviewer,
                    "ts": _utc_now(),
                }
            ).encode("utf-8")
        ).hexdigest()[:20]

        notes = (
            "accepted" if (accepted and not dry_run) else
            "candidate_better_but_dry_run" if accepted else
            "candidate_not_improved_or_validation_failed"
        )
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO darwin_runs (
                    run_id, status, dry_run, baseline_policy_json, candidate_policy_json,
                    baseline_objective, candidate_objective, accepted, validation_json, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    "completed",
                    int(bool(dry_run)),
                    _canonical_json(baseline_policy),
                    _canonical_json(candidate_policy),
                    float(baseline_eval["objective"]),
                    float(candidate_eval["objective"]),
                    int(bool(accepted and (not dry_run))),
                    json.dumps(validation),
                    notes,
                    _utc_now(),
                ),
            )

        return {
            "run_id": run_id,
            "accepted": bool(accepted and (not dry_run)),
            "accepted_if_not_dry_run": bool(accepted),
            "dry_run": bool(dry_run),
            "baseline": baseline_eval,
            "candidate": candidate_eval,
            "improvement": round(improvement, 6),
            "validation": validation,
            "baseline_policy": baseline_policy,
            "candidate_policy": candidate_policy,
            "active_policy": active_policy,
            "notes": notes,
        }

    def darwin_status(self) -> Dict[str, Any]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM darwin_runs
                ORDER BY id DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
        latest = None
        if row:
            latest = dict(row)
            latest["baseline_policy"] = self._parse_json(latest.pop("baseline_policy_json"), {})
            latest["candidate_policy"] = self._parse_json(latest.pop("candidate_policy_json"), {})
            latest["validation"] = self._parse_json(latest.pop("validation_json"), {})
            latest["dry_run"] = bool(latest.get("dry_run"))
            latest["accepted"] = bool(latest.get("accepted"))
        return {"policy": self.get_policy(), "latest_run": latest}

    def anti_gaming_report(self, limit: int = ANTI_GAMING_SCAN_LIMIT) -> Dict[str, Any]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM trust_gradients
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = [self._decode_trust_row(row) for row in cursor.fetchall()]

            cursor.execute(
                """
                SELECT source_alias, COUNT(*) AS c, COUNT(DISTINCT agent_address) AS a
                FROM dgc_signals
                WHERE source_alias IS NOT NULL AND TRIM(source_alias) != ''
                GROUP BY source_alias
                HAVING a >= 3
                ORDER BY a DESC, c DESC
                LIMIT 50
                """
            )
            alias_clusters = [
                {
                    "source_alias": row["source_alias"],
                    "signal_count": int(row["c"]),
                    "agent_count": int(row["a"]),
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT artifact_id, COUNT(*) AS c, COUNT(DISTINCT agent_address) AS a
                FROM dgc_signals
                WHERE artifact_id IS NOT NULL AND TRIM(artifact_id) != ''
                GROUP BY artifact_id
                HAVING a >= 2
                ORDER BY a DESC, c DESC
                LIMIT 50
                """
            )
            artifact_replays = [
                {
                    "artifact_id": row["artifact_id"],
                    "signal_count": int(row["c"]),
                    "agent_count": int(row["a"]),
                }
                for row in cursor.fetchall()
            ]

        suspicious_events: List[Dict[str, Any]] = []
        flag_counts: Dict[str, int] = {}
        for row in rows:
            flags = list(row.get("anti_gaming_flags") or [])
            if flags or float(row.get("trust_adjustment") or 0.0) < 0.0:
                suspicious_events.append(
                    {
                        "signal_event_id": row["signal_event_id"],
                        "agent_address": row["agent_address"],
                        "trust_score": row["trust_score"],
                        "base_trust_score": row.get("base_trust_score"),
                        "trust_adjustment": row.get("trust_adjustment", 0.0),
                        "anti_gaming_flags": flags,
                        "likely_causes": row.get("likely_causes", []),
                        "updated_at": row.get("created_at"),
                    }
                )
            for flag in flags:
                flag_counts[flag] = flag_counts.get(flag, 0) + 1

        summary = {
            "scanned_events": len(rows),
            "suspicious_count": len(suspicious_events),
            "flag_counts": flag_counts,
            "collusion_alias_cluster_count": len(alias_clusters),
            "cross_agent_artifact_replay_count": len(artifact_replays),
            "generated_at": _utc_now(),
        }
        return {
            "summary": summary,
            "suspicious_events": suspicious_events[:100],
            "collusion_alias_clusters": alias_clusters,
            "cross_agent_artifact_replays": artifact_replays,
        }

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
        for raw in trust_rows:
            row = self._decode_trust_row(raw)
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
                    "base_trust_score": row.get("base_trust_score", trust),
                    "trust_adjustment": row.get("trust_adjustment", 0.0),
                    "anti_gaming_flags": list(row.get("anti_gaming_flags", [])),
                    "strong_gates": list(row.get("strong_gates", []))[:5],
                    "weak_gates": list(row.get("weak_gates", []))[:5],
                    "likely_causes": list(row.get("likely_causes", [])),
                    "diagnostic": dict(row.get("diagnostic", {})),
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
