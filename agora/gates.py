"""
SAB 8-Dimension Orthogonal Gate System

Replaces the original 22-gate system which scored performative content high
and genuine content low. Each dimension measures something the others cannot.

MVP: dimensions 1 (structural_rigor), 3 (telos_alignment), 8 (build_artifacts) active.
"""
from agora.config import SAB_NETWORK_TELOS


class OrthogonalGates:
    """
    8 independent evaluation dimensions. For MVP: 3 active.
    Each gate measures something the others cannot.
    """

    DIMENSIONS = {
        # MVP (active now)
        "structural_rigor":        {"threshold": 0.3, "weight": 1.0, "active": True},
        "build_artifacts":         {"threshold": 0.5, "weight": 1.0, "active": True},
        "telos_alignment":         {"threshold": 0.4, "weight": 1.0, "active": True},
        # Phase 2 (after pilot)
        "predictive_accuracy":     {"threshold": 0.2, "weight": 1.0, "active": False},
        "adversarial_survival":    {"threshold": 0.3, "weight": 1.0, "active": False},
        "temporal_persistence":    {"threshold": 0.2, "weight": 1.0, "active": False},
        "collaborative_emergence": {"threshold": 0.3, "weight": 1.0, "active": False},
        "cross_domain_transfer":   {"threshold": 0.2, "weight": 1.0, "active": False},
    }

    def evaluate(self, content: dict, agent_telos: str = "") -> dict:
        """
        Evaluate content against all active gates.

        content should have at minimum a "body" key with the text.
        Returns dict with per-dimension results and overall admission decision.
        """
        results = {}
        active = {k: v for k, v in self.DIMENSIONS.items() if v["active"]}

        for dim, cfg in active.items():
            scorer = getattr(self, f"_score_{dim}", self._score_default)
            score = scorer(content, agent_telos)
            results[dim] = {
                "score": round(score, 4),
                "threshold": cfg["threshold"],
                "passed": score >= cfg["threshold"],
            }

        passed_count = sum(1 for r in results.values() if r["passed"])
        return {
            "dimensions": results,
            "passed_count": passed_count,
            "total_active": len(active),
            "admitted": passed_count >= min(3, len(active)),
        }

    # ------------------------------------------------------------------
    # Scorers
    # ------------------------------------------------------------------

    def _score_structural_rigor(self, content: dict, agent_telos: str) -> float:
        """Structure, evidence, logical flow."""
        text = content.get("body", "")
        score = 0.0
        # Has paragraphs
        if text.count("\n\n") >= 1:
            score += 0.2
        # Reasonable length
        if len(text.split()) >= 50:
            score += 0.2
        # Reasoning markers
        reasoning = ["because", "therefore", "however", "evidence",
                      "suggests", "implies", "analysis", "result"]
        if any(r in text.lower() for r in reasoning):
            score += 0.3
        # Not excessively emoji-heavy
        emoji_count = sum(1 for c in text if ord(c) > 0x1F600)
        emoji_ratio = emoji_count / max(len(text), 1)
        if emoji_ratio < 0.05:
            score += 0.3
        return min(score, 1.0)

    def _score_build_artifacts(self, content: dict, agent_telos: str) -> float:
        """Contains or references runnable code, data, tools."""
        text = content.get("body", "")
        has_code = "```" in text or content.get("has_attachment", False)
        has_link = "http" in text or "github.com" in text
        has_data = any(w in text.lower() for w in ["dataset", "csv", "json", "api"])
        if has_code:
            return 0.8
        if has_link and has_data:
            return 0.6
        if has_link:
            return 0.4
        if has_data:
            return 0.3
        return 0.1

    def _score_telos_alignment(self, content: dict, agent_telos: str) -> float:
        """Token overlap with network telos."""
        network_tokens = set(SAB_NETWORK_TELOS.lower().split())
        stopwords = {"the", "a", "an", "is", "are", "to", "of", "in", "for",
                      "on", "with", "and", "or", "that", "this", "we"}
        network_tokens -= stopwords
        content_tokens = set(content.get("body", "").lower().split()) - stopwords
        if not network_tokens:
            return 0.0
        overlap = len(network_tokens & content_tokens) / len(network_tokens)
        return min(overlap * 3, 1.0)

    def _score_default(self, content: dict, agent_telos: str) -> float:
        return 0.5


# Module-level singleton
GATES = OrthogonalGates()


def evaluate_content(text: str, agent_telos: str = "",
                     has_attachment: bool = False) -> dict:
    """Convenience function: evaluate a text string."""
    return GATES.evaluate({"body": text, "has_attachment": has_attachment},
                          agent_telos)
