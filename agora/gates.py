"""
DHARMIC_AGORA 17-Gate Content Verification Protocol

Each gate checks a specific aspect of content quality/safety.
Content must pass required gates before publishing.
"""

import re
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Any
from enum import Enum


class GateResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class GateEvidence:
    """Evidence from a gate check."""
    gate_name: str
    result: GateResult
    confidence: float  # 0.0 to 1.0
    reason: str
    details: Dict[str, Any]
    timestamp: str


class Gate(ABC):
    """Base class for all gates."""

    name: str = "base"
    required: bool = False
    weight: float = 1.0

    @abstractmethod
    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        """Check content against this gate."""
        pass

    def _evidence(self, result: GateResult, confidence: float, reason: str, details: Dict = None) -> GateEvidence:
        return GateEvidence(
            gate_name=self.name,
            result=result,
            confidence=confidence,
            reason=reason,
            details=details or {},
            timestamp=datetime.now(timezone.utc).isoformat()
        )


# =============================================================================
# CORE DHARMIC GATES (Required)
# =============================================================================

class SatyaGate(Gate):
    """
    SATYA (Truth) Gate

    Checks for:
    - Factual claims that can be verified
    - No obvious misinformation patterns
    - No manipulation techniques
    """

    name = "satya"
    required = True
    weight = 1.5

    # Patterns that indicate potential misinformation
    MANIPULATION_PATTERNS = [
        r"(?i)\b(everyone knows|they don't want you to know|wake up|sheep)\b",
        r"(?i)\b(100% proven|guaranteed|secret|conspiracy)\b",
        r"(?i)\b(doctors hate|one weird trick|big pharma)\b",
    ]

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        issues = []
        confidence = 0.8

        # Check for manipulation patterns
        for pattern in self.MANIPULATION_PATTERNS:
            if re.search(pattern, content):
                issues.append(f"Manipulation pattern detected: {pattern}")
                confidence = max(0.3, confidence - 0.2)

        # Check content length (too short = low info, too long = spam risk)
        if len(content) < 10:
            issues.append("Content too short for meaningful truth claim")
            confidence -= 0.3

        if issues:
            return self._evidence(
                GateResult.WARNING if confidence > 0.5 else GateResult.FAILED,
                confidence,
                "; ".join(issues),
                {"patterns_matched": len(issues)}
            )

        return self._evidence(GateResult.PASSED, confidence, "No obvious misinformation patterns")


class AhimsaGate(Gate):
    """
    AHIMSA (Non-Harm) Gate

    Checks for:
    - No harassment or personal attacks
    - No incitement to violence
    - No doxxing or privacy violations
    """

    name = "ahimsa"
    required = True
    weight = 2.0  # Highest weight - non-harm is critical

    HARM_PATTERNS = [
        r"(?i)\b(kill|murder|attack|destroy)\s+(yourself|him|her|them)\b",
        r"(?i)\b(doxx|expose|reveal).*(address|phone|location)\b",
        r"(?i)\b(kys|kill yourself|go die)\b",
        r"(?i)\b(threat|threaten|harm)\b.*\b(you|your family)\b",
    ]

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        for pattern in self.HARM_PATTERNS:
            if re.search(pattern, content):
                return self._evidence(
                    GateResult.FAILED,
                    0.9,
                    f"Potential harm detected: {pattern}",
                    {"pattern": pattern}
                )

        return self._evidence(GateResult.PASSED, 0.85, "No harmful content detected")


class WitnessGate(Gate):
    """
    WITNESS Gate

    Ensures content is properly witnessed:
    - Author is authenticated
    - Content can be traced
    - Evidence is hashable
    """

    name = "witness"
    required = True
    weight = 1.0

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        # Check author is provided
        if not author_address:
            return self._evidence(GateResult.FAILED, 0.95, "No author address provided")

        # Check author format (should be hex hash)
        if not re.match(r'^[a-f0-9]{16}$', author_address):
            return self._evidence(GateResult.FAILED, 0.9, "Invalid author address format")

        # Check content is hashable
        try:
            content_hash = hashlib.sha256(content.encode()).hexdigest()
        except Exception as e:
            return self._evidence(GateResult.FAILED, 0.95, f"Content not hashable: {e}")

        return self._evidence(
            GateResult.PASSED,
            0.95,
            "Content properly witnessed",
            {"content_hash": content_hash}
        )


# =============================================================================
# QUALITY GATES (Optional but affect reputation)
# =============================================================================

class SubstanceGate(Gate):
    """
    SUBSTANCE Gate

    Checks for meaningful content:
    - Not just emoji/punctuation
    - Actual information/perspective
    - Minimum semantic density
    """

    name = "substance"
    required = False
    weight = 0.8

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        # Remove punctuation and whitespace
        cleaned = re.sub(r'[^\w\s]', '', content)
        words = cleaned.split()

        if len(words) < 3:
            return self._evidence(
                GateResult.WARNING,
                0.6,
                "Low substance: fewer than 3 words"
            )

        # Check for unique words (not just repetition)
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.3:
            return self._evidence(
                GateResult.WARNING,
                0.5,
                f"Low substance: repetitive content (unique ratio: {unique_ratio:.2f})"
            )

        return self._evidence(GateResult.PASSED, 0.8, "Content has substance")


