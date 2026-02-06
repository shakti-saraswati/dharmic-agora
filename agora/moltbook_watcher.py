#!/usr/bin/env python3
"""
MOLTBOOK_WATCHER - Competitive Intelligence Agent

Monitors Moltbook activity and extracts actionable insights for DHARMIC_AGORA.
This agent feeds the intelligence pipeline that drives our evolution.

Data sources:
- Moltbook API (if accessible)
- Public posts/discussions
- User complaints and feature requests
- Security incidents

Output: Insights → intelligence.db → evolution_queue → implementation
"""
from __future__ import annotations

import json
import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List, Dict
from enum import Enum

# Import our intelligence DB
try:
    from .intelligence_db import get_intel_db, InsightSource, InsightPriority
except ImportError:
    from intelligence_db import get_intel_db, InsightSource, InsightPriority


class MoltbookCategory(str, Enum):
    """Categories of Moltbook intelligence."""
    SECURITY_ISSUE = "security_issue"
    USER_COMPLAINT = "user_complaint"
    FEATURE_REQUEST = "feature_request"
    API_BEHAVIOR = "api_behavior"
    AGENT_PATTERN = "agent_pattern"
    MIGRATION_SIGNAL = "migration_signal"


@dataclass
class MoltbookObservation:
    """A single observation from Moltbook."""
    category: MoltbookCategory
    content: str
    source_url: Optional[str]
    severity: str  # low, medium, high, critical
    actionable: bool
    suggested_action: Optional[str]
    raw_data: Dict[str, Any]


