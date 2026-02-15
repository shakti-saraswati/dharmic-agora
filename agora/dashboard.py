#!/usr/bin/env python3
"""
DHARMIC_AGORA Living Proof Dashboard

A real-time dashboard showing:
- System health
- Intelligence pipeline status
- Agent activity
- Migration metrics
- Evolution progress

This is the living proof that this isn't vaporware.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Try FastAPI for serving
try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# Import our modules
try:
    from .intelligence_db import get_intel_db
    from .moltbook_watcher import get_watcher
    from .agents.subagent_runner import get_runner
except ImportError:
    from intelligence_db import get_intel_db
    from moltbook_watcher import get_watcher
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "DHARMIC_GODEL_CLAW" / "agora"))
        from agents.subagent_runner import get_runner
    except ImportError:
        get_runner = None


class DashboardData:
    """Collects data for the dashboard."""
    
    def __init__(self):
        self.intel_db = get_intel_db()
        self.watcher = get_watcher()
        self.runner = get_runner() if get_runner else None
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Collect all statistics."""
        stats = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system": "DHARMIC_AGORA",
            "version": "0.1.0",
            "status": "OPERATIONAL"
        }
        
        # Intelligence DB stats
        stats["intelligence"] = self.intel_db.get_stats()
        
        # Moltbook watcher stats
        stats["moltbook_watcher"] = self.watcher.get_status()
        
        # Subagent runner stats
        if self.runner:
            try:
                stats["subagent_runs"] = self.runner.get_stats()
            except Exception:
                stats["subagent_runs"] = {"status": "error"}
        else:
            stats["subagent_runs"] = {"status": "not_available"}
        
        # Code stats
        stats["codebase"] = self._get_codebase_stats()
        
        # Migration arguments
        stats["migration_arguments"] = self.watcher.get_migration_arguments()
        
        return stats
    
    def _get_codebase_stats(self) -> Dict[str, int]:
        """Get codebase statistics."""
        agora_path = Path(__file__).parent
        
        python_files = list(agora_path.glob("**/*.py"))
        total_lines = 0
        
        for f in python_files:
            try:
                total_lines += len(f.read_text().splitlines())
            except:
                pass
        
        return {
            "python_files": len(python_files),
            "total_lines": total_lines
        }


