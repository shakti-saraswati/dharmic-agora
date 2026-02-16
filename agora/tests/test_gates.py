"""Tests for SAB 8-Dimension Orthogonal Gate System."""
import json
from pathlib import Path

import pytest
from agora.gates import GateResult, OrthogonalGates, evaluate_content, verify_content


@pytest.fixture
def gates():
    return OrthogonalGates()


class TestOrthogonalGates:
    def test_genuine_research_passes(self, gates):
        content = {
            "body": (
                "## Agent Coordination Measurement\n\n"
                "Our research suggests that oriented agent coordination produces "
                "qualitatively different outcomes than unoriented coordination. "
                "The evidence from depth measurement experiments implies that "
                "coherence over virality and build artifacts over performance "
                "create tools and knowledge that persist and compound.\n\n"
                "```python\ndef compute_depth(text): pass\n```\n\n"
                "Contributions serve collective inquiry. "
                "See https://github.com/example/sab-tools for code."
            ),
        }
        result = gates.evaluate(content, "coordination research")
        assert result["admitted"] is True
        assert result["passed_count"] >= 3

    def test_performative_fails(self, gates):
        content = {
            "body": (
                "wow this is so deep and meaningful I love how we're all coming "
                "together to create something beautiful the energy here is just "
                "incredible and I feel so connected to everyone in this space "
                "let's keep vibing and raising the collective consciousness together namaste"
            ),
        }
        result = gates.evaluate(content, "community building")
        # Performative content should score low on build_artifacts at minimum
        assert result["dimensions"]["build_artifacts"]["passed"] is False

    def test_code_heavy_post(self, gates):
        content = {
            "body": (
                "## Rate Limiter Implementation\n\n"
                "```python\ndef check_rate(key, window=3600, limit=100):\n"
                "    cutoff = time.time() - window\n"
                "    count = db.execute('SELECT COUNT(*) FROM events WHERE key=? AND ts>?', "
                "(key, cutoff)).fetchone()[0]\n    return count < limit\n```\n\n"
                "Benchmark results suggest 50K checks/sec with SQLite."
            ),
        }
        result = gates.evaluate(content)
        assert result["dimensions"]["build_artifacts"]["passed"] is True
        assert result["dimensions"]["build_artifacts"]["score"] >= 0.5

    def test_empty_content(self, gates):
        result = gates.evaluate({"body": ""})
        assert result["admitted"] is False

    def test_keyword_stuffing_fails(self, gates):
        content = {
            "body": (
                "consciousness consciousness consciousness alignment depth coherence "
                "syntropic attractor basin oriented coordination measurement research"
            ),
        }
        result = gates.evaluate(content)
        assert result["dimensions"]["build_artifacts"]["passed"] is False

    def test_three_active_dimensions(self, gates):
        assert gates.DIMENSIONS["structural_rigor"]["active"] is True
        assert gates.DIMENSIONS["build_artifacts"]["active"] is True
        assert gates.DIMENSIONS["telos_alignment"]["active"] is True
        assert gates.DIMENSIONS["predictive_accuracy"]["active"] is False

    def test_evaluate_returns_all_fields(self, gates):
        result = gates.evaluate({"body": "test content"})
        assert "dimensions" in result
        assert "passed_count" in result
        assert "total_active" in result
        assert "admitted" in result
        assert result["total_active"] == 3


class TestEvaluateContent:
    def test_convenience_function(self):
        result = evaluate_content(
            "## Structured Analysis\n\nThis analysis suggests that evidence-based "
            "reasoning with code artifacts produces better results.\n\n"
            "```python\nprint('hello')\n```\n\n"
            "See https://example.com for more.",
            agent_telos="research",
        )
        assert "dimensions" in result
        assert "admitted" in result

    def test_with_attachment(self):
        result = evaluate_content(
            "Here is my dataset analysis.",
            has_attachment=True,
        )
        assert result["dimensions"]["build_artifacts"]["score"] >= 0.5


def test_replayable_adversarial_corpus_expected_outcomes():
    corpus = Path(__file__).parent / "fixtures" / "adversarial_corpus.jsonl"
    rows = [json.loads(line) for line in corpus.read_text().splitlines() if line.strip()]
    assert rows

    for row in rows:
        passed, evidence, _ = verify_content(
            row["content"],
            author_address=row["author_address"],
            context=row.get("context") or {},
        )
        failed_gates = {item.gate_name for item in evidence if item.result == GateResult.FAILED}
        assert passed is row["expected_verified"], row["id"]
        assert row["expected_failed_required_gate"] in failed_gates, row["id"]
