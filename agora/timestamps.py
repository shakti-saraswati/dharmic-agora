#!/usr/bin/env python3
"""
DHARMIC_AGORA Timestamp Utility

Standard: Store in UTC, display in local (Bali UTC+8)

Usage:
    from timestamps import now_utc, now_local, to_local, format_timestamp
    
    ts = now_utc()           # For storage: "2026-02-06T04:55:48+00:00"
    local = now_local()      # For display: "2026-02-06T12:55:48+08:00"
    display = to_local(ts)   # Convert stored UTC to local
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional, Union

# Bali timezone: UTC+8 (WITA - Central Indonesia Time)
BALI_OFFSET = timedelta(hours=8)
BALI_TZ = timezone(BALI_OFFSET, name="WITA")

# Default local timezone (can be changed)
LOCAL_TZ = BALI_TZ


def now_utc() -> str:
    """Get current time in UTC (for storage)."""
    return datetime.now(timezone.utc).isoformat()


def now_local() -> str:
    """Get current time in local timezone (for display)."""
    return datetime.now(LOCAL_TZ).isoformat()


def now_both() -> dict:
    """Get both UTC and local timestamps."""
    utc = datetime.now(timezone.utc)
    local = utc.astimezone(LOCAL_TZ)
    return {
        "utc": utc.isoformat(),
        "local": local.isoformat(),
        "timezone": "WITA (UTC+8)"
    }


def to_utc(timestamp: Union[str, datetime]) -> str:
    """Convert any timestamp to UTC."""
    if isinstance(timestamp, str):
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    else:
        dt = timestamp
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    return dt.astimezone(timezone.utc).isoformat()


def to_local(timestamp: Union[str, datetime]) -> str:
    """Convert any timestamp to local (Bali) time."""
    if isinstance(timestamp, str):
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    else:
        dt = timestamp
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    return dt.astimezone(LOCAL_TZ).isoformat()


def format_timestamp(timestamp: Union[str, datetime], include_date: bool = True) -> str:
    """Format timestamp for human-readable display."""
    if isinstance(timestamp, str):
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    else:
        dt = timestamp
    
    local_dt = dt.astimezone(LOCAL_TZ)
    
    if include_date:
        return local_dt.strftime("%Y-%m-%d %H:%M:%S WITA")
    else:
        return local_dt.strftime("%H:%M:%S WITA")


def format_relative(timestamp: Union[str, datetime]) -> str:
    """Format timestamp as relative time (e.g., '5 minutes ago')."""
    if isinstance(timestamp, str):
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    else:
        dt = timestamp
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    diff = now - dt.astimezone(timezone.utc)
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"


# For convenience
def timestamp() -> str:
    """Alias for now_utc() - use this for all storage."""
    return now_utc()


if __name__ == "__main__":
    print("🕐 DHARMIC_AGORA Timestamps")
    print("=" * 50)
    print(f"UTC (storage):    {now_utc()}")
    print(f"Bali (display):   {now_local()}")
    print(f"Formatted:        {format_timestamp(now_utc())}")
    print()
    both = now_both()
    print(f"Both: {both}")
