"""Tests for SAB Onboarding / Telos Validation."""
import pytest
from agora.onboarding import TelosValidator
from agora.config import SAB_NETWORK_TELOS


@pytest.fixture
def validator():
    return TelosValidator()


class TestTelosValidator:
    def test_aligned_telos(self, validator):
        # Use enough tokens from the actual network telos to exceed 0.4 Jaccard threshold
        result = validator.validate(
            "oriented agent coordination produces qualitatively different outcomes "
            "depth engagement coherence virality build artifacts contributions serve "
            "collective inquiry creation tools research knowledge persist compound measurement"
        )
        assert result["aligned"] is True
        assert result["score"] >= 0.4
        assert result["method"] == "token_overlap_v1"

    def test_unaligned_telos(self, validator):
        result = validator.validate("cooking recipes and pasta sauce")
        assert result["aligned"] is False
        assert result["score"] < 0.4

    def test_empty_telos(self, validator):
        result = validator.validate("")
        assert result["aligned"] is False
        assert result["score"] == 0.0

    def test_exact_network_telos(self, validator):
        result = validator.validate(SAB_NETWORK_TELOS)
        assert result["aligned"] is True
        assert result["score"] > 0.5

    def test_partial_overlap(self, validator):
        result = validator.validate("agent coordination research")
        assert result["score"] > 0

    def test_stopwords_filtered(self, validator):
        result_stopwords = validator.validate("the a an is are to of in for on")
        assert result_stopwords["score"] == 0.0

    def test_custom_threshold(self):
        strict = TelosValidator(threshold=0.8)
        result = strict.validate("agent coordination")
        # Partial overlap should fail strict threshold
        assert result["score"] < 0.8

    def test_custom_network_telos(self):
        custom = TelosValidator(network_telos="quantum computing research simulation")
        result = custom.validate("quantum computing")
        assert result["score"] > 0
        assert result["aligned"] is True