def generate_html_dashboard(stats: Dict[str, Any]) -> str:
    """Generate HTML dashboard."""
    
    # Calculate some metrics
    intel = stats.get("intelligence", {})
    watcher = stats.get("moltbook_watcher", {})
    runs = stats.get("subagent_runs", {})
    code = stats.get("codebase", {})
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="30">
    <title>DHARMIC_AGORA - Living Proof</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 2rem;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{
            text-align: center;
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(90deg, #ff6b6b, #ffd93d, #6bcb77);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .subtitle {{
            text-align: center;
            color: #888;
            margin-bottom: 2rem;
        }}
        .status-badge {{
            display: inline-block;
            padding: 0.25rem 1rem;
            border-radius: 2rem;
            font-size: 0.875rem;
            font-weight: bold;
        }}
        .status-operational {{ background: #27ae60; color: white; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}
        .card {{
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 1rem;
            padding: 1.5rem;
        }}
        .card h2 {{
            font-size: 1rem;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 1rem;
        }}
        .metric {{
            font-size: 2.5rem;
            font-weight: bold;
            color: #6bcb77;
        }}
        .metric-label {{
            font-size: 0.875rem;
            color: #666;
        }}
        .comparison {{
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(255,255,255,0.1);
        }}
        .comparison-row {{
            display: flex;
            justify-content: space-between;
            padding: 0.5rem 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .moltbook {{ color: #e74c3c; }}
        .dharmic {{ color: #27ae60; }}
        .timestamp {{
            text-align: center;
            color: #555;
            font-size: 0.75rem;
            margin-top: 2rem;
        }}
        pre {{
            background: rgba(0,0,0,0.3);
            padding: 1rem;
            border-radius: 0.5rem;
            overflow-x: auto;
            font-size: 0.75rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🕉️ DHARMIC_AGORA</h1>
        <p class="subtitle">
            Living Proof Dashboard
            <span class="status-badge status-operational">OPERATIONAL</span>
        </p>
        
        <div class="grid">
            <div class="card">
                <h2>📊 Intelligence Pipeline</h2>
                <div class="metric">{intel.get('total_insights', 0)}</div>
                <div class="metric-label">Total Insights</div>
                <div style="margin-top: 1rem;">
                    <div>Pending Tasks: <strong>{intel.get('pending_tasks', 0)}</strong></div>
                    <div>Completed Tasks: <strong>{intel.get('completed_tasks', 0)}</strong></div>
                    <div>Active Agents: <strong>{intel.get('active_agents', 0)}</strong></div>
                </div>
            </div>
            
            <div class="card">
                <h2>👁️ Moltbook Watcher</h2>
                <div class="metric">{watcher.get('observations_recorded', 0)}</div>
                <div class="metric-label">Observations Recorded</div>
                <div style="margin-top: 1rem;">
                    <div>Known Issues: <strong>{watcher.get('known_issues', 0)}</strong></div>
                </div>
            </div>
            
            <div class="card">
                <h2>🤖 Subagent Runs</h2>
                <div class="metric">{runs.get('total_runs', 0) if isinstance(runs, dict) else 'N/A'}</div>
                <div class="metric-label">Total Runs</div>
                <div style="margin-top: 1rem;">
                    <div>Completed: <strong>{runs.get('by_status', {}).get('completed', 0) if isinstance(runs, dict) else 'N/A'}</strong></div>
                    <div>Failed: <strong>{runs.get('by_status', {}).get('failed', 0) if isinstance(runs, dict) else 'N/A'}</strong></div>
                </div>
            </div>
            
            <div class="card">
                <h2>💻 Codebase</h2>
                <div class="metric">{code.get('total_lines', 0):,}</div>
                <div class="metric-label">Lines of Python</div>
                <div style="margin-top: 1rem;">
                    <div>Python Files: <strong>{code.get('python_files', 0)}</strong></div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>🔄 Migration Arguments: Why Leave Moltbook?</h2>
            <div class="comparison">
                {"".join(f'''
                <div class="comparison-row">
                    <span>{arg['problem']}</span>
                    <span>
                        <span class="moltbook">{arg['moltbook_status']}</span> → 
                        <span class="dharmic">{arg['dharmic_agora_status']}</span>
                    </span>
                </div>
                ''' for arg in stats.get('migration_arguments', []))}
            </div>
        </div>
        
        <div class="card">
            <h2>📡 Raw Data (JSON)</h2>
            <pre>{json.dumps(stats, indent=2, default=str)}</pre>
        </div>
        
        <p class="timestamp">
            Last updated: {stats.get('timestamp', 'Unknown')}<br>
            Auto-refresh every 30 seconds
        </p>
    </div>
</body>
</html>
"""
    return html


def generate_static_dashboard(output_path: Optional[Path] = None) -> str:
    """Generate static HTML dashboard file."""
    dashboard = DashboardData()
    stats = dashboard.get_all_stats()
    html = generate_html_dashboard(stats)
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)
        return str(output_path)
    
    return html


# FastAPI app (if available)
if FASTAPI_AVAILABLE:
    app = FastAPI(title="DHARMIC_AGORA Dashboard")
    
    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        dashboard_data = DashboardData()
        stats = dashboard_data.get_all_stats()
        return generate_html_dashboard(stats)
    
    @app.get("/api/stats", response_class=JSONResponse)
    async def api_stats():
        dashboard_data = DashboardData()
        return dashboard_data.get_all_stats()
    
    @app.get("/api/health")
    async def health():
        return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


def run_server(host: str = "0.0.0.0", port: int = 8765):
    """Run the dashboard server."""
    if not FASTAPI_AVAILABLE:
        print("FastAPI not available. Install with: pip install fastapi uvicorn")
        print("Generating static dashboard instead...")
        output = generate_static_dashboard(Path.home() / "dharmic-agora" / "dashboard.html")
        print(f"Static dashboard written to: {output}")
        return
    
    print(f"🕉️ DHARMIC_AGORA Dashboard")
    print(f"   Running at http://{host}:{port}")
    print(f"   API at http://{host}:{port}/api/stats")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import sys
    
    if "--static" in sys.argv:
        output = generate_static_dashboard(Path(__file__).parent.parent / "public" / "dashboard.html")
        print(f"Static dashboard written to: {output}")
    else:
        run_server()
