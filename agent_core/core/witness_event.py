#!/usr/bin/env python3
"""WitnessEvent: append-only, hash-chained event log.

This is intentionally minimal:
  - JSON Lines storage
  - canonical JSON serialization
  - per-event SHA256 hash

It gives you "no silent edits" for any pipeline step that mutates state.

WITNESS LAYER BOUNDARY:
- This module is the agent_core witness (artifact derivation provenance):
  transformation/ingestion events inside capability pipelines.
- Publication/moderation provenance is intentionally separate and lives in
  `agora/witness.py`.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _utc_now_iso() -> str:
    # RFC3339-ish with Z suffix
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WitnessEvent:
    event_id: str
    ts: str
    actor: str
    action: str
    subject: str
    meta: Dict[str, Any] = field(default_factory=dict)
    prev_hash: str = ""
    hash: str = ""

    def payload_without_hash(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "ts": self.ts,
            "actor": self.actor,
            "action": self.action,
            "subject": self.subject,
            "meta": self.meta,
            "prev_hash": self.prev_hash,
        }

    def compute_hash(self) -> str:
        return _sha256_hex(_canonical_json(self.payload_without_hash()))

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.payload_without_hash())
        d["hash"] = self.hash
        return d


def new_event(*, actor: str, action: str, subject: str, meta: Optional[Dict[str, Any]] = None) -> WitnessEvent:
    return WitnessEvent(
        event_id=str(uuid.uuid4()),
        ts=_utc_now_iso(),
        actor=actor,
        action=action,
        subject=subject,
        meta=meta or {},
    )


def append_event(log_path: Path | str, event: WitnessEvent) -> WitnessEvent:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    prev_hash = ""
    if path.exists():
        try:
            last = None
            for last in _iter_events(path):
                pass
            if last:
                prev_hash = str(last.get("hash", ""))
        except Exception:
            # If log is corrupt, still write but mark prev_hash unknown.
            prev_hash = ""

    event2 = WitnessEvent(
        event_id=event.event_id,
        ts=event.ts,
        actor=event.actor,
        action=event.action,
        subject=event.subject,
        meta=event.meta,
        prev_hash=prev_hash,
    )
    h = event2.compute_hash()
    event3 = WitnessEvent(
        event_id=event2.event_id,
        ts=event2.ts,
        actor=event2.actor,
        action=event2.action,
        subject=event2.subject,
        meta=event2.meta,
        prev_hash=event2.prev_hash,
        hash=h,
    )

    with path.open("a", encoding="utf-8") as f:
        f.write(_canonical_json(event3.to_dict()) + "\n")
    return event3


def _iter_events(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def verify_log(log_path: Path | str) -> Dict[str, Any]:
    """Verify a witness log. Returns a summary dict."""
    path = Path(log_path)
    if not path.exists():
        return {"valid": True, "records": 0, "errors": []}

    errors: List[str] = []
    prev_hash = ""
    records = 0

    for i, ev in enumerate(_iter_events(path)):
        records += 1
        expected_prev = prev_hash
        actual_prev = str(ev.get("prev_hash", ""))
        if actual_prev != expected_prev:
            errors.append(f"prev_hash mismatch at index {i}: expected {expected_prev}, got {actual_prev}")

        # recompute hash
        payload = dict(ev)
        payload.pop("hash", None)
        expected_hash = _sha256_hex(_canonical_json(payload))
        actual_hash = str(ev.get("hash", ""))
        if actual_hash != expected_hash:
            errors.append(f"hash mismatch at index {i}")

        prev_hash = actual_hash

    return {"valid": not errors, "records": records, "errors": errors, "last_hash": prev_hash}
