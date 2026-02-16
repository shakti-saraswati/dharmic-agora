from __future__ import annotations

import sys
from pathlib import Path

# Pytest 9's import mode can omit repo root from sys.path when running `pytest tests/`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agora.gates import GateResult, OrthogonalGates, verify_content


def test_orthogonal_gates_empty_is_rejected():
    out = OrthogonalGates().evaluate({"body": ""}, agent_telos="")
    assert out["admitted"] is False
    assert out["passed_count"] == 0
    assert set(out["dimensions"].keys()) == {"structural_rigor", "build_artifacts", "telos_alignment"}


def test_orthogonal_gates_known_good_input_is_admitted():
    body = "\n".join(
        [
            "# Title",
            "",
            "Some text with enough structure to pass.",
            "",
            "```python",
            "print('x')",
            "```",
            "",
            "https://example.com",
        ]
    )
    out = OrthogonalGates().evaluate({"body": body}, agent_telos="testing")
    assert out["admitted"] is True
    assert out["passed_count"] >= 2
    assert out["dimensions"]["build_artifacts"]["passed"] is True


def test_gate_protocol_includes_satya_ahimsa_witness():
    passed, evidence, _ = verify_content(
        "This is a harmless, factual note with enough length to pass required gates.",
        author_address="a" * 16,
        context={},
    )
    assert passed is True

    by_gate = {e.gate_name: e for e in evidence}
    assert by_gate["satya"].result in {GateResult.PASSED, GateResult.WARNING}
    assert by_gate["ahimsa"].result == GateResult.PASSED
    assert by_gate["witness"].result == GateResult.PASSED
