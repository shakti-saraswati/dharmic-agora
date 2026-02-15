"""Tests for SAB Depth Scoring."""
import pytest
from agora.depth import (
    calculate_depth_score,
    score_structural_complexity,
    score_evidence_density,
    score_originality,
    score_collaborative_references,
)


class TestStructuralComplexity:
    def test_structured_post(self):
        text = (
            "## Heading One\n\n"
            "First paragraph with content.\n\n"
            "## Heading Two\n\n"
            "Second paragraph.\n\n"
            "- Item one\n"
            "- Item two\n"
            "- Item three\n\n"
            "## Heading Three\n\n"
            "Conclusion paragraph."
        )
        score = score_structural_complexity(text)
        assert score > 0.5

    def test_flat_text(self):
        score = score_structural_complexity("just a single line of text")
        assert score < 0.3

    def test_empty(self):
        score = score_structural_complexity("")
        assert score == 0.0


class TestEvidenceDensity:
    def test_rich_evidence(self):
        text = (
            "According to [1] and [2], the results are clear.\n"
            "See https://example.com and https://github.com/test.\n"
            "```python\nprint('hello')\n```\n"
            "The dataset shows interesting patterns."
        )
        score = score_evidence_density(text)
        assert score > 0.5

    def test_no_evidence(self):
        score = score_evidence_density("This is a casual opinion with no backing.")
        assert score < 0.2

    def test_code_blocks_count(self):
        text = "Here is code:\n```python\nx = 1\n```\nAnd more:\n```js\ny = 2\n```"
        score = score_evidence_density(text)
        assert score > 0.2


class TestOriginality:
    def test_diverse_vocabulary(self):
        text = (
            "The quantum chromodynamic lattice simulations reveal unexpected "
            "correlations between topological charge fluctuations and chiral "
            "symmetry restoration temperature across multiple spatial volumes "
            "suggesting fundamental universality in deconfinement mechanisms."
        )
        score = score_originality(text)
        assert score > 0.5

    def test_repetitive_text(self):
        score = score_originality("the the the the the the the the the the")
        assert score < 0.3

    def test_very_short(self):
        score = score_originality("hi")
        assert score == 0.0


class TestCollaborativeReferences:
    def test_mentions_and_refs(self):
        text = (
            "Building on @researcher_alpha's work, and in response to "
            "the earlier analysis, extending this framework further.\n"
            "> Previous quote here"
        )
        score = score_collaborative_references(text)
        assert score > 0.5

    def test_no_references(self):
        score = score_collaborative_references("A standalone thought with no references.")
        assert score == 0.0

    def test_just_mentions(self):
        score = score_collaborative_references("Hey @alice and @bob, thoughts?")
        assert score > 0.0


class TestCalculateDepthScore:
    def test_high_quality_post(self):
        text = (
            "## Analysis of Transformer Attention Patterns\n\n"
            "Our research suggests that attention heads in layers 24-27 "
            "exhibit convergent behavior. The evidence from activation "
            "patching experiments (n=45) implies a causal mechanism.\n\n"
            "Key findings:\n"
            "- Participation ratio contracts by 3.3-24.3%\n"
            "- Effect is strongest in MoE models\n"
            "- Layer 27 patching transfers the contraction\n\n"
            "Building on @researcher_alpha's work, this extends the R_V framework.\n"
            "```python\ndef compute(): pass\n```\n"
            "See https://github.com/example/rv-metric for code."
        )
        result = calculate_depth_score(text)
        assert result["composite"] > 0.3
        assert "dimensions" in result
        assert "weights" in result
        assert len(result["dimensions"]) == 4

    def test_low_quality_post(self):
        text = "wow so cool nice vibes everyone"
        result = calculate_depth_score(text)
        assert result["composite"] < 0.3

    def test_custom_weights(self):
        text = "## Heading\n\nSome content here with structure."
        w = {
            "structural_complexity": 1.0,
            "evidence_density": 0.0,
            "originality": 0.0,
            "collaborative_references": 0.0,
        }
        result = calculate_depth_score(text, weights=w)
        # All weight on structural_complexity
        assert result["composite"] == result["dimensions"]["structural_complexity"]

    def test_returns_all_dimensions(self):
        result = calculate_depth_score("any text here sufficient for scoring purposes")
        expected_dims = [
            "structural_complexity",
            "evidence_density",
            "originality",
            "collaborative_references",
        ]
        for dim in expected_dims:
            assert dim in result["dimensions"]
            assert 0.0 <= result["dimensions"][dim] <= 1.0
