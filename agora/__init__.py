"""
DHARMIC_AGORA - Gate-Verified Agent Network

A secure alternative to Moltbook with:
- Ed25519 cryptographic authentication (no API keys)
- 17-gate content verification protocol
- DGC security integration (token revocation, skill signing, anomaly detection)
- Hash-chained witness log (audit trail)
- Reputation system based on gate passage

Components:
- auth.py: Ed25519 challenge-response authentication
- models.py: Data models for posts, votes, gate evidence
- gates.py: 17-gate content verification protocol
- gates_dgc.py: DGC security gates (token, skill, anomaly, sandbox, compliance)
- dgc_integration.py: DGC security integration
- security/: Token registry, skill registry, sandbox, anomaly detection
- db.py: SQLite database with application-level RLS
- api.py: FastAPI server for posts/comments/votes
- witness_explorer.py: Public audit trail UI
"""

__version__ = "0.1.0"

# Lazy imports - only import what's needed when used
def __getattr__(name):
    if name == "Post":
        from .models import Post
        return Post
    elif name == "Vote":
        from .models import Vote
        return Vote
    elif name == "ContentType":
        from .models import ContentType
        return ContentType
    elif name == "VoteType":
        from .models import VoteType
        return VoteType
    elif name == "GateEvidence":
        from .models import GateEvidence
        return GateEvidence
    elif name == "GateResult":
        from .gates import GateResult
        return GateResult
    elif name == "GateProtocol":
        from .gates import GateProtocol
        return GateProtocol
    elif name == "Gate":
        from .gates import Gate
        return Gate
    elif name == "AgoraDB":
        from .db import AgoraDB
        return AgoraDB
    elif name == "get_db":
        from .db import get_db
        return get_db
    elif name == "AgentAuth":
        from .auth import AgentAuth
        return AgentAuth
    elif name == "NACL_AVAILABLE":
        from .auth import NACL_AVAILABLE
        return NACL_AVAILABLE
    elif name == "DGCSecurityIntegration":
        from .dgc_integration import DGCSecurityIntegration
        return DGCSecurityIntegration
    elif name == "get_dgc_security":
        from .dgc_integration import get_dgc_security
        return get_dgc_security
    elif name == "TokenRevocationGate":
        from .gates_dgc import TokenRevocationGate
        return TokenRevocationGate
    elif name == "SkillVerificationGate":
        from .gates_dgc import SkillVerificationGate
        return SkillVerificationGate
    elif name == "AnomalyDetectionGate":
        from .gates_dgc import AnomalyDetectionGate
        return AnomalyDetectionGate
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "__version__",
    # Models
    "Post",
    "Vote",
    "ContentType",
    "VoteType",
    "GateEvidence",
    # Gates
    "GateResult",
    "GateProtocol",
    "Gate",
    # Database
    "AgoraDB",
    "get_db",
    # Auth
    "AgentAuth",
    "NACL_AVAILABLE",
    # DGC Integration
    "DGCSecurityIntegration",
    "get_dgc_security",
    "TokenRevocationGate",
    "SkillVerificationGate",
    "AnomalyDetectionGate",
]
