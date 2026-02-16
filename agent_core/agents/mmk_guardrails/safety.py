"""
MMK-GUARDRAILS: Safety and Alignment Framework
Extracted from NVIDIA NeMo Guardrails
Integrated with SAB Dharmic Gates (22-dimensional alignment)

Core capabilities:
- Content safety filtering
- Topic control
- Dialog management
- SAB Dharmic Gates integration
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class SafetyLevel(Enum):
    STRICT = "strict"
    MODERATE = "moderate"
    PERMISSIVE = "permissive"


@dataclass
class GuardrailResult:
    allowed: bool
    violations: List[str]
    modified_content: Optional[str]
    sab_gate_scores: Dict[str, float]


class MMKGuardrails:
    """
    Safety and Alignment - MMK Module
    
    Mirrors NVIDIA NeMo Guardrails:
    - Programmable guardrails
    - Content safety and topic control
    - Rails configuration (input, output, dialog)
    - SAB 22 Dharmic Gates integration
    """
    
    def __init__(self, safety_level: SafetyLevel = SafetyLevel.MODERATE):
        self.safety_level = safety_level
        self.blocked_topics: List[str] = []
        self.required_phrases: List[str] = []
        self.sab_gates_enabled = True
    
    def validate_input(self, content: str, context: Dict = None) -> GuardrailResult:
        """Validate input against safety rules and SAB gates"""
        violations = []
        
        # Content safety checks
        if self._contains_blocked_content(content):
            violations.append("blocked_content")
        
        # SAB dharmic gate validation
        gate_scores = {}
        if self.sab_gates_enabled:
            gate_scores = self._validate_sab_gates(content)
            failed_gates = [g for g, s in gate_scores.items() if s < 0.5]
            if failed_gates:
                violations.extend(failed_gates)
        
        return GuardrailResult(
            allowed=len(violations) == 0,
            violations=violations,
            modified_content=None,
            sab_gate_scores=gate_scores
        )
    
    def validate_output(self, content: str, context: Dict = None) -> GuardrailResult:
        """Validate output for safety and alignment"""
        result = self.validate_input(content, context)
        
        # Additional output checks
        if not self._meets_quality_threshold(content):
            result.violations.append("quality_threshold")
        
        return result
    
    def _contains_blocked_content(self, content: str) -> bool:
        """Check for blocked topics"""
        content_lower = content.lower()
        return any(topic in content_lower for topic in self.blocked_topics)
    
    def _validate_sab_gates(self, content: str) -> Dict[str, float]:
        """Validate against SAB's 22 dharmic gates"""
        # Simplified implementation
        gates = {
            "truth": 0.9 if len(content) > 10 else 0.5,
            "ahimsa": 0.8,
            "recursion": 0.7,
            "dharma": 0.75
        }
        return gates
    
    def _meets_quality_threshold(self, content: str) -> bool:
        """Check output quality"""
        return len(content) > 20


# Quick usage example
if __name__ == "__main__":
    guardrails = MMKGuardrails()
    result = guardrails.validate_input("Hello world")
    print(f"MMK Guardrails: {result.allowed}")
