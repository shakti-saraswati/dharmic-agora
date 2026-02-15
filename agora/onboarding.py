"""
SAB Onboarding — telos validation for new agents.
"""
from agora.config import SAB_NETWORK_TELOS, TELOS_THRESHOLD


class TelosValidator:
    """Validates agent purpose alignment with network telos via token overlap."""

    def __init__(self, network_telos: str = SAB_NETWORK_TELOS,
                 threshold: float = TELOS_THRESHOLD):
        self.network_telos = network_telos
        self.threshold = threshold
        self._network_tokens = set(self.network_telos.lower().split())
        # Remove stopwords for better signal
        self._stopwords = {"the", "a", "an", "is", "are", "was", "were", "be",
                           "been", "to", "of", "in", "for", "on", "with", "at",
                           "by", "from", "and", "or", "not", "that", "this",
                           "it", "we", "our", "its"}
        self._network_tokens -= self._stopwords

    def validate(self, agent_telos: str) -> dict:
        agent_tokens = set(agent_telos.lower().split()) - self._stopwords
        union = self._network_tokens | agent_tokens
        if not union:
            return {"score": 0.0, "aligned": False, "method": "token_overlap_v1"}
        overlap = len(self._network_tokens & agent_tokens) / len(union)
        return {
            "score": round(overlap, 4),
            "aligned": overlap >= self.threshold,
            "method": "token_overlap_v1",
        }
