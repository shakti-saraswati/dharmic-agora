from __future__ import annotations

import pytest
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agora.node_coordinates import (
    infer_node_coordinate_from_node_id,
    normalize_node_coordinate,
    resolve_node_coordinate,
)


def test_normalize_node_coordinate_variants() -> None:
    assert normalize_node_coordinate("1") == "Node_01"
    assert normalize_node_coordinate("node_7") == "Node_07"
    assert normalize_node_coordinate("Node-12") == "Node_12"
    assert normalize_node_coordinate("NODE49") == "Node_49"


def test_normalize_node_coordinate_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        normalize_node_coordinate("Node_00")
    with pytest.raises(ValueError):
        normalize_node_coordinate("Node_50")


def test_infer_node_coordinate_from_anchor_node_id() -> None:
    assert infer_node_coordinate_from_node_id("anchor-01-math-formal") == "Node_01"
    assert infer_node_coordinate_from_node_id("anchor-07-dharmic-jain-epistemics") == "Node_07"
    assert infer_node_coordinate_from_node_id("custom-node-id") is None


def test_resolve_node_coordinate_requires_presence_when_requested() -> None:
    with pytest.raises(ValueError):
        resolve_node_coordinate(
            node_id="custom-node-id",
            node_coordinate=None,
            required=True,
        )


def test_resolve_node_coordinate_rejects_mismatch() -> None:
    with pytest.raises(ValueError):
        resolve_node_coordinate(
            node_id="anchor-03-ml-intelligence-engineering",
            node_coordinate="Node_07",
            required=True,
        )


def test_resolve_node_coordinate_prefers_canonical_alignment() -> None:
    resolved = resolve_node_coordinate(
        node_id="anchor-03-ml-intelligence-engineering",
        node_coordinate="node_3",
        required=True,
    )
    assert resolved == "Node_03"
