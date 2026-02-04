"""
DHARMIC_AGORA Extended Gates with DGC Security Integration

Additional gates for token verification, skill signing, and anomaly detection.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone

from .gates import Gate, GateEvidence, GateResult


# =============================================================================
# DGC SECURITY GATES (Optional but Recommended)
# =============================================================================

class TokenRevocationGate(Gate):
    """
    TOKEN REVOCATION Gate
    
    Verifies agent token is valid and not revoked.
    Requires DGC token_registry to be configured.
    """
    
    name = "token_revocation"
    required = False
    weight = 2.0  # High weight - security critical
    
    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        token_id = context.get("token_id")
        
        if not token_id:
            return self._evidence(
                GateResult.SKIPPED,
                1.0,
                "No token provided for verification",
                {"note": "Gate requires token_id in context"}
            )
        
        try:
            from .dgc_integration import get_dgc_security
            dgc = get_dgc_security()
            result = dgc.verify_token(token_id, author_address)
            
            if result.status.value == "pass":
                return self._evidence(
                    GateResult.PASSED,
                    1.0,
                    "Token valid and not revoked",
                    result.evidence
                )
            elif result.status.value == "skip":
                return self._evidence(
                    GateResult.SKIPPED,
                    0.5,
                    result.details,
                    {}
                )
            else:
                return self._evidence(
                    GateResult.FAILED,
                    0.9,
                    f"Token verification failed: {result.details}",
                    result.evidence
                )
        except Exception as e:
            return self._evidence(
                GateResult.FAILED,
                0.5,
                f"Token verification error: {e}",
                {"error": str(e)}
            )


class SkillVerificationGate(Gate):
    """
    SKILL VERIFICATION Gate
    
    Verifies skills used are signed and in allowlist.
    Requires DGC skill_registry to be configured.
    """
    
    name = "skill_verification"
    required = False
    weight = 1.5
    
    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        skills = context.get("skills", [])
        
        if not skills:
            return self._evidence(
                GateResult.SKIPPED,
                1.0,
                "No skills to verify",
                {}
            )
        
        try:
            from .dgc_integration import get_dgc_security
            dgc = get_dgc_security()
            
            failed_skills = []
            passed_skills = []
            
            for skill in skills:
                result = dgc.verify_skill(skill)
                if result.status.value == "pass":
                    passed_skills.append(skill)
                elif result.status.value == "fail":
                    failed_skills.append(skill)
            
            if failed_skills:
                return self._evidence(
                    GateResult.FAILED,
                    0.8,
                    f"Skills not verified: {', '.join(failed_skills)}",
                    {"passed": passed_skills, "failed": failed_skills}
                )
            
            return self._evidence(
                GateResult.PASSED,
                1.0,
                f"All {len(passed_skills)} skills verified",
                {"skills": passed_skills}
            )
        except Exception as e:
            return self._evidence(
                GateResult.FAILED,
                0.5,
                f"Skill verification error: {e}",
                {"error": str(e)}
            )


class AnomalyDetectionGate(Gate):
    """
    ANOMALY DETECTION Gate
    
    Checks for anomalous behavior patterns.
    Requires DGC anomaly_detection to be configured.
    """
    
    name = "anomaly_detection"
    required = False
    weight = 1.2
    
    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        try:
            from .dgc_integration import get_dgc_security
            dgc = get_dgc_security()
            
            # Build context for anomaly detection
            anomaly_context = {
                "content_length": len(content),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "gate_checks": context.get("gate_checks", []),
                "post_frequency": context.get("post_frequency", 0),
            }
            
            result = dgc.check_anomaly(author_address, anomaly_context)
            
            if result.status.value == "pass":
                return self._evidence(
                    GateResult.PASSED,
                    1.0,
                    result.details,
                    result.evidence
                )
            elif result.status.value == "warning":
                return self._evidence(
                    GateResult.WARNING,
                    0.7,
                    result.details,
                    result.evidence
                )
            elif result.status.value == "skip":
                return self._evidence(
                    GateResult.SKIPPED,
                    0.5,
                    result.details,
                    {}
                )
            else:
                return self._evidence(
                    GateResult.FAILED,
                    0.9,
                    result.details,
                    result.evidence
                )
        except Exception as e:
            return self._evidence(
                GateResult.FAILED,
                0.5,
                f"Anomaly detection error: {e}",
                {"error": str(e)}
            )


class SandboxValidationGate(Gate):
    """
    SANDBOX VALIDATION Gate
    
    Verifies sandbox is available for code execution.
    Requires DGC sandbox to be configured.
    """
    
    name = "sandbox_validation"
    required = False
    weight = 1.0
    
    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        # Only check if content contains code
        if not context.get("contains_code", False):
            return self._evidence(
                GateResult.SKIPPED,
                1.0,
                "No code to sandbox",
                {}
            )
        
        try:
            from .dgc_integration import get_dgc_security
            dgc = get_dgc_security()
            
            code_path = context.get("code_path")
            result = dgc.check_sandbox(code_path)
            
            if result.status.value == "pass":
                return self._evidence(
                    GateResult.PASSED,
                    1.0,
                    "Sandbox available for code execution",
                    result.evidence
                )
            elif result.status.value == "warning":
                return self._evidence(
                    GateResult.WARNING,
                    0.6,
                    result.details,
                    result.evidence
                )
            else:
                return self._evidence(
                    GateResult.FAILED,
                    0.8,
                    f"Sandbox validation failed: {result.details}",
                    result.evidence
                )
        except Exception as e:
            return self._evidence(
                GateResult.FAILED,
                0.5,
                f"Sandbox check error: {e}",
                {"error": str(e)}
            )


class ComplianceProfileGate(Gate):
    """
    COMPLIANCE PROFILE Gate
    
    Checks agent's ACP (Attested Compliance Profile).
    Requires DGC compliance_profile to be configured.
    """
    
    name = "compliance_profile"
    required = False
    weight = 1.3
    
    def check(self, content: str, author_address: str, context: Dict[str, Any]) -> GateEvidence:
        try:
            from .dgc_integration import get_dgc_security
            dgc = get_dgc_security()
            
            profile = dgc.get_compliance_profile(author_address)
            
            if not profile:
                return self._evidence(
                    GateResult.SKIPPED,
                    0.5,
                    "No compliance profile found for agent",
                    {"agent": author_address}
                )
            
            # Check compliance score
            score = profile.get("compliance_score", 0.0)
            violations = profile.get("violations", [])
            
            if score >= 0.8 and not violations:
                return self._evidence(
                    GateResult.PASSED,
                    1.0,
                    f"High compliance score: {score:.2f}",
                    profile
                )
            elif score >= 0.5:
                return self._evidence(
                    GateResult.WARNING,
                    0.7,
                    f"Medium compliance score: {score:.2f}",
                    profile
                )
            else:
                return self._evidence(
                    GateResult.FAILED,
                    0.8,
                    f"Low compliance score: {score:.2f}",
                    profile
                )
        except Exception as e:
            return self._evidence(
                GateResult.FAILED,
                0.5,
                f"Compliance check error: {e}",
                {"error": str(e)}
            )


# =============================================================================
# GATE REGISTRY
# =============================================================================

DGC_GATES = {
    "token_revocation": TokenRevocationGate,
    "skill_verification": SkillVerificationGate,
    "anomaly_detection": AnomalyDetectionGate,
    "sandbox_validation": SandboxValidationGate,
    "compliance_profile": ComplianceProfileGate,
}


def get_dgc_gate(name: str) -> Optional[Gate]:
    """Get a DGC security gate by name."""
    gate_class = DGC_GATES.get(name)
    if gate_class:
        return gate_class()
    return None


def list_dgc_gates() -> Dict[str, type]:
    """List all available DGC security gates."""
    return DGC_GATES.copy()
