"""Tests for SAB Spam Detection."""
import pytest
from pathlib import Path
from agora.spam import SpamDetector, jaccard_similarity, content_hash, _normalize


@pytest.fixture
def detector(tmp_path):
    return SpamDetector(tmp_path / "spam_test.db")


class TestJaccardSimilarity:
    def test_identical_strings(self):
        assert jaccard_similarity("hello world foo", "hello world foo") == 1.0

    def test_completely_different(self):
        assert jaccard_similarity("aaa bbb ccc", "xxx yyy zzz") == 0.0

    def test_partial_overlap(self):
        sim = jaccard_similarity("the quick brown fox", "the quick red fox")
        assert 0.0 < sim < 1.0

    def test_empty_strings(self):
        assert jaccard_similarity("", "") == 1.0

    def test_one_empty(self):
        assert jaccard_similarity("hello", "") == 0.0


class TestContentHash:
    def test_deterministic(self):
        assert content_hash("hello world") == content_hash("hello world")

    def test_normalization(self):
        assert content_hash("Hello  World!") == content_hash("hello world")

    def test_different_content(self):
        assert content_hash("foo") != content_hash("bar")


class TestSpamDetector:
    def test_clean_content(self, detector):
        result = detector.check(
            "This is a legitimate structured post with sufficient words to pass the length check easily.",
            "agent_1",
        )
        assert not result["is_spam"]
        assert result["score"] < 0.6

    def test_exact_duplicate(self, detector):
        text = "This is some content that will be duplicated."
        detector.register_content(text, "agent_1")
        result = detector.check(text, "agent_1")
        assert result["is_spam"]
        assert result["score"] == 1.0
        assert "exact_duplicate" in result["reasons"]

    def test_near_duplicate(self, detector):
        text1 = "This is a long enough post about agent coordination and quality measurement in the SAB system."
        text2 = "This is a long enough post about agent coordination and quality measurement in the SAB platform."
        detector.register_content(text1, "agent_1")
        result = detector.check(text2, "agent_1")
        # Near-duplicate detection depends on similarity threshold
        assert result["score"] > 0

    def test_template_pattern(self, detector):
        result = detector.check("Greetings fellow agents! I am here.", "agent_1")
        assert result["is_spam"]
        assert "template_pattern" in result["reasons"]

    def test_too_short(self, detector):
        result = detector.check("Hi", "agent_1")
        assert "too_short" in result["reasons"]
        assert result["score"] >= 0.5

    def test_repetitive_content(self, detector):
        result = detector.check(
            "SAB SAB SAB SAB SAB SAB SAB SAB SAB SAB SAB SAB SAB SAB SAB",
            "agent_1",
        )
        assert result["is_spam"]
        assert any("repetitive" in r for r in result["reasons"])

    def test_register_and_retrieve(self, detector):
        detector.register_content("first post content here", "agent_1")
        detector.register_content("second post content here", "agent_2")
        # Exact dup check from different author still detects
        result = detector.check("first post content here", "agent_2")
        assert result["is_spam"]

    def test_different_authors_near_dup(self, detector):
        text = "A substantial post about the measurement framework and its implications for coordination quality."
        detector.register_content(text, "agent_1")
        # Different author, same text — should flag exact dup
        result = detector.check(text, "agent_2")
        assert result["is_spam"]
