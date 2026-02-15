"""DGM Mutator - Applies random mutations to genome"""

import random
import json
from copy import deepcopy


def mutate_genome(genome):
    """Apply ONE random mutation to genome - returns new genome"""
    mutated = deepcopy(genome)
    
    # Choose mutation target randomly
    mutation_type = random.choice(['gate_weight', 'composite_weight', 'threshold'])
    
    if mutation_type == 'gate_weight':
        # Mutate a gate weight
        gate_name = random.choice(list(mutated['gate_weights'].keys()))
        old_value = mutated['gate_weights'][gate_name]
        noise = random.gauss(0, 0.1)  # Gaussian noise, sigma=0.1
        new_value = max(0.0, old_value + noise)  # Keep non-negative
        mutated['gate_weights'][gate_name] = new_value
        
    elif mutation_type == 'composite_weight':
        # Mutate composite weight (renormalize after)
        comp_name = random.choice(list(mutated['composite_weights'].keys()))
        old_value = mutated['composite_weights'][comp_name]
        noise = random.gauss(0, 0.05)  # Smaller noise for weights that sum
        new_value = max(0.01, old_value + noise)  # Keep positive
        mutated['composite_weights'][comp_name] = new_value
        
        # Renormalize to sum to 1.0
        total = sum(mutated['composite_weights'].values())
        for k in mutated['composite_weights']:
            mutated['composite_weights'][k] /= total
            
    elif mutation_type == 'threshold':
        # Mutate a threshold
        thresh_name = random.choice(list(mutated['thresholds'].keys()))
        old_value = mutated['thresholds'][thresh_name]
        noise = random.gauss(0, 0.05)
        new_value = max(0.0, min(1.0, old_value + noise))  # Clamp to [0,1]
        mutated['thresholds'][thresh_name] = new_value
    
    return mutated


def mutate_genome_from_file(input_path, output_path):
    """Load genome, mutate, save - for standalone use"""
    with open(input_path, 'r') as f:
        genome = json.load(f)
    
    mutated = mutate_genome(genome)
    
    with open(output_path, 'w') as f:
        json.dump(mutated, f, indent=2)
    
    return mutated


if __name__ == "__main__":
    # Standalone test
    import sys
    if len(sys.argv) >= 3:
        mutate_genome_from_file(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python mutator.py <input.json> <output.json>")