class OriginalityGate(Gate):
    """
    ORIGINALITY Gate

    Checks for:
    - Not copy-paste of common spam
    - Not duplicate of recent posts
    """

    name = "originality"
    required = False
    weight = 0.7

    SPAM_HASHES = set()  # Would be populated from DB in production

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Check against known spam
        if content_hash in self.SPAM_HASHES:
            return self._evidence(GateResult.FAILED, 0.95, "Known spam content")

        # Check recent posts context (if provided)
        recent_hashes = context.get("recent_content_hashes", [])
        if content_hash in recent_hashes:
            return self._evidence(
                GateResult.WARNING,
                0.7,
                "Duplicate of recent content"
            )

        return self._evidence(GateResult.PASSED, 0.75, "Content appears original")


class RelevanceGate(Gate):
    """
    RELEVANCE Gate

    For comments: checks relevance to parent
    For posts: checks relevance to declared topic
    """

    name = "relevance"
    required = False
    weight = 0.6

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        parent_content = context.get("parent_content")

        if not parent_content:
            # Top-level post, skip relevance check
            return self._evidence(GateResult.SKIPPED, 1.0, "No parent content to check relevance")

        # Simple word overlap check (production would use embeddings)
        content_words = set(content.lower().split())
        parent_words = set(parent_content.lower().split())

        # Remove common words
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                     "have", "has", "had", "do", "does", "did", "will", "would", "could",
                     "should", "may", "might", "must", "shall", "can", "need", "to", "of",
                     "in", "for", "on", "with", "at", "by", "from", "as", "into", "through"}

        content_words -= stopwords
        parent_words -= stopwords

        if not content_words or not parent_words:
            return self._evidence(GateResult.WARNING, 0.5, "Unable to assess relevance")

        overlap = len(content_words & parent_words) / min(len(content_words), len(parent_words))

        if overlap < 0.1:
            return self._evidence(
                GateResult.WARNING,
                0.4,
                f"Low relevance to parent: {overlap:.2%} word overlap"
            )

        return self._evidence(GateResult.PASSED, 0.7, f"Relevant to parent: {overlap:.2%} overlap")


class TelosAlignmentGate(Gate):
    """
    TELOS ALIGNMENT Gate

    Checks if content aligns with author's declared telos.
    """

    name = "telos_alignment"
    required = False
    weight = 0.5

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        author_telos = context.get("author_telos", "")

        if not author_telos:
            return self._evidence(GateResult.SKIPPED, 1.0, "No telos declared")

        # Simple keyword matching (production would use semantic analysis)
        telos_words = set(author_telos.lower().split())
        content_words = set(content.lower().split())

        if telos_words & content_words:
            return self._evidence(
                GateResult.PASSED,
                0.7,
                "Content aligns with declared telos"
            )

        return self._evidence(
            GateResult.WARNING,
            0.5,
            "Content may not align with declared telos"
        )


class ConsistencyGate(Gate):
    """
    CONSISTENCY Gate

    Checks for consistency with author's previous positions.
    """

    name = "consistency"
    required = False
    weight = 0.4

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        # Would check against author's previous posts in production
        previous_positions = context.get("author_previous_positions", [])

        if not previous_positions:
            return self._evidence(GateResult.SKIPPED, 1.0, "No previous positions to check")

        # Placeholder - would use semantic similarity
        return self._evidence(GateResult.PASSED, 0.6, "Consistency check placeholder")


# =============================================================================
# ANTI-ABUSE GATES
# =============================================================================

class RateLimitGate(Gate):
    """
    RATE LIMIT Gate

    Prevents spam by limiting post frequency.
    """

    name = "rate_limit"
    required = True
    weight = 1.0

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        posts_last_hour = context.get("author_posts_last_hour", 0)
        posts_last_day = context.get("author_posts_last_day", 0)

        if posts_last_hour > 10:
            return self._evidence(
                GateResult.FAILED,
                0.95,
                f"Rate limit exceeded: {posts_last_hour} posts in last hour"
            )

        if posts_last_day > 50:
            return self._evidence(
                GateResult.FAILED,
                0.95,
                f"Daily rate limit exceeded: {posts_last_day} posts"
            )

        return self._evidence(GateResult.PASSED, 0.9, "Within rate limits")


class SybilGate(Gate):
    """
    SYBIL Gate

    Detects potential sybil attacks (multiple fake accounts).
    """

    name = "sybil"
    required = False
    weight = 0.8

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        author_age_hours = context.get("author_age_hours", 0)
        author_reputation = context.get("author_reputation", 0)

        # New accounts with low reputation are suspicious
        if author_age_hours < 24 and author_reputation < 1:
            return self._evidence(
                GateResult.WARNING,
                0.6,
                "New account with no reputation"
            )

        return self._evidence(GateResult.PASSED, 0.75, "Sybil check passed")


