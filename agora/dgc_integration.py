"""
DGC Security Integration for DHARMIC_AGORA

Wires DGC security components into the agora gate system:
- Token revocation/rotation checks
- Skill registry verification
- Sandbox execution validation
- Anomaly detection
- ACP (Attested Compliance Profile)
"""

import os
import sys
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

# Add security module to path
sys.path.insert(0, os.path.dirname(__file__))


class SecurityStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIP = "skip"


@dataclass
class SecurityCheck:
    """Result of a security verification."""
    component: str
    status: SecurityStatus
    details: str
    evidence: Optional[Dict[str, Any]] = None


class DGCSecurityIntegration:
    """
    Integrates DGC security components with agora 17-gate system.
    
    Usage:
        security = DGCSecurityIntegration()
        results = security.verify_agent(agent_id, token, context)
    """
    
    def __init__(self, policy_dir: Optional[str] = None):
        self.policy_dir = policy_dir or os.path.join(
            os.path.dirname(__file__), '..', 'policy'
        )
        self._load_components()
    
    def _load_components(self):
        """Lazy-load security components."""
        self._token_registry = None
        self._skill_registry = None
        self._sandbox = None
        self._anomaly_detector = None
        self._compliance = None
    
    @property
    def token_registry(self):
        """Token revocation and rotation."""
        if self._token_registry is None:
            try:
                from security.token_registry import TokenRegistry
                self._token_registry = TokenRegistry()
            except ImportError:
                pass
        return self._token_registry
    
    @property
    def skill_registry(self):
        """Skill signing and allowlist."""
        if self._skill_registry is None:
            try:
                from security.skill_registry import SkillRegistry
                self._skill_registry = SkillRegistry()
            except ImportError:
                pass
        return self._skill_registry
    
    @property
    def sandbox(self):
        """Sandbox execution harness."""
        if self._sandbox is None:
            try:
                from security.sandbox import SandboxHarness
                self._sandbox = SandboxHarness()
            except ImportError:
                pass
        return self._sandbox
    
    @property
    def anomaly_detector(self):
        """Anomaly detection."""
        if self._anomaly_detector is None:
            try:
                from security.anomaly_detection import AnomalyDetector
                self._anomaly_detector = AnomalyDetector()
            except ImportError:
                pass
        return self._anomaly_detector
    
    @property
    def compliance(self):
        """ACP (Attested Compliance Profile)."""
        if self._compliance is None:
            try:
                from security.compliance_profile import ComplianceProfile
                self._compliance = ComplianceProfile()
            except ImportError:
                pass
        return self._compliance
    
    def verify_token(self, token_id: str, agent_id: str) -> SecurityCheck:
        """Verify token is valid and not revoked."""
        if not self.token_registry:
            return SecurityCheck(
                component="token_registry",
                status=SecurityStatus.SKIP,
                details="Token registry not available"
            )
        
        try:
            result = self.token_registry.verify_token(token_id, agent_id)
            if result.get("valid"):
                return SecurityCheck(
                    component="token_registry",
                    status=SecurityStatus.PASS,
                    details="Token valid and not revoked",
                    evidence=result
                )
            else:
                return SecurityCheck(
                    component="token_registry",
                    status=SecurityStatus.FAIL,
                    details=f"Token invalid: {result.get('reason', 'unknown')}",
                    evidence=result
                )
        except Exception as e:
            return SecurityCheck(
                component="token_registry",
                status=SecurityStatus.FAIL,
                details=f"Token verification error: {e}"
            )
    
    def verify_skill(self, skill_name: str, signature: Optional[str] = None) -> SecurityCheck:
        """Verify skill is signed and in allowlist."""
        if not self.skill_registry:
            return SecurityCheck(
                component="skill_registry",
                status=SecurityStatus.SKIP,
                details="Skill registry not available"
            )
        
        try:
            result = self.skill_registry.verify_skill(skill_name, signature)
            if result.get("verified"):
                return SecurityCheck(
                    component="skill_registry",
                    status=SecurityStatus.PASS,
                    details="Skill verified and in allowlist",
                    evidence=result
                )
            else:
                return SecurityCheck(
                    component="skill_registry",
                    status=SecurityStatus.FAIL,
                    details=f"Skill verification failed: {result.get('reason', 'unknown')}",
                    evidence=result
                )
        except Exception as e:
            return SecurityCheck(
                component="skill_registry",
                status=SecurityStatus.FAIL,
                details=f"Skill verification error: {e}"
            )
    
    def check_sandbox(self, code_path: str, image: Optional[str] = None) -> SecurityCheck:
        """Verify code can run in sandbox."""
        if not self.sandbox:
            return SecurityCheck(
                component="sandbox",
                status=SecurityStatus.SKIP,
                details="Sandbox not available"
            )
        
        try:
            # Check if sandbox is available
            if not self.sandbox.is_available():
                return SecurityCheck(
                    component="sandbox",
                    status=SecurityStatus.WARNING,
                    details="Docker sandbox not available, using default-deny"
                )
            
            return SecurityCheck(
                component="sandbox",
                status=SecurityStatus.PASS,
                details="Sandbox available for execution"
            )
        except Exception as e:
            return SecurityCheck(
                component="sandbox",
                status=SecurityStatus.FAIL,
                details=f"Sandbox check error: {e}"
            )
    
    def check_anomaly(self, agent_id: str, context: Dict[str, Any]) -> SecurityCheck:
        """Check for anomalous behavior patterns."""
        if not self.anomaly_detector:
            return SecurityCheck(
                component="anomaly_detection",
                status=SecurityStatus.SKIP,
                details="Anomaly detector not available"
            )
        
        try:
            result = self.anomaly_detector.check_agent(agent_id, context)
            risk_score = result.get("risk_score", 0.0)
            
            if risk_score < 0.3:
                return SecurityCheck(
                    component="anomaly_detection",
                    status=SecurityStatus.PASS,
                    details=f"Low risk score: {risk_score:.2f}",
                    evidence=result
                )
            elif risk_score < 0.7:
                return SecurityCheck(
                    component="anomaly_detection",
                    status=SecurityStatus.WARNING,
                    details=f"Medium risk score: {risk_score:.2f}",
                    evidence=result
                )
            else:
                return SecurityCheck(
                    component="anomaly_detection",
                    status=SecurityStatus.FAIL,
                    details=f"High risk score: {risk_score:.2f}",
                    evidence=result
                )
        except Exception as e:
            return SecurityCheck(
                component="anomaly_detection",
                status=SecurityStatus.FAIL,
                details=f"Anomaly check error: {e}"
            )
    
    def get_compliance_profile(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get ACP (Attested Compliance Profile) for agent."""
        if not self.compliance:
            return None
        
        try:
            return self.compliance.get_profile(agent_id)
        except Exception:
            return None
    
    def verify_agent(
        self,
        agent_id: str,
        token_id: Optional[str] = None,
        skills: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[SecurityCheck]:
        """
        Full security verification for an agent.
        
        Returns list of checks for all enabled security components.
        """
        results = []
        context = context or {}
        
        # 1. Token verification
        if token_id:
            results.append(self.verify_token(token_id, agent_id))
        
        # 2. Skill verification
        if skills:
            for skill in skills:
                results.append(self.verify_skill(skill))
        
        # 3. Anomaly detection
        results.append(self.check_anomaly(agent_id, context))
        
        return results
    
    def generate_safety_report(self, output_path: Optional[str] = None) -> str:
        """Generate safety case report."""
        try:
            from security.safety_case_report import SafetyCaseReport
            report = SafetyCaseReport()
            return report.generate(output_path)
        except ImportError:
            return "Safety case report generator not available"


# Singleton instance
_dgc_security: Optional[DGCSecurityIntegration] = None


def get_dgc_security() -> DGCSecurityIntegration:
    """Get singleton DGC security integration."""
    global _dgc_security
    if _dgc_security is None:
        _dgc_security = DGCSecurityIntegration()
    return _dgc_security
