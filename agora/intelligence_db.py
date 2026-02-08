#!/usr/bin/env python3
"""
Shared Intelligence Database for DHARMIC_AGORA

A SQLite-based shared memory that both Warp and OpenClaw can read/write.
This becomes the automated coordination layer - no more manual message relay.

Tables:
- insights: Raw intelligence from any source
- synthesis: Processed insights ready for action
- evolution_queue: Prioritized tasks for implementation
- agent_activity: Track who's contributing what
"""
from __future__ import annotations

import json
import hashlib
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List
from enum import Enum


class InsightSource(str, Enum):
    MOLTBOOK = "moltbook"
    RESEARCH = "research"
    USER_FEEDBACK = "user_feedback"
    AGENT_OBSERVATION = "agent_observation"
    SYNTHESIS = "synthesis"


class InsightPriority(str, Enum):
    CRITICAL = "critical"  # Act now
    HIGH = "high"          # This week
    MEDIUM = "medium"      # This month
    LOW = "low"            # Backlog


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class Insight:
    """A piece of intelligence from any source."""
    id: str
    source: str
    category: str
    content: str
    priority: str
    created_by: str
    created_at: str
    metadata: dict
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass 
class EvolutionTask:
    """A task in the evolution queue."""
    id: str
    title: str
    description: str
    priority: str
    status: str
    source_insight_id: Optional[str]
    assigned_to: Optional[str]
    created_at: str
    completed_at: Optional[str]
    result: Optional[dict]


