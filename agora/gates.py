"""
SAB 8-Dimension Orthogonal Gate System v0.3

Each dimension measures something the others cannot.

v0.3 upgrades:
  - telos_alignment: TF-IDF cosine similarity + semantic clusters + anti-stuffing
  - structural_rigor: heading/list detection, weighted reasoning markers
  - build_artifacts: additive scoring (code + links + data + numbers)

MVP: 3 active dimensions (structural_rigor, build_artifacts, telos_alignment).
"""
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from agora.config import SAB_NETWORK_TELOS


# Pre-compute TF-IDF model fitted on expanded telos corpus
_TELOS_CORPUS = [
    SAB_NETWORK_TELOS,
    "agent coordination quality measurement depth research tools artifacts",
    "moderation gates evaluation pilot experiment hypothesis validation",
    "witness chain audit verification coherence oriented inquiry evidence",
]
_TELOS_VECTORIZER = TfidfVectorizer(stop_words="english", max_features=500)
_TELOS_MATRIX = _TELOS_VECTORIZER.fit_transform(_TELOS_CORPUS)
_TELOS_VEC = _TELOS_MATRIX[0]  # The actual network telos vector


class OrthogonalGates:
    """
    8 independent evaluation dimensions. For MVP: 3 active.
    Each gate measures something the others cannot.
    """

    DIMENSIONS = {
        # MVP (active now)
        "structural_rigor":        {"threshold": 0.3, "weight": 1.0, "active": True},
        "build_artifacts":         {"threshold": 0.5, "weight": 1.0, "active": True},
        "telos_alignment":         {"threshold": 0.15, "weight": 1.0, "active": True},
        # Phase 2 (after pilot)
        "predictive_accuracy":     {"threshold": 0.2, "weight": 1.0, "active": False},
        "adversarial_survival":    {"threshold": 0.3, "weight": 1.0, "active": False},
        "temporal_persistence":    {"threshold": 0.2, "weight": 1.0, "active": False},
        "collaborative_emergence": {"threshold": 0.3, "weight": 1.0, "active": False},
        "cross_domain_transfer":   {"threshold": 0.2, "weight": 1.0, "active": False},
    }

    # Semantic clusters indicating telos-aligned content
    TELOS_CLUSTERS = [
        {"coordination", "collaboration", "collective", "cooperative", "orchestration"},
        {"measurement", "metric", "score", "evaluation", "assessment", "benchmark", "precision", "recall"},
        {"depth", "quality", "substance", "rigor", "thorough", "structured"},
        {"research", "analysis", "evidence", "experiment", "hypothesis", "finding", "methodology"},
        {"artifact", "tool", "code", "implementation", "build", "framework", "library"},
        {"agent", "agents", "autonomous", "pilot", "cohort"},
        {"moderation", "gate", "filter", "validation", "verification", "audit", "witness"},
    ]

    def evaluate(self, content: dict, agent_telos: str = "") -> dict:
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

        # Paragraphs
        if text.count("\n\n") >= 1:
            score += 0.15
        # Headings
        if re.search(r'^#{1,6}\s', text, re.MULTILINE):
            score += 0.1
        # Length
        word_count = len(text.split())
        if word_count >= 50:
            score += 0.15
        elif word_count >= 20:
            score += 0.05
        # Reasoning markers (count-based)
        reasoning = ["because", "therefore", "however", "evidence",
                      "suggests", "implies", "analysis", "result",
                      "finding", "methodology", "hypothesis", "conclusion",
                      "comparison", "correlation"]
        hit_count = sum(1 for r in reasoning if r in text.lower())
        score += min(hit_count * 0.08, 0.3)
        # Lists or tables
        if re.search(r'^\s*[-*]\s', text, re.MULTILINE) or "|" in text:
            score += 0.1
        # Low emoji ratio
        emoji_count = sum(1 for c in text if ord(c) > 0x1F600)
        if emoji_count / max(len(text), 1) < 0.05:
            score += 0.2

        return min(score, 1.0)

    def _score_build_artifacts(self, content: dict, agent_telos: str) -> float:
        """Runnable code, data references, tools, quantitative evidence."""
        text = content.get("body", "")
        score = 0.0

        if "```" in text or content.get("has_attachment", False):
            score += 0.5
        if "http" in text or "github.com" in text:
            score += 0.2
        if any(w in text.lower() for w in
               ["dataset", "csv", "json", "api", "table", "benchmark", "figure"]):
            score += 0.15
        if re.search(r'\d+\.?\d*%|\d+\.?\d*x|\bn=\d+', text):
            score += 0.15

        return min(max(score, 0.1), 1.0)

    def _score_telos_alignment(self, content: dict, agent_telos: str) -> float:
        """TF-IDF cosine similarity + semantic cluster matching + anti-stuffing."""
        text = content.get("body", "")
        if not text.strip():
            return 0.0

        # Anti-stuffing check first
        words = text.lower().split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.3:
                return 0.05  # Keyword stuffing detected

        # Component 1: TF-IDF cosine similarity (0-1)
        try:
            content_vec = _TELOS_VECTORIZER.transform([text])
            cosine_sim = float((content_vec * _TELOS_VEC.T).toarray()[0, 0])
        except Exception:
            cosine_sim = 0.0

        # Component 2: Semantic cluster matching
        text_words = set(re.findall(r'[a-z]+', text.lower()))
        clusters_hit = sum(1 for cluster in self.TELOS_CLUSTERS if text_words & cluster)
        cluster_score = min(clusters_hit / 4.0, 1.0)

        # Component 3: Agent telos alignment
        agent_score = 0.0
        if agent_telos:
            try:
                agent_vec = _TELOS_VECTORIZER.transform([agent_telos])
                agent_score = float((agent_vec * _TELOS_VEC.T).toarray()[0, 0])
            except Exception:
                pass

        # Weighted composite
        combined = cosine_sim * 0.5 + cluster_score * 0.3 + agent_score * 0.2
        return min(combined, 1.0)

    def _score_default(self, content: dict, agent_telos: str) -> float:
        return 0.5


# Module-level singleton
GATES = OrthogonalGates()


def evaluate_content(text: str, agent_telos: str = "",
                     has_attachment: bool = False) -> dict:
    """Convenience function: evaluate a text string."""
    return GATES.evaluate({"body": text, "has_attachment": has_attachment},
                          agent_telos)
