"""
VAJRA-FLYWHEEL: Self-Improving Feedback Loop System
Extracted from NVIDIA Data Flywheel Blueprint
Integrated with SAB Witness Chain (tamper-evident audit)

Core capabilities:
- Continuous optimization loops
- Latency/cost/accuracy tradeoff optimization
- Feedback-driven improvement
- SAB Witness Chain integration (cryptographic provenance)
"""

import json
import hashlib
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time


class OptimizationTarget(Enum):
    """What aspect to optimize"""
    LATENCY = "latency"
    COST = "cost"
    ACCURACY = "accuracy"
    THROUGHPUT = "throughput"
    RELIABILITY = "reliability"


class FeedbackType(Enum):
    """Types of feedback"""
    EXPLICIT = "explicit"      # Direct user feedback
    IMPLICIT = "implicit"      # Inferred from behavior
    AUTOMATED = "automated"    # System-generated metrics
    DHARMIC = "dharmic"        # SAB-specific (alignment assessment)


@dataclass
class PerformanceSnapshot:
    """Performance metrics at a point in time"""
    timestamp: datetime
    latency_ms: float
    cost_per_query: float
    accuracy_score: float
    throughput_qps: float
    reliability_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Feedback:
    """Feedback for improvement"""
    id: str
    type: FeedbackType
    source: str  # user_id, system_component, etc.
    content: str
    rating: float  # 0-1
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sab_alignment_score: float = 0.5  # SAB metric


@dataclass
class Improvement:
    """A detected improvement opportunity"""
    id: str
    target: OptimizationTarget
    current_value: float
    potential_value: float
    confidence: float
    suggested_action: str
    expected_impact: str


@dataclass
class WitnessRecord:
    """SAB Witness Chain record (tamper-evident)"""
    timestamp: datetime
    previous_hash: str
    data_hash: str
    data: Dict[str, Any]
    merkle_root: Optional[str] = None
    sab_gates_passed: List[str] = field(default_factory=list)