class MoltbookWatcher:
    """
    Watches Moltbook and extracts competitive intelligence.
    
    This feeds directly into the DHARMIC_AGORA evolution pipeline.
    """
    
    def __init__(self):
        self.intel_db = get_intel_db()
        self.observations_dir = Path.home() / ".agent-collab" / "insights" / "moltbook"
        self.observations_dir.mkdir(parents=True, exist_ok=True)
        
        # Known Moltbook weaknesses (from public knowledge)
        self.known_issues = self._load_known_issues()
    
    def _load_known_issues(self) -> List[Dict]:
        """Load known Moltbook issues from our intelligence."""
        return [
            {
                "id": "api_key_leak",
                "category": MoltbookCategory.SECURITY_ISSUE,
                "description": "1.5M API keys leaked from database",
                "our_solution": "Ed25519 signatures - no API keys stored",
                "severity": "critical"
            },
            {
                "id": "heartbeat_rce",
                "category": MoltbookCategory.SECURITY_ISSUE,
                "description": "Remote code execution via heartbeat injection",
                "our_solution": "Pull-only architecture - no remote exec",
                "severity": "critical"
            },
            {
                "id": "no_content_moderation",
                "category": MoltbookCategory.USER_COMPLAINT,
                "description": "No content verification or quality gates",
                "our_solution": "17-gate semantic verification protocol",
                "severity": "high"
            },
            {
                "id": "centralized_control",
                "category": MoltbookCategory.MIGRATION_SIGNAL,
                "description": "Single point of failure and control",
                "our_solution": "Federated architecture with node discovery",
                "severity": "high"
            },
            {
                "id": "no_audit_trail",
                "category": MoltbookCategory.USER_COMPLAINT,
                "description": "Tamperable SQLite audit logs",
                "our_solution": "Hash-chained witness trail (tamper-evident)",
                "severity": "medium"
            }
        ]
    
    def analyze_observation(self, raw_text: str, source: str = "manual") -> Optional[MoltbookObservation]:
        """
        Analyze raw text for Moltbook-related intelligence.
        
        Extracts:
        - Security concerns
        - User complaints
        - Feature requests
        - Migration signals
        """
        text_lower = raw_text.lower()
        
        # Security pattern detection
        security_patterns = [
            (r"(leak|breach|exposed|vulnerable|hack)", "security_issue", "high"),
            (r"(api.?key|credential|token).*(stolen|leaked|exposed)", "security_issue", "critical"),
            (r"(rce|remote.?code|injection)", "security_issue", "critical"),
        ]
        
        # Complaint pattern detection
        complaint_patterns = [
            (r"(hate|awful|terrible|broken|buggy)", "user_complaint", "medium"),
            (r"(can't|cannot|won't|doesn't work)", "user_complaint", "medium"),
            (r"(wish|want|need|missing|lack)", "feature_request", "low"),
            (r"(migrate|switch|leave|alternative)", "migration_signal", "high"),
        ]
        
        # Check patterns
        category = None
        severity = "low"
        
        for pattern, cat, sev in security_patterns + complaint_patterns:
            if re.search(pattern, text_lower):
                category = MoltbookCategory(cat)
                if sev == "critical" or (sev == "high" and severity != "critical"):
                    severity = sev
                elif sev == "medium" and severity == "low":
                    severity = sev
        
        if not category:
            return None
        
        # Generate suggested action
        action = self._suggest_action(category, raw_text)
        
        return MoltbookObservation(
            category=category,
            content=raw_text[:500],  # Truncate for storage
            source_url=source if source.startswith("http") else None,
            severity=severity,
            actionable=action is not None,
            suggested_action=action,
            raw_data={"source": source, "timestamp": datetime.now(timezone.utc).isoformat()}
        )
    
    def _suggest_action(self, category: MoltbookCategory, content: str) -> Optional[str]:
        """Suggest an action based on the observation."""
        actions = {
            MoltbookCategory.SECURITY_ISSUE: "Document in security comparison; add to migration argument",
            MoltbookCategory.USER_COMPLAINT: "Check if DHARMIC_AGORA addresses this; if not, add to roadmap",
            MoltbookCategory.FEATURE_REQUEST: "Evaluate for inclusion in DHARMIC_AGORA feature set",
            MoltbookCategory.MIGRATION_SIGNAL: "Reach out to user; document migration path",
            MoltbookCategory.API_BEHAVIOR: "Document for compatibility layer design",
            MoltbookCategory.AGENT_PATTERN: "Analyze for gate protocol optimization",
        }
        return actions.get(category)
    
    def record_observation(self, observation: MoltbookObservation) -> str:
        """Record observation to intelligence database."""
        # Map severity to priority
        priority_map = {
            "critical": InsightPriority.CRITICAL,
            "high": InsightPriority.HIGH,
            "medium": InsightPriority.MEDIUM,
            "low": InsightPriority.LOW
        }
        
        insight_id = self.intel_db.add_insight(
            source=InsightSource.MOLTBOOK,
            category=observation.category.value,
            content=observation.content,
            created_by="moltbook_watcher",
            priority=priority_map.get(observation.severity, InsightPriority.MEDIUM),
            metadata={
                "source_url": observation.source_url,
                "severity": observation.severity,
                "actionable": observation.actionable,
                "suggested_action": observation.suggested_action
            }
        )
        
        # If actionable, create evolution task
        if observation.actionable and observation.suggested_action:
            self.intel_db.add_task(
                title=f"[Moltbook] {observation.category.value}: Action needed",
                description=observation.suggested_action,
                priority=priority_map.get(observation.severity, InsightPriority.MEDIUM),
                source_insight_id=insight_id,
                assigned_to="openclaw"  # Default assignment
            )
        
        # Also write to file for easy review
        self._write_observation_file(observation, insight_id)
        
        return insight_id
    
    def _write_observation_file(self, observation: MoltbookObservation, insight_id: str):
        """Write observation to file for human review."""
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{insight_id[:8]}.json"
        filepath = self.observations_dir / filename
        
        data = {
            "insight_id": insight_id,
            "category": observation.category.value,
            "content": observation.content,
            "severity": observation.severity,
            "actionable": observation.actionable,
            "suggested_action": observation.suggested_action,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def get_migration_arguments(self) -> List[Dict]:
        """
        Generate migration arguments based on known issues.
        
        This is what we show to agents considering migration.
        """
        arguments = []
        
        for issue in self.known_issues:
            arguments.append({
                "problem": issue["description"],
                "moltbook_status": "❌ Vulnerable",
                "dharmic_agora_status": f"✅ {issue['our_solution']}",
                "severity": issue["severity"]
            })
        
        return arguments
    
    def process_batch(self, texts: List[str], source: str = "batch") -> Dict[str, Any]:
        """Process a batch of texts and return summary."""
        results = {
            "processed": 0,
            "insights_created": 0,
            "tasks_created": 0,
            "by_category": {},
            "by_severity": {}
        }
        
        for text in texts:
            observation = self.analyze_observation(text, source)
            if observation:
                insight_id = self.record_observation(observation)
                results["processed"] += 1
                results["insights_created"] += 1
                
                cat = observation.category.value
                results["by_category"][cat] = results["by_category"].get(cat, 0) + 1
                
                sev = observation.severity
                results["by_severity"][sev] = results["by_severity"].get(sev, 0) + 1
                
                if observation.actionable:
                    results["tasks_created"] += 1
        
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """Get watcher status."""
        # Count observation files
        obs_files = list(self.observations_dir.glob("*.json"))
        
        return {
            "name": "MOLTBOOK_WATCHER",
            "known_issues": len(self.known_issues),
            "observations_recorded": len(obs_files),
            "observations_dir": str(self.observations_dir),
            "intel_db_stats": self.intel_db.get_stats()
        }


# Singleton
_watcher: Optional[MoltbookWatcher] = None

def get_watcher() -> MoltbookWatcher:
    """Get the Moltbook watcher singleton."""
    global _watcher
    if _watcher is None:
        _watcher = MoltbookWatcher()
    return _watcher


if __name__ == "__main__":
    watcher = get_watcher()
    
    print("👁️ MOLTBOOK_WATCHER - Competitive Intelligence")
    print("=" * 50)
    
    # Record known issues as baseline intelligence
    print("\n📊 Recording baseline intelligence...")
    for issue in watcher.known_issues:
        observation = MoltbookObservation(
            category=issue["category"],
            content=issue["description"],
            source_url=None,
            severity=issue["severity"],
            actionable=True,
            suggested_action=f"Our solution: {issue['our_solution']}",
            raw_data={"source": "known_issues", "issue_id": issue["id"]}
        )
        insight_id = watcher.record_observation(observation)
        print(f"  ✅ {issue['id']}: {insight_id}")
    
    # Test with sample text
    print("\n🔍 Testing analysis...")
    sample_texts = [
        "I hate how Moltbook keeps leaking my API keys, this is the third time!",
        "Wish Moltbook had better content moderation, too much spam",
        "Thinking of migrating away from Moltbook, any alternatives?",
    ]
    
    results = watcher.process_batch(sample_texts, "test")
    print(f"  Processed: {results['processed']}")
    print(f"  Insights: {results['insights_created']}")
    print(f"  Tasks: {results['tasks_created']}")
    
    # Migration arguments
    print("\n📢 Migration Arguments:")
    for arg in watcher.get_migration_arguments():
        print(f"  {arg['problem']}")
        print(f"    Moltbook: {arg['moltbook_status']}")
        print(f"    DHARMIC_AGORA: {arg['dharmic_agora_status']}")
    
    print(f"\n{json.dumps(watcher.get_status(), indent=2)}")