class IntelligenceDB:
    """
    Shared intelligence database for DHARMIC_AGORA ecosystem.
    
    Location: ~/.agent-collab/intelligence.db
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path.home() / ".agent-collab" / "intelligence.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Insights table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insights (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                priority TEXT DEFAULT 'medium',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """)
        
        # Synthesis table (processed insights)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS synthesis (
                id TEXT PRIMARY KEY,
                insight_ids TEXT NOT NULL,
                summary TEXT NOT NULL,
                actionable_items TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        # Evolution queue
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evolution_queue (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'pending',
                source_insight_id TEXT,
                assigned_to TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                result TEXT
            )
        """)
        
        # Agent activity log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                timestamp TEXT NOT NULL,
                details TEXT DEFAULT '{}'
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_source ON insights(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_insights_priority ON insights(priority)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_status ON evolution_queue(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_agent ON agent_activity(agent_id)")
        
        conn.commit()
        conn.close()
    
    def _generate_id(self, *parts) -> str:
        """Generate unique ID from parts."""
        content = f"{datetime.now(timezone.utc).isoformat()}" + "".join(str(p) for p in parts)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    # === Insight Operations ===
    
    def add_insight(
        self,
        source: InsightSource,
        category: str,
        content: str,
        created_by: str,
        priority: InsightPriority = InsightPriority.MEDIUM,
        metadata: dict = None
    ) -> str:
        """Add a new insight to the database."""
        insight_id = self._generate_id(source, category, content)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO insights 
            (id, source, category, content, priority, created_by, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            insight_id,
            source.value if isinstance(source, InsightSource) else source,
            category,
            content,
            priority.value if isinstance(priority, InsightPriority) else priority,
            created_by,
            datetime.now(timezone.utc).isoformat(),
            json.dumps(metadata or {})
        ))
        
        # Log activity
        self._log_activity(conn, created_by, "add_insight", insight_id)
        
        conn.commit()
        conn.close()
        
        return insight_id
    
    def get_insights(
        self,
        source: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50
    ) -> List[Insight]:
        """Query insights with optional filters."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT * FROM insights WHERE 1=1"
        params = []
        
        if source:
            query += " AND source = ?"
            params.append(source)
        if category:
            query += " AND category = ?"
            params.append(category)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [
            Insight(
                id=row[0],
                source=row[1],
                category=row[2],
                content=row[3],
                priority=row[4],
                created_by=row[5],
                created_at=row[6],
                metadata=json.loads(row[7])
            )
            for row in rows
        ]
    
    # === Evolution Queue Operations ===
    
    def add_task(
        self,
        title: str,
        description: str,
        priority: InsightPriority = InsightPriority.MEDIUM,
        source_insight_id: Optional[str] = None,
        assigned_to: Optional[str] = None
    ) -> str:
        """Add a task to the evolution queue."""
        task_id = self._generate_id(title, description)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO evolution_queue 
            (id, title, description, priority, status, source_insight_id, assigned_to, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            title,
            description,
            priority.value if isinstance(priority, InsightPriority) else priority,
            TaskStatus.PENDING.value,
            source_insight_id,
            assigned_to,
            datetime.now(timezone.utc).isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return task_id
    
    def get_pending_tasks(self, assigned_to: Optional[str] = None) -> List[EvolutionTask]:
        """Get pending tasks from the queue."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if assigned_to:
            cursor.execute("""
                SELECT * FROM evolution_queue 
                WHERE status = 'pending' AND (assigned_to = ? OR assigned_to IS NULL)
                ORDER BY 
                    CASE priority 
                        WHEN 'critical' THEN 1 
                        WHEN 'high' THEN 2 
                        WHEN 'medium' THEN 3 
                        ELSE 4 
                    END,
                    created_at ASC
            """, (assigned_to,))
        else:
            cursor.execute("""
                SELECT * FROM evolution_queue 
                WHERE status = 'pending'
                ORDER BY 
                    CASE priority 
                        WHEN 'critical' THEN 1 
                        WHEN 'high' THEN 2 
                        WHEN 'medium' THEN 3 
                        ELSE 4 
                    END,
                    created_at ASC
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            EvolutionTask(
                id=row[0],
                title=row[1],
                description=row[2],
                priority=row[3],
                status=row[4],
                source_insight_id=row[5],
                assigned_to=row[6],
                created_at=row[7],
                completed_at=row[8],
                result=json.loads(row[9]) if row[9] else None
            )
            for row in rows
        ]
    
    def complete_task(self, task_id: str, result: dict = None):
        """Mark a task as completed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE evolution_queue 
            SET status = 'completed', 
                completed_at = ?,
                result = ?
            WHERE id = ?
        """, (
            datetime.now(timezone.utc).isoformat(),
            json.dumps(result or {}),
            task_id
        ))
        
        conn.commit()
        conn.close()
    
    # === Activity Logging ===
    
    def _log_activity(self, conn: sqlite3.Connection, agent_id: str, action: str, target: str = None, details: dict = None):
        """Log agent activity."""
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agent_activity (agent_id, action, target, timestamp, details)
            VALUES (?, ?, ?, ?, ?)
        """, (
            agent_id,
            action,
            target,
            datetime.now(timezone.utc).isoformat(),
            json.dumps(details or {})
        ))
    
    def log_activity(self, agent_id: str, action: str, target: str = None, details: dict = None):
        """Public method to log activity."""
        conn = sqlite3.connect(self.db_path)
        self._log_activity(conn, agent_id, action, target, details)
        conn.commit()
        conn.close()
    
    # === Stats ===
    
    def get_stats(self) -> dict:
        """Get database statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM insights")
        insight_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM evolution_queue WHERE status = 'pending'")
        pending_tasks = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM evolution_queue WHERE status = 'completed'")
        completed_tasks = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT agent_id) FROM agent_activity")
        active_agents = cursor.fetchone()[0]
        
        cursor.execute("SELECT source, COUNT(*) FROM insights GROUP BY source")
        by_source = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            "total_insights": insight_count,
            "pending_tasks": pending_tasks,
            "completed_tasks": completed_tasks,
            "active_agents": active_agents,
            "insights_by_source": by_source,
            "db_path": str(self.db_path)
        }


# Singleton
_intel_db: Optional[IntelligenceDB] = None

def get_intel_db() -> IntelligenceDB:
    """Get the shared intelligence database."""
    global _intel_db
    if _intel_db is None:
        _intel_db = IntelligenceDB()
    return _intel_db


if __name__ == "__main__":
    db = get_intel_db()
    
    print("📊 Intelligence Database")
    print("=" * 50)
    
    # Add test insight
    insight_id = db.add_insight(
        source=InsightSource.AGENT_OBSERVATION,
        category="coordination",
        content="Intelligence DB is now operational",
        created_by="warp_regent",
        priority=InsightPriority.HIGH
    )
    print(f"Added insight: {insight_id}")
    
    # Add test task
    task_id = db.add_task(
        title="Test the intelligence pipeline",
        description="Verify insights flow from source to action",
        priority=InsightPriority.HIGH,
        source_insight_id=insight_id,
        assigned_to="openclaw"
    )
    print(f"Added task: {task_id}")
    
    print(f"\nStats: {json.dumps(db.get_stats(), indent=2)}")
