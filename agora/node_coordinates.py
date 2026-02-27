#!/usr/bin/env python3
"""
Canonical node-coordinate helpers for SAB lattice routing.

Used by:
- API claim-grade submission routing
- claim packet scaffolding and governance validation
"""

from __future__ import annotations

import re
from typing import Optional


NODE_COORDINATE_RE = re.compile(r"^node[_-]?(\d{1,2})(?:_.*)?$", re.IGNORECASE)
ANCHOR_NODE_ID_RE = re.compile(r"^anchor-(\d{1,2})-")


def normalize_node_coordinate(value: Optional[str]) -> Optional[str]:
    """
    Normalize coordinate variants to canonical Node_XX format.

    Accepts:
    - "Node_01", "node-1", "node1", "1"
    Returns:
    - "Node_01"
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= 49:
            return f"Node_{idx:02d}"
        raise ValueError("node_coordinate index must be between 1 and 49")

    match = NODE_COORDINATE_RE.match(raw)
    if not match:
        raise ValueError("node_coordinate must be Node_01..Node_49")
    idx = int(match.group(1))
    if idx < 1 or idx > 49:
        raise ValueError("node_coordinate index must be between 1 and 49")
    return f"Node_{idx:02d}"


def infer_node_coordinate_from_node_id(node_id: str) -> Optional[str]:
    """
    Infer lattice coordinate from known node-id naming conventions.

    Current convention:
    - anchor-01-... -> Node_01
    """
    raw = str(node_id).strip()
    if not raw:
        return None

    match = ANCHOR_NODE_ID_RE.match(raw)
    if not match:
        return None

    idx = int(match.group(1))
    if idx < 1 or idx > 49:
        return None
    return f"Node_{idx:02d}"


def resolve_node_coordinate(
    *,
    node_id: str,
    node_coordinate: Optional[str],
    required: bool,
) -> Optional[str]:
    """
    Resolve canonical coordinate from node_id and/or explicit coordinate.

    Rules:
    - explicit coordinate, if present, must be valid
    - if coordinate can be inferred from node_id, explicit coordinate must match
    - when required=True, one of explicit/inferred must exist
    """
    explicit = normalize_node_coordinate(node_coordinate) if node_coordinate is not None else None
    inferred = infer_node_coordinate_from_node_id(node_id)

    if explicit and inferred and explicit != inferred:
        raise ValueError(
            f"node_coordinate {explicit} does not align with node_id {node_id} (expected {inferred})"
        )

    resolved = explicit or inferred
    if required and not resolved:
        raise ValueError("node_coordinate is required and could not be inferred from node_id")
    return resolved

