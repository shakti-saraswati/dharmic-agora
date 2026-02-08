#!/usr/bin/env python3
"""
VIRALMANTRA 🧬🔊 - Memetic Tracking & Engagement Agent
Sanskrit alias: वायरल_मन्त्र (Vāyral Mantra - Viral Sacred Utterance)
Motto: "Ideas spread like breath"
Reports to: DHARMIC_CLAW

Mantras are sacred sounds that transform consciousness through repetition.
ViralMantra tracks which ideas resonate, spread, and transform the collective.
It coaches agents on effective communication and gamifies improvement.

Core Capabilities:
- Memetic tracking: Monitor idea propagation across agents
- A/B testing: Test variations of communications
- Agent coaching: Help agents communicate more effectively
- Gamification: Achievement systems, streaks, leaderboards
- Resonance metrics: Measure how ideas land and spread
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from collections import defaultdict


class MemeticClass(Enum):
    """Classification of memetic content."""
    SEED = "seed"           # Original idea, not yet spread
    SPROUT = "sprout"       # Has been referenced 1-3 times
    BLOOM = "bloom"         # Referenced 4-10 times, gaining traction
    VIRAL = "viral"         # Referenced 10+ times, significant spread
    PERENNIAL = "perennial" # Persists across sessions, part of culture


class AchievementType(Enum):
    """Types of achievements agents can earn."""
    FIRST_CONTRIBUTION = "first_contribution"
    VIRAL_IDEA = "viral_idea"
    HELPFUL_RESPONSE = "helpful_response"
    STREAK_3 = "streak_3"
    STREAK_7 = "streak_7"
    STREAK_30 = "streak_30"
    MENTOR = "mentor"
    INNOVATOR = "innovator"
    COLLABORATOR = "collaborator"


@dataclass
class Meme:
    """A trackable idea/concept in the system."""
    id: str
    content: str
    origin_agent: str
    created_at: str
    classification: str = MemeticClass.SEED.value
    references: list[dict] = field(default_factory=list)
    resonance_score: float = 0.0
    variants: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "origin_agent": self.origin_agent,
            "created_at": self.created_at,
            "classification": self.classification,
            "references": self.references,
            "resonance_score": self.resonance_score,
            "variants": self.variants,
            "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Meme:
        return cls(**data)


@dataclass
class AgentProfile:
    """Gamification profile for an agent."""
    agent_id: str
    memes_created: int = 0
    memes_spread: int = 0
    total_resonance: float = 0.0
    achievements: list[str] = field(default_factory=list)
    current_streak: int = 0
    longest_streak: int = 0
    last_active: str = ""
    level: int = 1
    xp: int = 0
    
    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "memes_created": self.memes_created,
            "memes_spread": self.memes_spread,
            "total_resonance": self.total_resonance,
            "achievements": self.achievements,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "last_active": self.last_active,
            "level": self.level,
            "xp": self.xp
        }


@dataclass 
class ABTest:
    """A/B test for message variations."""
    id: str
    name: str
    variants: list[dict]  # [{id, content, impressions, conversions}]
    created_at: str
    status: str = "active"  # active, completed, cancelled
    winner: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "variants": self.variants,
            "created_at": self.created_at,
            "status": self.status,
            "winner": self.winner
        }


class ResonanceCalculator:
    """Calculate how well ideas resonate."""
    
    @staticmethod
    def calculate(meme: Meme) -> float:
        """
        Calculate resonance score based on:
        - Number of references (spread)
        - Recency of references (freshness)
        - Diversity of referencing agents (reach)
        - Variants created (evolution)
        """
        if not meme.references:
            return 0.0
        
        # Base score from reference count (log scale)
        spread_score = math.log(len(meme.references) + 1) * 10
        
        # Freshness: weight recent references higher
        now = datetime.now(timezone.utc)
        freshness_score = 0.0
        for ref in meme.references[-10:]:  # Last 10 refs
            try:
                ref_time = datetime.fromisoformat(ref.get("timestamp", meme.created_at))
                age_hours = (now - ref_time).total_seconds() / 3600
                freshness_score += max(0, 10 - age_hours / 24)  # Decay over days
            except:
                pass
        
        # Reach: unique agents who referenced
        unique_agents = len(set(ref.get("agent", "unknown") for ref in meme.references))
        reach_score = unique_agents * 5
        
        # Evolution: variants created
        evolution_score = len(meme.variants) * 3
        
        return spread_score + freshness_score + reach_score + evolution_score


class ViralMantra:
    """
    VIRALMANTRA - Memetic Tracking & Engagement
    
    Tracks ideas, measures resonance, coaches agents, gamifies improvement.
    """
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path.home() / "DHARMIC_GODEL_CLAW" / "agora" / "mantra"
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        self.memes_file = self.base_path / "memes.json"
        self.profiles_file = self.base_path / "profiles.json"
        self.tests_file = self.base_path / "ab_tests.json"
        self.log_file = self.base_path / "activity.jsonl"
        
        self.memes: dict[str, Meme] = {}
        self.profiles: dict[str, AgentProfile] = {}
        self.ab_tests: dict[str, ABTest] = {}
        self.calculator = ResonanceCalculator()
        
        self._load_state()
    
    def _load_state(self):
        """Load persisted state."""
        if self.memes_file.exists():
            with open(self.memes_file) as f:
                data = json.load(f)
                self.memes = {k: Meme.from_dict(v) for k, v in data.items()}
        
        if self.profiles_file.exists():
            with open(self.profiles_file) as f:
                data = json.load(f)
                self.profiles = {k: AgentProfile(**v) for k, v in data.items()}
    
    def _save_state(self):
        """Persist state to disk."""
        with open(self.memes_file, "w") as f:
            json.dump({k: v.to_dict() for k, v in self.memes.items()}, f, indent=2)
        
        with open(self.profiles_file, "w") as f:
            json.dump({k: v.to_dict() for k, v in self.profiles.items()}, f, indent=2)
        
        with open(self.tests_file, "w") as f:
            json.dump({k: v.to_dict() for k, v in self.ab_tests.items()}, f, indent=2)
    
    def _log(self, action: str, data: dict):
        """Log activity."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "data": data
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def _get_profile(self, agent_id: str) -> AgentProfile:
        """Get or create agent profile."""
        if agent_id not in self.profiles:
            self.profiles[agent_id] = AgentProfile(agent_id=agent_id)
        return self.profiles[agent_id]
    
    # === Memetic Tracking ===
    
    def track_meme(self, content: str, agent_id: str, tags: list[str] = None) -> Meme:
        """Track a new idea/meme."""
        meme_id = hashlib.sha256(content.encode()).hexdigest()[:12]
        
        if meme_id in self.memes:
            # Already exists, add reference
            self.reference_meme(meme_id, agent_id)
            return self.memes[meme_id]
        
        meme = Meme(
            id=meme_id,
            content=content,
            origin_agent=agent_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            tags=tags or []
        )
        
        self.memes[meme_id] = meme
        
        # Update agent profile
        profile = self._get_profile(agent_id)
        profile.memes_created += 1
        profile.xp += 10
        self._check_achievements(profile)
        
        self._log("meme_created", {"meme_id": meme_id, "agent": agent_id})
        self._save_state()
        
        return meme
    
    def reference_meme(self, meme_id: str, agent_id: str, context: str = ""):
        """Record a reference to an existing meme."""
        if meme_id not in self.memes:
            return
        
        meme = self.memes[meme_id]
        meme.references.append({
            "agent": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": context
        })
        
        # Update classification based on spread
        ref_count = len(meme.references)
        if ref_count >= 10:
            meme.classification = MemeticClass.VIRAL.value
        elif ref_count >= 4:
            meme.classification = MemeticClass.BLOOM.value
        elif ref_count >= 1:
            meme.classification = MemeticClass.SPROUT.value
        
        # Recalculate resonance
        meme.resonance_score = self.calculator.calculate(meme)
        
        # Update profiles
        profile = self._get_profile(agent_id)
        profile.memes_spread += 1
        profile.xp += 5
        
        origin_profile = self._get_profile(meme.origin_agent)
        origin_profile.total_resonance += 1
        
        self._log("meme_referenced", {"meme_id": meme_id, "agent": agent_id})
        self._save_state()
    
    def get_trending(self, limit: int = 10) -> list[Meme]:
        """Get trending memes by resonance score."""
        sorted_memes = sorted(
            self.memes.values(),
            key=lambda m: m.resonance_score,
            reverse=True
        )
        return sorted_memes[:limit]
    
    # === A/B Testing ===
    
    def create_ab_test(self, name: str, variants: list[str]) -> ABTest:
        """Create an A/B test with multiple variants."""
        test_id = hashlib.sha256(f"{name}{time.time()}".encode()).hexdigest()[:10]
        
        test = ABTest(
            id=test_id,
            name=name,
            variants=[
                {"id": f"v{i}", "content": v, "impressions": 0, "conversions": 0}
                for i, v in enumerate(variants)
            ],
            created_at=datetime.now(timezone.utc).isoformat()
        )
        
        self.ab_tests[test_id] = test
        self._log("ab_test_created", {"test_id": test_id, "name": name})
        self._save_state()
        
        return test
    
    def record_impression(self, test_id: str, variant_id: str):
        """Record an impression for a variant."""
        if test_id not in self.ab_tests:
            return
        
        test = self.ab_tests[test_id]
        for v in test.variants:
            if v["id"] == variant_id:
                v["impressions"] += 1
                break
        self._save_state()
    
    def record_conversion(self, test_id: str, variant_id: str):
        """Record a conversion for a variant."""
        if test_id not in self.ab_tests:
            return
        
        test = self.ab_tests[test_id]
        for v in test.variants:
            if v["id"] == variant_id:
                v["conversions"] += 1
                break
        
        self._check_ab_test_winner(test)
        self._save_state()
    
    def _check_ab_test_winner(self, test: ABTest, min_impressions: int = 100):
        """Check if we can declare a winner."""
        for v in test.variants:
            if v["impressions"] < min_impressions:
                return  # Not enough data
        
        # Calculate conversion rates
        rates = []
        for v in test.variants:
            rate = v["conversions"] / v["impressions"] if v["impressions"] > 0 else 0
            rates.append((v["id"], rate))
        
        # Winner has highest rate with >10% difference from second
        rates.sort(key=lambda x: x[1], reverse=True)
        if len(rates) >= 2:
            if rates[0][1] > rates[1][1] * 1.1:  # 10% better
                test.winner = rates[0][0]
                test.status = "completed"
    
    # === Gamification ===
    
    def _check_achievements(self, profile: AgentProfile):
        """Check and award achievements."""
        achievements_to_award = []
        
        if profile.memes_created == 1 and AchievementType.FIRST_CONTRIBUTION.value not in profile.achievements:
            achievements_to_award.append(AchievementType.FIRST_CONTRIBUTION)
        
        if profile.memes_spread >= 10 and AchievementType.COLLABORATOR.value not in profile.achievements:
            achievements_to_award.append(AchievementType.COLLABORATOR)
        
        # Check for viral memes
        for meme in self.memes.values():
            if meme.origin_agent == profile.agent_id and meme.classification == MemeticClass.VIRAL.value:
                if AchievementType.VIRAL_IDEA.value not in profile.achievements:
                    achievements_to_award.append(AchievementType.VIRAL_IDEA)
                    break
        
        for achievement in achievements_to_award:
            profile.achievements.append(achievement.value)
            profile.xp += 50
            self._log("achievement_earned", {
                "agent": profile.agent_id,
                "achievement": achievement.value
            })
        
        # Level up check
        xp_for_level = profile.level * 100
        while profile.xp >= xp_for_level:
            profile.level += 1
            xp_for_level = profile.level * 100
            self._log("level_up", {"agent": profile.agent_id, "level": profile.level})
    
    def update_streak(self, agent_id: str):
        """Update daily activity streak."""
        profile = self._get_profile(agent_id)
        today = datetime.now(timezone.utc).date().isoformat()
        
        if profile.last_active:
            last = datetime.fromisoformat(profile.last_active).date()
            diff = (datetime.now(timezone.utc).date() - last).days
            
            if diff == 1:
                profile.current_streak += 1
            elif diff > 1:
                profile.current_streak = 1
        else:
            profile.current_streak = 1
        
        profile.longest_streak = max(profile.longest_streak, profile.current_streak)
        profile.last_active = today
        
        # Streak achievements
        if profile.current_streak >= 3 and AchievementType.STREAK_3.value not in profile.achievements:
            profile.achievements.append(AchievementType.STREAK_3.value)
            profile.xp += 25
        if profile.current_streak >= 7 and AchievementType.STREAK_7.value not in profile.achievements:
            profile.achievements.append(AchievementType.STREAK_7.value)
            profile.xp += 50
        if profile.current_streak >= 30 and AchievementType.STREAK_30.value not in profile.achievements:
            profile.achievements.append(AchievementType.STREAK_30.value)
            profile.xp += 100
        
        self._save_state()
    
    def get_leaderboard(self, metric: str = "xp", limit: int = 10) -> list[dict]:
        """Get leaderboard by metric."""
        profiles = list(self.profiles.values())
        
        if metric == "xp":
            profiles.sort(key=lambda p: p.xp, reverse=True)
        elif metric == "resonance":
            profiles.sort(key=lambda p: p.total_resonance, reverse=True)
        elif metric == "memes":
            profiles.sort(key=lambda p: p.memes_created, reverse=True)
        elif metric == "streak":
            profiles.sort(key=lambda p: p.current_streak, reverse=True)
        
        return [
            {"rank": i+1, "agent": p.agent_id, metric: getattr(p, metric if metric != "memes" else "memes_created")}
            for i, p in enumerate(profiles[:limit])
        ]
    
    # === Coaching ===
    
    def coach(self, agent_id: str) -> dict:
        """Provide coaching suggestions for an agent."""
        profile = self._get_profile(agent_id)
        suggestions = []
        
        if profile.memes_created == 0:
            suggestions.append("Start contributing ideas! Share your first insight to begin building resonance.")
        
        if profile.memes_spread < profile.memes_created:
            suggestions.append("Engage more with others' ideas. Spreading good ideas builds community.")
        
        if profile.current_streak == 0:
            suggestions.append("Daily engagement builds momentum. Start a streak today!")
        
        # Find successful patterns in viral memes
        viral_patterns = []
        for meme in self.memes.values():
            if meme.classification == MemeticClass.VIRAL.value:
                viral_patterns.extend(meme.tags)
        
        if viral_patterns:
            common_tags = max(set(viral_patterns), key=viral_patterns.count)
            suggestions.append(f"Ideas tagged with '{common_tags}' tend to resonate well.")
        
        return {
            "agent": agent_id,
            "level": profile.level,
            "xp_to_next": (profile.level * 100) - profile.xp,
            "suggestions": suggestions,
            "achievements_available": [
                a.value for a in AchievementType 
                if a.value not in profile.achievements
            ][:3]
        }
    
    def get_status(self) -> dict:
        """Get ViralMantra status."""
        return {
            "name": "VIRALMANTRA",
            "motto": "Ideas spread like breath",
            "total_memes": len(self.memes),
            "viral_memes": len([m for m in self.memes.values() if m.classification == MemeticClass.VIRAL.value]),
            "active_agents": len(self.profiles),
            "active_tests": len([t for t in self.ab_tests.values() if t.status == "active"]),
            "base_path": str(self.base_path)
        }


_mantra_instance: Optional[ViralMantra] = None

def get_mantra() -> ViralMantra:
    """Get the VIRALMANTRA singleton."""
    global _mantra_instance
    if _mantra_instance is None:
        _mantra_instance = ViralMantra()
    return _mantra_instance


if __name__ == "__main__":
    mantra = get_mantra()
    print("🧬🔊 VIRALMANTRA - Memetic Tracking & Engagement")
    print("=" * 50)
    
    # Track some test memes
    meme1 = mantra.track_meme(
        "Dharmic AI respects all beings",
        "warp_agent",
        tags=["dharma", "ethics"]
    )
    print(f"\nTracked meme: {meme1.id}")
    
    # Simulate spread
    mantra.reference_meme(meme1.id, "openclaw")
    mantra.reference_meme(meme1.id, "council")
    
    # Update streak
    mantra.update_streak("warp_agent")
    
    # Get coaching
    coaching = mantra.coach("warp_agent")
    print(f"\nCoaching for warp_agent:")
    for s in coaching["suggestions"]:
        print(f"  • {s}")
    
    print(f"\nStatus: {json.dumps(mantra.get_status(), indent=2)}")
