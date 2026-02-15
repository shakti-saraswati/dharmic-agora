#!/usr/bin/env python3
"""DGM Evolution Orchestrator - Main evolution loop"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dgm.mutator import mutate_genome
from dgm.fitness import evaluate_fitness


def load_genome(path="dgm/genome.json"):
    """Load current genome from JSON"""
    with open(path, 'r') as f:
        return json.load(f)


def save_genome(genome, path="dgm/genome.json"):
    """Save genome to JSON"""
    with open(path, 'w') as f:
        json.dump(genome, f, indent=2)


def save_elite(genome, fitness, generation):
    """Archive elite genome"""
    os.makedirs("dgm/archive/elite", exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"dgm/archive/elite/gen_{generation:06d}_{timestamp}_fit_{fitness:.4f}.json"
    
    data = {
        "generation": generation,
        "fitness": fitness,
        "timestamp": timestamp,
        "genome": genome
    }
    
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)


def log_history(generation, fitness, improved, genome):
    """Append to history log"""
    os.makedirs("dgm", exist_ok=True)
    
    entry = {
        "generation": generation,
        "fitness": fitness,
        "improved": improved,
        "timestamp": datetime.utcnow().isoformat(),
        "genome": genome
    }
    
    with open("dgm/history.jsonl", 'a') as f:
        f.write(json.dumps(entry) + "\n")


def main():
    """Main evolution loop - runs forever"""
    print("🧬 DGM Evolution Engine Starting...")
    
    # Initialize
    current_genome = load_genome()
    current_fitness = evaluate_fitness(current_genome)
    generation = 0
    
    print(f"📊 Initial fitness: {current_fitness:.4f}")
    log_history(generation, current_fitness, False, current_genome)
    
    # Evolution loop
    while True:
        generation += 1
        print(f"\n🔄 Generation {generation}")
        
        # Mutate
        mutated_genome = mutate_genome(current_genome)
        
        # Evaluate
        mutated_fitness = evaluate_fitness(mutated_genome)
        print(f"   Current: {current_fitness:.4f} | Mutated: {mutated_fitness:.4f}", end="")
        
        # Selection
        if mutated_fitness > current_fitness:
            improvement = mutated_fitness - current_fitness
            print(f" | ✅ IMPROVEMENT +{improvement:.4f}")
            
            # Accept mutation
            current_genome = mutated_genome
            current_fitness = mutated_fitness
            
            # Save as current
            save_genome(current_genome)
            
            # Archive elite
            save_elite(current_genome, current_fitness, generation)
            
            # Log
            log_history(generation, current_fitness, True, current_genome)
        else:
            print(" | ❌ Reject")
            log_history(generation, mutated_fitness, False, mutated_genome)


if __name__ == "__main__":
    main()