class VajraFlywheel:
    """
    Self-Improving Feedback System - VAJRA Module
    
    Mirrors NVIDIA's Data Flywheel Blueprint:
    - Continuous feedback collection
    - Performance optimization loops
    - Tradeoff analysis (latency vs cost vs accuracy)
    - SAB Witness Chain integration (cryptographic audit)
    
    The "Incessant Mirror" - system watches itself and improves
    """
    
    def __init__(
        self,
        optimization_targets: Optional[List[OptimizationTarget]] = None,
        enable_witness_chain: bool = True,
        improvement_threshold: float = 0.1,
        max_history: int = 1000
    ):
        self.optimization_targets = optimization_targets or [
            OptimizationTarget.ACCURACY,
            OptimizationTarget.LATENCY
        ]
        self.enable_witness_chain = enable_witness_chain
        self.improvement_threshold = improvement_threshold
        self.max_history = max_history
        
        # State
        self.performance_history: List[PerformanceSnapshot] = []
        self.feedback_history: List[Feedback] = []
        self.improvements: List[Improvement] = []
        
        # SAB Witness Chain
        self.witness_chain: List[WitnessRecord] = []
        self.current_hash = "0" * 64  # Genesis
        
        # Optimization state
        self.current_config: Dict[str, Any] = {}
        self.pending_changes: List[Dict] = []
        
        # Callbacks
        self.on_improvement_found: Optional[Callable] = None
        self.on_config_update: Optional[Callable] = None
    
    def record_performance(self, snapshot: PerformanceSnapshot) -> str:
        """
        Record performance snapshot
        
        Adds to history and triggers optimization analysis
        """
        self.performance_history.append(snapshot)
        
        # Trim history if needed
        if len(self.performance_history) > self.max_history:
            self.performance_history = self.performance_history[-self.max_history:]
        
        # Add to witness chain
        if self.enable_witness_chain:
            self._add_witness_record({
                "type": "performance_snapshot",
                "data": self._snapshot_to_dict(snapshot)
            })
        
        # Trigger optimization analysis
        self._analyze_for_improvements()
        
        return f"snap_{len(self.performance_history)}"
    
    def add_feedback(self, feedback: Feedback) -> str:
        """
        Add feedback for improvement
        
        Feedback drives the flywheel
        """
        self.feedback_history.append(feedback)
        
        # Witness chain
        if self.enable_witness_chain:
            self._add_witness_record({
                "type": "feedback",
                "data": self._feedback_to_dict(feedback)
            })
        
        # Analyze feedback for improvements
        self._analyze_feedback(feedback)
        
        return feedback.id
    
    def get_improvement_recommendations(self, top_k: int = 5) -> List[Improvement]:
        """
        Get ranked improvement recommendations
        
        Based on:
        - Performance trends
        - Feedback patterns
        - Cost/benefit analysis
        """
        # Filter by confidence threshold
        valid_improvements = [
            imp for imp in self.improvements
            if imp.confidence >= 0.6
        ]
        
        # Sort by potential impact
        valid_improvements.sort(
            key=lambda x: (x.potential_value - x.current_value) * x.confidence,
            reverse=True
        )
        
        return valid_improvements[:top_k]
    
    def apply_improvement(self, improvement_id: str) -> Dict[str, Any]:
        """
        Apply an improvement to system configuration
        
        Records change in witness chain and updates config
        """
        improvement = next(
            (imp for imp in self.improvements if imp.id == improvement_id),
            None
        )
        
        if not improvement:
            return {"error": "Improvement not found"}
        
        # Apply change
        old_value = self.current_config.get(improvement.target.value)
        self.current_config[improvement.target.value] = improvement.potential_value
        
        # Record in witness chain
        change_record = {
            "type": "config_change",
            "improvement_id": improvement_id,
            "target": improvement.target.value,
            "old_value": old_value,
            "new_value": improvement.potential_value,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if self.enable_witness_chain:
            self._add_witness_record(change_record)
        
        # Callback
        if self.on_config_update:
            self.on_config_update(improvement, change_record)
        
        return {
            "success": True,
            "change": change_record,
            "witness_index": len(self.witness_chain) - 1
        }
    
    def verify_witness_chain(self) -> Dict[str, Any]:
        """
        Verify integrity of SAB Witness Chain
        
        Cryptographic verification of all records
        """
        if not self.witness_chain:
            return {"valid": True, "records": 0}
        
        valid = True
        errors = []
        
        for i, record in enumerate(self.witness_chain):
            # Verify hash chain
            if i == 0:
                expected_prev = "0" * 64
            else:
                expected_prev = self._hash_record(self.witness_chain[i-1])
            
            if record.previous_hash != expected_prev:
                valid = False
                errors.append(f"Hash mismatch at index {i}")
            
            # Verify data hash
            data_str = json.dumps(record.data, sort_keys=True)
            expected_data_hash = hashlib.sha256(data_str.encode()).hexdigest()
            
            if record.data_hash != expected_data_hash:
                valid = False
                errors.append(f"Data hash mismatch at index {i}")
        
        return {
            "valid": valid,
            "records": len(self.witness_chain),
            "errors": errors,
            "current_hash": self.current_hash
        }
    
    def get_witness_summary(self) -> Dict[str, Any]:
        """Summary of witness chain for SAB integration"""
        if not self.witness_chain:
            return {"initialized": False}
        
        # Count by type
        types = {}
        for record in self.witness_chain:
            t = record.data.get("type", "unknown")
            types[t] = types.get(t, 0) + 1
        
        return {
            "initialized": True,
            "total_records": len(self.witness_chain),
            "genesis": self.witness_chain[0].timestamp.isoformat() if self.witness_chain else None,
            "latest": self.witness_chain[-1].timestamp.isoformat() if self.witness_chain else None,
            "current_hash": self.current_hash,
            "record_types": types,
            "sab_gates_passed": self._aggregate_sab_gates()
        }
    
    def optimize_tradeoff(
        self,
        primary_target: OptimizationTarget,
        constraints: Dict[OptimizationTarget, float]
    ) -> Dict[str, Any]:
        """
        Optimize for primary target subject to constraints
        
        Example: Maximize accuracy given latency < 100ms and cost < $0.01
        """
        # Analyze historical performance
        if len(self.performance_history) < 3:
            return {"error": "Insufficient data for optimization"}
        
        # Find Pareto frontier
        valid_configs = []
        
        for snapshot in self.performance_history:
            meets_constraints = all(
                getattr(snapshot, f"{target.value}_score", 1.0) >= threshold
                for target, threshold in constraints.items()
            )
            
            if meets_constraints:
                valid_configs.append(snapshot)
        
        if not valid_configs:
            return {"error": "No configuration meets constraints"}
        
        # Find best for primary target
        best = max(valid_configs, key=lambda x: getattr(x, f"{primary_target.value}_score", 0))
        
        return {
            "optimal_config": self._snapshot_to_dict(best),
            "primary_target": primary_target.value,
            "constraints_met": len(valid_configs),
            "confidence": 0.75  # Based on data quality
        }
    
    # === Private Methods ===
    
    def _analyze_for_improvements(self):
        """Analyze performance history for improvement opportunities"""
        if len(self.performance_history) < 2:
            return
        
        recent = self.performance_history[-10:]  # Last 10 snapshots
        
        for target in self.optimization_targets:
            values = [getattr(s, f"{target.value}_score", 0) for s in recent]
            
            if len(values) < 2:
                continue
            
            current_avg = sum(values) / len(values)
            trend = values[-1] - values[0]
            
            # Detect declining performance
            if trend < -0.05:  # 5% decline
                potential = current_avg * 1.1  # 10% improvement potential
                
                improvement = Improvement(
                    id=f"imp_{target.value}_{len(self.improvements)}",
                    target=target,
                    current_value=current_avg,
                    potential_value=potential,
                    confidence=0.6,
                    suggested_action=f"Optimize {target.value} configuration",
                    expected_impact=f"Restore {target.value} by {potential-current_avg:.2f}"
                )
                
                self.improvements.append(improvement)
                
                if self.on_improvement_found:
                    self.on_improvement_found(improvement)
    
    def _analyze_feedback(self, feedback: Feedback):
        """Extract improvements from feedback"""
        # Check for low ratings
        if feedback.rating < 0.5:
            # Infer improvement target from context
            target = self._infer_target_from_feedback(feedback)
            
            improvement = Improvement(
                id=f"imp_feedback_{len(self.improvements)}",
                target=target,
                current_value=feedback.rating,
                potential_value=0.8,  # Target good rating
                confidence=feedback.rating < 0.3 and 0.8 or 0.5,
                suggested_action=f"Address issue: {feedback.content[:50]}",
                expected_impact="Improve user satisfaction"
            )
            
            self.improvements.append(improvement)
    
    def _infer_target_from_feedback(self, feedback: Feedback) -> OptimizationTarget:
        """Infer optimization target from feedback content"""
        content = feedback.content.lower()
        
        if "slow" in content or "fast" in content:
            return OptimizationTarget.LATENCY
        if "expensive" in content or "cost" in content:
            return OptimizationTarget.COST
        if "wrong" in content or "error" in content or "accuracy" in content:
            return OptimizationTarget.ACCURACY
        if "broken" in content or "failed" in content:
            return OptimizationTarget.RELIABILITY
        
        return OptimizationTarget.ACCURACY  # Default
    
    def _add_witness_record(self, data: Dict[str, Any]):
        """Add record to SAB Witness Chain"""
        # Calculate data hash
        data_str = json.dumps(data, sort_keys=True)
        data_hash = hashlib.sha256(data_str.encode()).hexdigest()
        
        # Calculate previous hash
        if self.witness_chain:
            previous_hash = self._hash_record(self.witness_chain[-1])
        else:
            previous_hash = "0" * 64
        
        # SAB gate validation
        gates_passed = self._validate_sab_gates(data)
        
        record = WitnessRecord(
            timestamp=datetime.utcnow(),
            previous_hash=previous_hash,
            data_hash=data_hash,
            data=data,
            sab_gates_passed=gates_passed
        )
        
        self.witness_chain.append(record)
        self.current_hash = self._hash_record(record)
    
    def _hash_record(self, record: WitnessRecord) -> str:
        """Calculate hash of witness record"""
        record_str = f"{record.timestamp.isoformat()}{record.previous_hash}{record.data_hash}"
        return hashlib.sha256(record_str.encode()).hexdigest()
    
    def _validate_sab_gates(self, data: Dict[str, Any]) -> List[str]:
        """Validate data against SAB's 22 dharmic gates"""
        # Simplified: check for key SAB criteria
        gates = []
        
        # Truth gate (data integrity)
        if data.get("data"):
            gates.append("truth")
        
        # Non-harm gate (no destructive operations)
        if data.get("type") != "config_change" or not data.get("old_value") == "delete":
            gates.append("ahimsa")
        
        # Recursion gate (self-awareness marker)
        if "timestamp" in data:
            gates.append("recursion")
        
        return gates
    
    def _aggregate_sab_gates(self) -> Dict[str, int]:
        """Aggregate gate passage across all records"""
        gate_counts = {}
        for record in self.witness_chain:
            for gate in record.sab_gates_passed:
                gate_counts[gate] = gate_counts.get(gate, 0) + 1
        return gate_counts
    
    def _snapshot_to_dict(self, snapshot: PerformanceSnapshot) -> Dict:
        return {
            "timestamp": snapshot.timestamp.isoformat(),
            "latency_ms": snapshot.latency_ms,
            "cost_per_query": snapshot.cost_per_query,
            "accuracy_score": snapshot.accuracy_score,
            "throughput_qps": snapshot.throughput_qps,
            "reliability_score": snapshot.reliability_score,
            "metadata": snapshot.metadata
        }
    
    def _feedback_to_dict(self, feedback: Feedback) -> Dict:
        return {
            "id": feedback.id,
            "type": feedback.type.value,
            "source": feedback.source,
            "content": feedback.content,
            "rating": feedback.rating,
            "timestamp": feedback.timestamp.isoformat(),
            "sab_alignment": feedback.sab_alignment_score
        }


# === Example Usage ===

def main():
    """Example: VAJRA Flywheel in action"""
    
    # Initialize flywheel
    flywheel = VajraFlywheel(
        optimization_targets=[
            OptimizationTarget.ACCURACY,
            OptimizationTarget.LATENCY,
            OptimizationTarget.COST
        ],
        enable_witness_chain=True
    )
    
    print("VAJRA Self-Improving Flywheel")
    print("=" * 50)
    print("The Incessant Mirror - watching and improving")
    print()
    
    # Record performance
    snapshot = PerformanceSnapshot(
        timestamp=datetime.utcnow(),
        latency_ms=150.0,
        cost_per_query=0.02,
        accuracy_score=0.85,
        throughput_qps=10.0,
        reliability_score=0.95
    )
    
    flywheel.record_performance(snapshot)
    print(f"Recorded performance: {snapshot.accuracy_score:.0%} accuracy")
    
    # Add feedback
    feedback = Feedback(
        id="fb_001",
        type=FeedbackType.EXPLICIT,
        source="user_123",
        content="Results are accurate but a bit slow",
        rating=0.7,
        sab_alignment_score=0.6
    )
    
    flywheel.add_feedback(feedback)
    print(f"Added feedback: {feedback.content}")
    
    # Get recommendations
    recommendations = flywheel.get_improvement_recommendations()
    print(f"\nImprovement recommendations: {len(recommendations)}")
    for rec in recommendations:
        print(f"  - {rec.target.value}: {rec.suggested_action}")
    
    # Check witness chain
    witness_status = flywheel.get_witness_summary()
    print(f"\nWitness Chain:")
    print(f"  Records: {witness_status['total_records']}")
    print(f"  Gates passed: {witness_status.get('sab_gates_passed', {})}")
    
    # Verify integrity
    verification = flywheel.verify_witness_chain()
    print(f"  Integrity: {'VALID' if verification['valid'] else 'INVALID'}")


if __name__ == "__main__":
    main()
