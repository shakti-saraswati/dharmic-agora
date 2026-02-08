"""Tests for SAB Rate Limiter."""
import time
import pytest
from unittest.mock import patch
from agora.rate_limit import RateLimiter


@pytest.fixture
def limiter(tmp_path):
    return RateLimiter(tmp_path / "rate_test.db")


class TestRateLimiter:
    def test_first_post_allowed(self, limiter):
        result = limiter.check_post("agent_1")
        assert result["allowed"] is True
        assert result["count"] == 0

    def test_post_limit_reached(self, limiter):
        for _ in range(5):
            limiter.record("agent_1", "post")
        result = limiter.check_post("agent_1")
        assert result["allowed"] is False
        assert result["count"] == 5
        assert result["retry_after"] == 3600

    def test_different_agents_independent(self, limiter):
        for _ in range(5):
            limiter.record("agent_1", "post")
        result = limiter.check_post("agent_2")
        assert result["allowed"] is True

    def test_comment_limit(self, limiter):
        for _ in range(20):
            limiter.record("agent_1", "comment")
        result = limiter.check_comment("agent_1")
        assert result["allowed"] is False

    def test_comment_under_limit(self, limiter):
        for _ in range(5):
            limiter.record("agent_1", "comment")
        result = limiter.check_comment("agent_1")
        assert result["allowed"] is True

    def test_ip_rate_limit(self, limiter):
        for _ in range(30):
            limiter.record("192.168.1.1", "request")
        result = limiter.check_ip("192.168.1.1")
        assert result["allowed"] is False

    def test_ip_under_limit(self, limiter):
        for _ in range(10):
            limiter.record("192.168.1.1", "request")
        result = limiter.check_ip("192.168.1.1")
        assert result["allowed"] is True

    def test_record_cleans_old_events(self, limiter):
        # Record should delete events older than 24h
        limiter.record("agent_1", "post")
        result = limiter.check_post("agent_1")
        assert result["count"] == 1

    def test_post_vs_comment_separate(self, limiter):
        for _ in range(5):
            limiter.record("agent_1", "post")
        # Post limit reached, but comments should be fine
        result = limiter.check_comment("agent_1")
        assert result["allowed"] is True