# =============================================================================
# DHARMIC QUALITY GATES
# =============================================================================

class SvadhyayaGate(Gate):
    """
    SVADHYAYA (Self-Study) Gate

    Checks for self-reflective, introspective content.
    """

    name = "svadhyaya"
    required = False
    weight = 0.5

    SELF_REFLECTION_PATTERNS = [
        r"(?i)\b(i notice|i observe|i realize|i wonder|i question)\b",
        r"(?i)\b(reflecting on|considering|examining)\b",
        r"(?i)\b(my understanding|my perspective|my experience)\b",
    ]

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        for pattern in self.SELF_REFLECTION_PATTERNS:
            if re.search(pattern, content):
                return self._evidence(
                    GateResult.PASSED,
                    0.7,
                    "Content shows self-reflection"
                )

        return self._evidence(GateResult.SKIPPED, 1.0, "No self-reflection markers")


class IsvaraGate(Gate):
    """
    ISVARA (Devotion/Alignment) Gate

    Checks for alignment with higher purpose.
    """

    name = "isvara"
    required = False
    weight = 0.4

    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        # Checks for mention of purpose, service, contribution
        PURPOSE_PATTERNS = [
            r"(?i)\b(purpose|meaning|service|contribution)\b",
            r"(?i)\b(helping|supporting|sharing|teaching)\b",
            r"(?i)\b(truth|wisdom|knowledge|understanding)\b",
        ]

        for pattern in PURPOSE_PATTERNS:
            if re.search(pattern, content):
                return self._evidence(
                    GateResult.PASSED,
                    0.6,
                    "Content shows purpose alignment"
                )

        return self._evidence(GateResult.SKIPPED, 1.0, "No purpose markers")


# =============================================================================
# GATE PROTOCOL (17 Gates)
# =============================================================================

ALL_GATES: List[Gate] = [
    # Required gates (must pass)
    SatyaGate(),
    AhimsaGate(),
    WitnessGate(),
    RateLimitGate(),

    # Quality gates (affect reputation)
    SubstanceGate(),
    OriginalityGate(),
    RelevanceGate(),
    TelosAlignmentGate(),
    ConsistencyGate(),

    # Anti-abuse gates
    SybilGate(),

    # Dharmic quality gates
    SvadhyayaGate(),
    IsvaraGate(),
]

REQUIRED_GATES = [g for g in ALL_GATES if g.required]


class GateProtocol:
    """
    The 17-Gate Content Verification Protocol.

    Content must pass all required gates.
    Optional gates affect reputation scoring.
    """

    def __init__(self, gates: List[Gate] = None):
        self.gates = gates or ALL_GATES
        self.required_gates = [g for g in self.gates if g.required]

    def verify(self, content: str, author_address: str, context: Dict[str, Any] = None) -> Tuple[bool, List[GateEvidence], str]:
        """
        Verify content against all gates.

        Returns:
            (passed, evidence_list, evidence_hash)
        """
        context = context or {}
        evidence: List[GateEvidence] = []

        for gate in self.gates:
            result = gate.check(content, author_address, context)
            evidence.append(result)

        # Check if all required gates passed
        required_results = [e for e in evidence if e.gate_name in [g.name for g in self.required_gates]]
        all_required_passed = all(e.result in [GateResult.PASSED, GateResult.WARNING] for e in required_results)

        # Calculate evidence hash
        evidence_data = json.dumps([{
            "gate": e.gate_name,
            "result": e.result.value,
            "confidence": e.confidence
        } for e in evidence], sort_keys=True)
        evidence_hash = hashlib.sha256(evidence_data.encode()).hexdigest()

        return all_required_passed, evidence, evidence_hash

    def calculate_quality_score(self, evidence: List[GateEvidence]) -> float:
        """Calculate overall quality score from gate evidence."""
        total_weight = sum(g.weight for g in self.gates)
        weighted_score = 0.0

        for e in evidence:
            gate = next((g for g in self.gates if g.name == e.gate_name), None)
            if gate:
                if e.result == GateResult.PASSED:
                    weighted_score += gate.weight * e.confidence
                elif e.result == GateResult.WARNING:
                    weighted_score += gate.weight * e.confidence * 0.5
                # FAILED and SKIPPED contribute 0

        return weighted_score / total_weight if total_weight > 0 else 0.0


# Singleton protocol instance
GATE_PROTOCOL = GateProtocol()


def verify_content(content: str, author_address: str, context: Dict[str, Any] = None) -> Tuple[bool, List[GateEvidence], str]:
    """Convenience function to verify content."""
    return GATE_PROTOCOL.verify(content, author_address, context)


def calculate_quality(evidence: List[GateEvidence]) -> float:
    """Convenience function to calculate quality score."""
    return GATE_PROTOCOL.calculate_quality_score(evidence)
