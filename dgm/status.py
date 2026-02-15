#!/usr/bin/env python3
"""DGC Status Reporter — check evolution health."""
import json, os, subprocess
from pathlib import Path
from datetime import datetime

DGM_DIR = Path(__file__).parent

def report():
    # Genome state
    genome = json.load(open(DGM_DIR / "genome.json"))
    
    # History stats
    history = DGM_DIR / "history.jsonl"
    total_gens = 0
    improvements = 0
    if history.exists():
        with open(history) as f:
            for line in f:
                total_gens += 1
                entry = json.loads(line)
                if entry.get("improved"):
                    improvements += 1
    
    # Elite archive
    elite_dir = DGM_DIR / "archive" / "elite"
    elite_count = len(list(elite_dir.glob("*.json"))) if elite_dir.exists() else 0
    
    # Process running?
    try:
        result = subprocess.run(["pgrep", "-f", "dgm/orchestrator.py"], capture_output=True)
        running = result.returncode == 0
        pid = result.stdout.decode().strip() if running else None
    except:
        running = False
        pid = None
    
    # Current fitness
    current_fitness = 0
    if elite_count > 0:
        latest = sorted(elite_dir.glob("*.json"))[-1]
        latest_data = json.loads(latest.read_text())
        current_fitness = latest_data.get("fitness", 0)
    
    print("=" * 50)
    print("🧬 DGC EVOLUTION STATUS")
    print("=" * 50)
    print(f"Running: {'✅ PID ' + pid if running else '❌ STOPPED'}")
    print(f"Generations: {total_gens:,}")
    print(f"Improvements: {improvements} ({improvements/max(total_gens,1)*100:.1f}%)")
    print(f"Elite archive: {elite_count} genomes")
    print(f"Current fitness: {current_fitness:.4f}")
    print(f"\nGenome weights:")
    print(f"  Gates:      {genome['composite_weights']['gates']:.3f}")
    print(f"  Depth:      {genome['composite_weights']['depth']:.3f}")  
    print(f"  Reputation: {genome['composite_weights']['reputation']:.3f}")
    print(f"\nGate weights:")
    for k, v in genome['gate_weights'].items():
        print(f"  {k}: {v:.3f}")
    print("=" * 50)

if __name__ == "__main__":
    report()
